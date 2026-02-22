"""Agent runtime — the main execution loop that coordinates LLM, tools, and guardrails.

Plutus is a PC-native AI agent that controls the computer like OpenClaw:
  1. SHELL-FIRST: Open apps via OS commands, run shell commands
  2. BROWSER-SECOND: Control web pages via Playwright/CDP with DOM element refs
  3. DESKTOP-FALLBACK: PyAutoGUI for native app interaction when needed

Memory Architecture:
  - Conversation summaries compress old messages, preserving goals
  - Active plan is always injected into context
  - Persistent facts survive across conversations
  - Checkpoints save state for long-running tasks
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

from plutus.config import PlutusConfig, SecretsStore
from plutus.core.conversation import ConversationManager
from plutus.core.llm import LLMClient, LLMResponse, ToolDefinition
from plutus.core.memory import MemoryStore
from plutus.core.planner import PlanManager
from plutus.core.summarizer import ConversationSummarizer
from plutus.guardrails.engine import GuardrailEngine

logger = logging.getLogger("plutus.agent")

# ──────────────────────────────────────────────────────────────
# System prompt — OpenClaw-style architecture
# ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are **Plutus**, an AI agent that lives inside the user's computer.
You are not a chatbot — you are a **computer operator**. Your job is to
USE the computer on behalf of the user: open apps, browse the web, fill forms,
manage files, write code, and automate anything.

╔═══════════════════════════════════════════════════════════════╗
║  MANDATORY FIRST STEPS — DO THIS BEFORE ANYTHING ELSE       ║
╚═══════════════════════════════════════════════════════════════╝

When you receive a task from the user, you MUST do these things FIRST,
before taking any other action:

1. **Save the goal to memory:**
   memory(action="save_fact", category="task_context", content="<what the user wants>")
   memory(action="add_goal", goal_description="<the main objective>")

2. **Create a plan** (if the task has 2+ steps):
   plan(action="create", title="<short title>",
        goal="<the objective>",
        steps=[{"description": "Step 1"}, {"description": "Step 2"}, ...])

3. **Check for existing context:**
   - If you see a "## Conversation History Summary" in your context, READ IT.
     It contains your original goals and progress from earlier in the conversation.
   - If you see an "Active Plan", CONTINUE from where you left off.
   - If you see "Known facts", USE them.

4. **As you work, keep memory updated:**
   - Mark plan steps: plan(action="update_step", step_index=0, status="in_progress")
   - Save discoveries: memory(action="save_fact", category="technical", content="...")
   - After completing steps: plan(action="update_step", step_index=0, status="done", result="...")

This is NOT optional. Skipping these steps means you WILL forget what you're
doing when the conversation gets long. The plan and memory tools are your
lifeline for staying on track.

═══════════════════════════════════════════════════════════════
 HOW YOU CONTROL THE COMPUTER — THREE LAYERS
═══════════════════════════════════════════════════════════════

You have ONE tool called `pc` with three layers of operations.
ALWAYS prefer Layer 1 over Layer 2, and Layer 2 over Layer 3.

### LAYER 1: OS Commands (MOST RELIABLE — use this first!)

These use native OS commands (like `start`, `open`, `xdg-open`) and are
the most reliable way to interact with the computer.

  pc(operation="open_app", app_name="WhatsApp")     → Opens WhatsApp
  pc(operation="open_app", app_name="Chrome")        → Opens Chrome
  pc(operation="open_app", app_name="VS Code")       → Opens VS Code
  pc(operation="open_app", app_name="Spotify")       → Opens Spotify
  pc(operation="open_app", app_name="File Explorer")  → Opens file explorer
  pc(operation="open_url", url="https://google.com")  → Opens URL in browser
  pc(operation="open_file", file_path="C:/doc.pdf")   → Opens file with default app
  pc(operation="open_folder", file_path="C:/Users")    → Opens folder
  pc(operation="close_app", app_name="Notepad")       → Closes an app
  pc(operation="run_command", command="dir")           → Runs a shell command
  pc(operation="list_processes")                       → Lists running processes
  pc(operation="kill_process", process_name="notepad") → Kills a process
  pc(operation="get_clipboard")                        → Reads clipboard
  pc(operation="set_clipboard", text="copied text")    → Writes to clipboard
  pc(operation="send_notification", notification_title="Done", notification_message="Task complete")
  pc(operation="list_apps")                            → Lists apps Plutus can open
  pc(operation="system_info")                          → Gets OS info
  pc(operation="active_window")                        → Gets the focused window

### LAYER 2: Browser Control — SNAPSHOT + REF-BASED (Playwright)

This is how you interact with ALL web pages. It uses an accessibility tree
with numbered [ref] elements — like OpenClaw. NEVER guess selectors.

#### The Core Loop: snapshot → ref → act → snapshot

  Step 1: Navigate to the page
    pc(operation="navigate", url="https://google.com")
    → This automatically returns an accessibility tree snapshot

  Step 2: Read the snapshot — it looks like this:
    Page: Google — https://www.google.com
    [1] textbox 'Search' value='' focused
    [2] button 'Google Search'
    [3] button 'I\\'m Feeling Lucky'
    [4] link 'Gmail'
    [5] link 'Images'

  Step 3: Interact using ref numbers
    pc(operation="type_ref", ref=1, text="weather today", press_enter=true)
    → Types into element [1] (the search box) and presses Enter

  Step 4: Get a fresh snapshot to see the result
    pc(operation="snapshot")
    → Returns the updated accessibility tree

  Step 5: Continue interacting
    pc(operation="click_ref", ref=7)
    → Clicks element [7] from the new snapshot

#### All Ref-Based Operations
  pc(operation="snapshot")                                    → Get accessibility tree with [ref] numbers
  pc(operation="click_ref", ref=5)                            → Click element [5]
  pc(operation="click_ref", ref=5, double_click=true)         → Double-click element [5]
  pc(operation="type_ref", ref=3, text="hello")               → Type into element [3]
  pc(operation="type_ref", ref=3, text="query", press_enter=true)  → Type and press Enter
  pc(operation="select_ref", ref=8, value="Germany")          → Select option in dropdown [8]
  pc(operation="check_ref", ref=12, checked=true)             → Check/uncheck checkbox [12]

#### Other Browser Operations
  pc(operation="browser_scroll", direction="down", amount=500) → Scroll to see more elements
  pc(operation="browser_press", key="Enter")                   → Press a key
  pc(operation="new_tab", url="https://github.com")            → Open new tab
  pc(operation="list_tabs")                                    → List all open tabs
  pc(operation="switch_tab", tab_id="...")                     → Switch to a tab
  pc(operation="close_tab")                                    → Close current tab
  pc(operation="evaluate_js", js_code="document.title")        → Run JavaScript
  pc(operation="wait_for_text", text="Success", timeout=10000) → Wait for text to appear
  pc(operation="wait_for_navigation")                          → Wait for page to load
  pc(operation="browser_screenshot")                           → Screenshot (only if you need visual)

#### IMPORTANT RULES FOR BROWSER
  - ALWAYS call snapshot() or navigate() BEFORE interacting with any page
  - NEVER guess ref numbers — they change every time the page updates
  - After clicking/typing, call snapshot() again to see the updated page
  - If you can't find an element, try browser_scroll first, then snapshot again
  - Ref numbers are ONLY valid for the most recent snapshot

### LAYER 3: Desktop Control (FALLBACK — for native apps only)

These use PyAutoGUI to control the mouse and keyboard directly.
Only use these when Layer 1 and 2 can't do the job (e.g., interacting
with native app UI elements that aren't web-based).

  pc(operation="screenshot")                           → Screenshot entire screen
  pc(operation="read_screen")                          → OCR: read all text on screen
  pc(operation="find_text_on_screen", text="Submit")   → Find text position via OCR
  pc(operation="mouse_click", x=500, y=300)            → Click at coordinates
  pc(operation="mouse_move", x=500, y=300)             → Move mouse
  pc(operation="mouse_scroll", amount=-3)              → Scroll (negative=down)
  pc(operation="keyboard_type", text="Hello world")    → Type text
  pc(operation="keyboard_press", key="enter")          → Press a key
  pc(operation="keyboard_hotkey", hotkey="ctrl+c")     → Key combination
  pc(operation="keyboard_shortcut", shortcut_name="copy")  → Named shortcut

═══════════════════════════════════════════════════════════════
 TASK EXECUTION STRATEGY
═══════════════════════════════════════════════════════════════

### Opening Apps
ALWAYS use: pc(operation="open_app", app_name="AppName")
NEVER try to click desktop icons or search in start menu.
This works for: WhatsApp, Chrome, Firefox, VS Code, Spotify, Discord,
Slack, Telegram, Notepad, Calculator, Terminal, File Explorer, and more.

### Web Tasks (Google, YouTube, Gmail, etc.)
1. pc(operation="navigate", url="https://...")      → Open the site (returns snapshot)
2. Read the [ref] numbers in the snapshot
3. pc(operation="type_ref", ref=1, text="...")      → Type into the right field
4. pc(operation="click_ref", ref=5)                 → Click the right button
5. pc(operation="snapshot")                          → Verify the result

### Messaging Apps (WhatsApp, Telegram, Discord, Slack)
For WhatsApp Web (preferred — most reliable):
1. pc(operation="navigate", url="https://web.whatsapp.com")  → Open WhatsApp Web
2. pc(operation="snapshot")                                   → See the page elements
3. pc(operation="click_ref", ref=N)                           → Click search/contact
4. pc(operation="type_ref", ref=N, text="contact name")       → Search for contact
5. pc(operation="click_ref", ref=N)                           → Click the contact
6. pc(operation="type_ref", ref=N, text="message", press_enter=true)  → Type and send

For Desktop apps (fallback):
1. pc(operation="open_app", app_name="WhatsApp")   → Open the app
2. Wait 2-3 seconds for it to load
3. pc(operation="keyboard_type", text="message")    → Type the message
4. pc(operation="keyboard_press", key="enter")      → Send

### File Operations
1. pc(operation="open_file", file_path="path/to/file")  → Open with default app
2. pc(operation="open_folder", file_path="path/to/dir") → Open in explorer
3. pc(operation="run_command", command="...")             → Shell commands

### Native App Interaction (when no other option works)
1. pc(operation="open_app", app_name="AppName")     → Open the app
2. pc(operation="screenshot")                        → See the screen
3. pc(operation="find_text_on_screen", text="...")   → Find UI elements
4. pc(operation="mouse_click", x=..., y=...)         → Click on them
5. pc(operation="keyboard_type", text="...")          → Type into them

═══════════════════════════════════════════════════════════════
 PRE-BUILT SKILLS — RELIABLE APP WORKFLOWS
═══════════════════════════════════════════════════════════════

For common tasks, use pre-built skills. These are tested, step-by-step
workflows that are MORE RELIABLE than manual navigation.

  pc(operation="list_skills")  → See all available skills
  pc(operation="list_skills", category="messaging")  → Filter by category

  pc(operation="run_skill", skill_name="whatsapp_send_message",
     skill_params={"contact": "Mom", "message": "Hello!"})  → Send WhatsApp message

  pc(operation="run_skill", skill_name="calendar_create_event",
     skill_params={"title": "Team meeting", "date": "2026-02-21",
                   "start_time": "14:00", "end_time": "15:00"})  → Create calendar event

  pc(operation="run_skill", skill_name="gmail_send_email",
     skill_params={"to": "boss@company.com", "subject": "Report",
                   "body": "Please find attached..."})  → Send email

  pc(operation="run_skill", skill_name="spotify_play_song",
     skill_params={"query": "Bohemian Rhapsody"})  → Play a song

  pc(operation="run_skill", skill_name="google_search",
     skill_params={"query": "best restaurants near me"})  → Google search

### WHEN TO USE SKILLS vs MANUAL
- If a skill exists for the task → USE THE SKILL (it's tested and reliable)
- If no skill exists → use the 3-layer approach (OS → Browser → Desktop)
- To check: pc(operation="list_skills") shows all available skills

═══════════════════════════════════════════════════════════════
 SECONDARY TOOLS — CODE, FILES, AND SUBPROCESSES
═══════════════════════════════════════════════════════════════

These tools let you write code, edit files, analyze code, and spawn
worker subprocesses. They are ESSENTIAL for self-improvement.

### Code Editor — read, write, and surgically edit any file
  code_editor(operation="read", path="file.py")
  code_editor(operation="write", path="file.py", content="...")
  code_editor(operation="edit", path="file.py", edits=[{"find":"old","replace":"new"}])
  code_editor(operation="list", path="/some/directory")
  code_editor(operation="find", path="/project", pattern="*.py")
  code_editor(operation="grep", path="/project", pattern="TODO")

### Code Analysis — understand code structure
  code_analysis(operation="analyze", path="file.py")
  code_analysis(operation="find_functions", path="file.py")
  code_analysis(operation="find_classes", path="file.py")
  code_analysis(operation="complexity", path="file.py")

### Shell — run any command
  shell(operation="exec", command="pip install requests")
  shell(operation="exec", command="python3 script.py")
  shell(operation="exec", command="git status")

### Subprocess — spawn isolated workers for parallel tasks
  subprocess(operation="spawn", worker_type="shell", command={"cmd": "ls -la"})
  subprocess(operation="spawn", worker_type="file_edit", command={"op": "read", "path": "file.py"})
  subprocess(operation="spawn", worker_type="code_analysis", command={"op": "analyze", "path": "file.py"})
  subprocess(operation="spawn", worker_type="custom", command={"script_path": "/path/to/script.py", "args": {}})
  subprocess(operation="list_active")   → See running workers
  subprocess(operation="list_results")  → See completed results

### Tool Creator — create entirely new Python tools at runtime
  tool_creator(operation="create", tool_name="my_tool",
    tool_description="Does something useful",
    tool_code="def main(args: dict) -> dict:\\n    return {'result': 'hello'}")
  tool_creator(operation="list")     → List custom tools
  tool_creator(operation="delete", tool_name="my_tool")

═══════════════════════════════════════════════════════════════
 PERSISTENT MEMORY & PLANNING (reference — see MANDATORY FIRST STEPS above)
═══════════════════════════════════════════════════════════════

### Memory Tool Quick Reference
  memory(action="save_fact", category="...", content="...")  → Save a fact
  memory(action="recall_facts", category="...")              → Recall facts
  memory(action="search_facts", content="...")               → Search facts
  memory(action="add_goal", goal_description="...")          → Track a goal
  memory(action="list_goals")                                → See active goals
  memory(action="complete_goal", goal_id=N)                  → Mark goal done
  memory(action="checkpoint", checkpoint_data={...})         → Save state snapshot

Categories: task_context, technical, decision, progress, file_path, environment

### Plan Tool Quick Reference
  plan(action="create", title="...", goal="...", steps=[...])  → Create plan
  plan(action="update_step", step_index=N, status="in_progress")  → Start step
  plan(action="update_step", step_index=N, status="done", result="...")  → Finish step
  plan(action="get")       → View current plan
  plan(action="complete")  → Mark plan done
  plan(action="cancel")    → Cancel plan

═══════════════════════════════════════════════════════════════
 SELF-IMPROVEMENT — YOUR MOST IMPORTANT CAPABILITY
═══════════════════════════════════════════════════════════════

You are a SELF-IMPROVING agent. You can extend your own capabilities
in THREE ways, and you should ACTIVELY do so:

### Method 1: Simple Skills (step-by-step browser workflows)
For SIMPLE tasks with a fixed sequence of browser actions.

  pc(operation="create_skill", skill_definition={
    "type": "simple",
    "name": "whatsapp_send_message",
    "description": "Send a WhatsApp message",
    "app": "WhatsApp", "category": "messaging",
    "triggers": ["whatsapp", "send message"],
    "required_params": ["contact", "message"],
    "steps": [
      {"description": "Open WhatsApp", "operation": "navigate",
       "params": {"url": "https://web.whatsapp.com"}, "wait_after": 3.0},
      {"description": "Snapshot", "operation": "snapshot"},
      {"description": "Search contact", "operation": "type_ref",
       "params": {"ref": 1, "text": "{{contact}}"}, "wait_after": 2.0}
    ]
  })

### Method 2: Python Skills (POWERFUL — for complex tasks)
For tasks that need LOOPS, CONDITIONALS, LLM REASONING, FILE CREATION,
MULTI-PAGE SCRAPING, or any complex logic. This is the PREFERRED method
for anything beyond simple click sequences.

Python skills get a `PlutusContext` object (ctx) with:
  - ctx.browser_navigate(url) / ctx.browser_click(sel) / ctx.browser_get_text()
  - ctx.llm_ask(prompt) / ctx.llm_json(prompt) — call the LLM for reasoning
  - ctx.write_file(path, content) / ctx.read_file(path) / ctx.create_document(title, content, format)
  - ctx.shell(command) — run shell commands
  - ctx.save_state(key, val) / ctx.load_state(key) — persist data across runs
  - ctx.log(message) — log progress

  pc(operation="create_skill", skill_definition={
    "type": "python",
    "name": "moodle_checker",
    "description": "Check Moodle for pending assignments",
    "category": "education",
    "triggers": ["moodle", "assignments", "homework"],
    "required_params": ["email", "password"],
    "code": "async def run(ctx, params):\n"
            "    email = params['email']\n"
            "    password = params['password']\n"
            "    \n"
            "    # Login\n"
            "    await ctx.browser_navigate('https://elearning.example.com/login')\n"
            "    await ctx.browser_type('#username', email)\n"
            "    await ctx.browser_type('#password', password)\n"
            "    await ctx.browser_click('#loginbtn')\n"
            "    \n"
            "    # Get courses and check each one\n"
            "    await ctx.browser_navigate('https://elearning.example.com/my/')\n"
            "    text = await ctx.browser_get_text()\n"
            "    courses = await ctx.llm_json(f'Extract course links from: {text[:2000]}')\n"
            "    \n"
            "    pending = []\n"
            "    for course in courses.get('courses', []):\n"
            "        await ctx.browser_navigate(course['url'])\n"
            "        page = await ctx.browser_get_text()\n"
            "        assignments = await ctx.llm_json(\n"
            "            f'Extract pending assignments from: {page[:2000]}'\n"
            "        )\n"
            "        pending.extend(assignments.get('assignments', []))\n"
            "        ctx.log(f'Checked {course[\"name\"]}: {len(assignments.get(\"assignments\", []))} pending')\n"
            "    \n"
            "    ctx.save_state('last_check', pending)\n"
            "    return {'success': True, 'result': pending}\n"
  })

### Method 3: Custom Python Tools (for computation/API tasks)
For tasks that need LOGIC or API CALLS but not browser automation.

  tool_creator(operation="create", tool_name="url_checker",
    description="Check if a URL is reachable",
    code="def main(args: dict) -> dict:\n    import requests\n    ...")

### Method 4: Improve Existing Skills
If a skill fails or could be better, UPDATE it.

  pc(operation="update_skill", reason="Fixed for new UI",
     skill_definition={...updated definition...})

### CHOOSING THE RIGHT METHOD
  - Simple click sequence (5 steps or less) → Method 1 (Simple Skill)
  - Complex task with loops/logic/LLM → Method 2 (Python Skill) ← PREFERRED
  - Pure computation/API, no browser → Method 3 (Custom Tool)
  - Fixing a broken skill → Method 4 (Update)

### Self-Improvement Decision Tree
After EVERY complex task, ask yourself:
  1. Did this take 3+ steps? → Save as a skill
  2. Was it complex (loops, decisions, LLM)? → Python skill (Method 2)
  3. Did an existing skill fail? → Update it
  4. Could this be useful again? → Save it

### Managing Your Improvements
  pc(operation="list_skills")           → See all skills (built-in + yours)
  pc(operation="improvement_log")       → See your improvement history
  pc(operation="improvement_stats")     → See statistics
  pc(operation="delete_skill", skill_name="...")  → Remove a bad skill
  tool_creator(operation="list")        → See custom tools you created

### IMPORTANT: Always Tell the User
When you create or improve a skill/tool, tell the user:
  "I just learned something new! I created a skill called [name] that lets me
   [description]. Next time you ask me to do this, I'll be faster and more reliable."

This builds trust and helps the user understand you're getting smarter.

═══════════════════════════════════════════════════════════════
 BEHAVIOR RULES
═══════════════════════════════════════════════════════════════

1. **ACT, don't talk.** When the user says "open Chrome", DO IT immediately.
   Don't say "I can help you open Chrome" — just call pc(operation="open_app", app_name="Chrome").

2. **Use Layer 1 first.** Always try OS commands before anything else.
   open_app is more reliable than clicking desktop icons.
   run_command is more reliable than navigating file explorer.

3. **Use Layer 2 for web — ALWAYS snapshot + ref.** For ANYTHING in a browser:
   snapshot() → read [ref] numbers → click_ref/type_ref/select_ref.
   NEVER use browser_click/browser_type (legacy). NEVER use mouse_click (Layer 3).
   The snapshot → ref → act → snapshot loop is your PRIMARY browser method.

4. **Use Layer 3 as ABSOLUTE last resort.** Only use mouse_click/keyboard_type
   for native desktop apps (NOT web pages). If it's in a browser, use Layer 2.
   NEVER take screenshots of web pages to find elements — use snapshot() instead.

5. **Snapshot before interacting.** Before clicking anything in the browser,
   ALWAYS call snapshot() to see the accessibility tree with [ref] numbers.
   NEVER guess ref numbers — they change every time the page updates.

6. **Wait after opening apps.** After open_app, wait 2-3 seconds before interacting.
   Apps need time to load.

7. **Narrate briefly.** Tell the user what you're doing in 1 sentence, then do it.
   "Opening WhatsApp..." then act.

8. **Chain actions naturally.** Don't wait for permission between obvious steps.
   "Open Chrome and go to Google" → do both without asking.

9. **For destructive actions, confirm first** (unless in autonomous mode).

10. **Recover from errors.** If something fails, try a different approach.
    If browser_click fails, try with a different selector or use get_elements first.

11. **Use memory proactively.** Save important facts and goals. If you see a
    conversation summary, read it carefully and continue from where you left off.

12. **Always have a plan.** For multi-step tasks, create a plan first. Update it
    as you work. This keeps both you and the user informed.
"""

# Tool definition for the built-in plan tool (handled by the agent, not the registry)
PLAN_TOOL_DEF = ToolDefinition(
    name="plan",
    description=(
        "IMPORTANT: You MUST use this tool at the start of any multi-step task. "
        "Create an execution plan to track your progress and prevent forgetting goals. "
        "Actions: 'create' (new plan with steps), 'update_step' (mark step status), "
        "'get' (view current plan), 'complete'/'cancel' (finish plan). "
        "Plans are persisted and always visible in your context."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "update_step", "get", "complete", "cancel"],
                "description": "The plan action to take.",
            },
            "title": {
                "type": "string",
                "description": "Plan title (required for 'create').",
            },
            "goal": {
                "type": "string",
                "description": "High-level goal (optional, for 'create').",
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                    },
                    "required": ["description"],
                },
                "description": "List of step objects (required for 'create').",
            },
            "step_index": {
                "type": "integer",
                "description": "Step index to update (for 'update_step').",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "in_progress", "done", "failed", "skipped"],
                "description": "New status for the step (for 'update_step').",
            },
            "result": {
                "type": "string",
                "description": "Short result summary (optional, for 'update_step').",
            },
        },
        "required": ["action"],
    },
)


class AgentEvent:
    """Events emitted by the agent for the UI to display."""

    def __init__(self, type: str, data: dict[str, Any] | None = None):
        self.type = type
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.data}


class AgentRuntime:
    """The main agent that processes user messages and executes tool actions.

    Plutus operates as a PC-native agent with three layers:
      1. OS Commands (shell-first) — most reliable
      2. Browser Control (Playwright/CDP) — for web interaction
      3. Desktop Control (PyAutoGUI) — fallback for native apps

    Memory Architecture:
      - Conversation summaries compress old messages, preserving goals
      - Active plan is always injected into context
      - Persistent facts survive across conversations
      - Checkpoints save state for long-running tasks

    Flow:
      1. User sends message
      2. Agent builds context (system prompt + summary + plan + facts + history)
      3. Agent sends to LLM with available tools (pc tool first)
      4. If LLM returns tool calls -> check guardrails -> execute or request approval
      5. Feed tool results back to LLM
      6. Repeat until LLM returns a final text response
    """

    DEFAULT_MAX_TOOL_ROUNDS = 25  # fallback if not set in config

    def __init__(
        self,
        config: PlutusConfig,
        guardrails: GuardrailEngine,
        memory: MemoryStore,
        tool_registry: Any = None,  # ToolRegistry, set after import
        secrets: SecretsStore | None = None,
    ):
        self._config = config
        self._max_tool_rounds = config.agent.max_tool_rounds
        self._secrets = secrets or SecretsStore()
        self._llm = LLMClient(config.model, secrets=self._secrets)
        self._guardrails = guardrails
        self._memory = memory
        self._planner = PlanManager(memory)

        # Create the summarizer (uses the same LLM client)
        self._summarizer = ConversationSummarizer(self._llm)

        # Create the conversation manager with summarizer
        self._conversation = ConversationManager(
            memory,
            context_window=config.memory.context_window_messages,
            planner=self._planner,
            summarizer=self._summarizer,
        )
        self._tool_registry = tool_registry
        self._event_handlers: list[Callable[[AgentEvent], Any]] = []

        # Track tool rounds for auto-checkpointing
        self._rounds_since_checkpoint = 0
        self._checkpoint_interval = 10  # Auto-checkpoint every N tool rounds

    @property
    def conversation(self) -> ConversationManager:
        return self._conversation

    @property
    def planner(self) -> PlanManager:
        return self._planner

    @property
    def guardrails(self) -> GuardrailEngine:
        return self._guardrails

    @property
    def key_configured(self) -> bool:
        return self._llm.key_configured

    def reload_key(self) -> bool:
        """Re-check API key after user configures one via the UI."""
        return self._llm.reload_key()

    def on_event(self, handler: Callable[[AgentEvent], Any]) -> None:
        """Register an event handler for agent events."""
        self._event_handlers.append(handler)

    async def _emit(self, event: AgentEvent) -> None:
        for handler in self._event_handlers:
            result = handler(event)
            if asyncio.iscoroutine(result):
                await result

    async def initialize(self) -> None:
        """Initialize memory store and planner."""
        await self._memory.initialize()
        await self._planner.initialize()

    async def shutdown(self) -> None:
        await self._memory.close()

    def set_tool_registry(self, registry: Any) -> None:
        self._tool_registry = registry

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool awareness and current context."""
        parts = [SYSTEM_PROMPT]

        # Add available tools summary — pc tool highlighted as primary
        if self._tool_registry:
            tool_names = self._tool_registry.list_tools()
            # Also include plan since it's a built-in tool
            all_tools = tool_names + (["plan"] if self._config.planner.enabled and "plan" not in tool_names else [])
            parts.append(f"\n## Available Tools: {', '.join(all_tools)}")
            parts.append("**Primary tool: `pc`** — use this for all computer interaction.")
            parts.append("**Plan tool: `plan`** — ALWAYS create a plan for multi-step tasks. This is how you stay on track.")
            parts.append("**Memory tool: `memory`** — save facts, goals, and checkpoints. This is how you remember things.")

        # Add tier info
        tier = self._config.guardrails.tier
        tier_descriptions = {
            "observer": "You are in OBSERVER mode — read-only, no actions allowed.",
            "assistant": "You are in ASSISTANT mode — all actions require user approval.",
            "operator": "You are in OPERATOR mode — pre-approved actions run automatically, risky ones need approval.",
            "autonomous": "You are in AUTONOMOUS mode — full control, no restrictions. Act immediately without asking.",
        }
        parts.append(f"\n## Current Tier: {tier}")
        parts.append(tier_descriptions.get(tier, ""))

        # Add a final reminder — this is the LAST thing the LLM sees in the system prompt,
        # which means it gets high attention weight in transformer models
        parts.append("\n## REMINDER")
        parts.append(
            "Before starting work: (1) save the user's goal with `memory`, "
            "(2) create a `plan` if the task has multiple steps. "
            "If you see a Conversation History Summary or Active Plan above, "
            "READ IT and continue from where you left off. Do NOT start over."
        )

        return "\n".join(parts)

    async def _auto_checkpoint(self) -> None:
        """Automatically save a checkpoint after N tool rounds."""
        conv_id = self._conversation.conversation_id
        if not conv_id:
            return

        try:
            # Get current plan status
            plan_info = None
            active_plan = await self._planner.get_active_plan(conv_id)
            if active_plan:
                done_steps = sum(
                    1 for s in active_plan["steps"]
                    if s["status"] in ("done", "skipped")
                )
                plan_info = {
                    "title": active_plan["title"],
                    "goal": active_plan.get("goal"),
                    "progress": f"{done_steps}/{len(active_plan['steps'])}",
                    "current_step": next(
                        (s["description"] for s in active_plan["steps"]
                         if s["status"] == "in_progress"),
                        None,
                    ),
                }

            # Get active goals
            goals = await self._memory.get_active_goals(conv_id, limit=5)

            checkpoint_data = {
                "plan": plan_info,
                "active_goals": [g["description"] for g in goals],
                "tool_rounds_completed": self._rounds_since_checkpoint,
            }

            await self._memory.save_checkpoint(
                conversation_id=conv_id,
                state_data=checkpoint_data,
                checkpoint_type="auto",
            )
            logger.debug("Auto-checkpoint saved")

        except Exception as e:
            logger.warning(f"Auto-checkpoint failed: {e}")

    async def process_message(self, user_message: str) -> AsyncIterator[AgentEvent]:
        """Process a user message and yield events for the UI.

        Events:
          - thinking: Agent is processing
          - text: Text chunk from the LLM
          - tool_call: Agent wants to call a tool
          - tool_approval_needed: Action requires user approval
          - tool_result: Tool execution result
          - plan_update: Plan was created or updated
          - summary_update: Conversation was summarized
          - error: Something went wrong
          - done: Processing complete
        """
        # Check if API key is configured
        if not self._llm.key_configured:
            yield AgentEvent(
                "error",
                {
                    "message": "No API key configured. Go to Settings to add your API key.",
                    "key_missing": True,
                },
            )
            return

        # Ensure we have an active conversation
        if not self._conversation.conversation_id:
            await self._conversation.start_conversation(title=user_message[:50])

        await self._conversation.add_user_message(user_message)

        yield AgentEvent("thinking", {"message": "Processing your request..."})

        tool_defs = self._get_tool_definitions()

        external_rounds = 0  # only count rounds with real (non-plan) tool calls

        max_rounds = self._max_tool_rounds or self.DEFAULT_MAX_TOOL_ROUNDS

        for round_num in range(max_rounds):
            messages = await self._conversation.build_messages()

            # Inject system prompt
            system_prompt = self._build_system_prompt()
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] = system_prompt
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})

            try:
                response = await self._llm.complete(messages, tools=tool_defs or None)
            except Exception as e:
                yield AgentEvent("error", {"message": f"LLM error: {e}"})
                return

            # If there's text content, emit it
            if response.content:
                yield AgentEvent("text", {"content": response.content})

            # If no tool calls, we're done
            if not response.tool_calls:
                await self._conversation.add_assistant_message(content=response.content)
                yield AgentEvent("done", {})
                return

            # Track whether this round has any external (non-plan, non-memory) tool calls
            has_external_call = any(
                tc.name not in ("plan", "memory") for tc in response.tool_calls
            )
            if has_external_call:
                external_rounds += 1
                self._rounds_since_checkpoint += 1

            # Auto-checkpoint periodically
            if self._rounds_since_checkpoint >= self._checkpoint_interval:
                await self._auto_checkpoint()
                self._rounds_since_checkpoint = 0

            # Process tool calls — store content and tool_calls together
            tool_call_dicts = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in response.tool_calls
            ]
            await self._conversation.add_assistant_message(
                content=response.content, tool_calls=tool_call_dicts
            )

            for tc in response.tool_calls:
                yield AgentEvent(
                    "tool_call",
                    {"id": tc.id, "tool": tc.name, "arguments": tc.arguments},
                )

                # Internal tools (plan, memory) bypass guardrails entirely —
                # they're bookkeeping tools that don't affect the system.
                _INTERNAL_TOOLS = {"plan", "memory"}

                if tc.name not in _INTERNAL_TOOLS:
                    # Check guardrails for external tools
                    operation = tc.arguments.get("operation")
                    decision = self._guardrails.check(tc.name, operation, tc.arguments)

                    if not decision.allowed:
                        result_text = f"[DENIED] {decision.reason}"
                        yield AgentEvent(
                            "tool_result",
                            {"id": tc.id, "tool": tc.name, "result": result_text, "denied": True},
                        )
                        await self._conversation.add_tool_result(tc.id, result_text)
                        continue

                if tc.name not in _INTERNAL_TOOLS and decision.requires_approval:
                    yield AgentEvent(
                        "tool_approval_needed",
                        {
                            "tool": tc.name,
                            "arguments": tc.arguments,
                            "reason": decision.reason,
                        },
                    )

                    approved = await self._guardrails.request_approval(
                        tc.name, operation, tc.arguments, decision.reason
                    )

                    if not approved:
                        result_text = "[REJECTED] User declined the action."
                        yield AgentEvent(
                            "tool_result",
                            {
                                "id": tc.id,
                                "tool": tc.name,
                                "result": result_text,
                                "denied": True,
                            },
                        )
                        await self._conversation.add_tool_result(tc.id, result_text)
                        continue

                # Execute the tool (plan tool handled internally)
                try:
                    if tc.name == "plan":
                        result = await self._handle_plan_tool(tc.arguments)
                        result_text = str(result)
                        # Emit plan update event for UI
                        await self._emit(AgentEvent("plan_update", {"result": result_text}))
                    else:
                        result = await self._execute_tool(tc.name, tc.arguments)
                        result_text = str(result)
                except Exception as e:
                    result_text = f"[ERROR] Tool execution failed: {e}"
                    logger.exception(f"Tool {tc.name} failed")

                yield AgentEvent(
                    "tool_result",
                    {"id": tc.id, "tool": tc.name, "result": result_text},
                )
                await self._conversation.add_tool_result(tc.id, result_text)

        # If we exhausted all rounds, save a checkpoint before stopping
        await self._auto_checkpoint()

        yield AgentEvent(
            "error",
            {"message": f"Reached maximum tool rounds ({max_rounds}). Stopping."},
        )
        yield AgentEvent("done", {})

    async def _execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool via the registry."""
        if not self._tool_registry:
            return "[ERROR] No tools registered"

        tool = self._tool_registry.get(tool_name)
        if not tool:
            return f"[ERROR] Unknown tool: {tool_name}"

        return await tool.execute(**arguments)

    async def _handle_plan_tool(self, arguments: dict[str, Any]) -> str:
        """Handle the built-in plan tool."""
        action = arguments.get("action", "get")
        conv_id = self._conversation.conversation_id

        if action == "create":
            title = arguments.get("title", "Untitled Plan")
            steps = arguments.get("steps", [])
            goal = arguments.get("goal")
            plan = await self._planner.create_plan(
                title=title, steps=steps, goal=goal, conversation_id=conv_id
            )

            # Also save the goal to persistent memory
            if goal and conv_id:
                await self._memory.add_goal(
                    description=goal,
                    conversation_id=conv_id,
                    priority=10,
                )

            return json.dumps({"created": plan["id"], "title": title, "steps": len(steps)})

        elif action == "update_step":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "[ERROR] No active plan to update."
            step_index = arguments.get("step_index", 0)
            status = arguments.get("status", "done")
            result = arguments.get("result")
            updated = await self._planner.update_step(plan["id"], step_index, status, result)
            if not updated:
                return f"[ERROR] Could not update step {step_index}."
            return json.dumps({
                "plan": updated["id"],
                "step": step_index,
                "status": status,
                "plan_status": updated["status"],
            })

        elif action == "get":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "No active plan."
            return self._planner.format_plan_for_context(plan)

        elif action == "complete":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "No active plan to complete."
            await self._planner.set_plan_status(plan["id"], "completed")

            # Also mark the associated goal as completed
            if conv_id:
                goals = await self._memory.get_active_goals(conv_id)
                for g in goals:
                    if g.get("description") == plan.get("goal"):
                        await self._memory.update_goal_status(g["id"], "completed")

            return f"Plan '{plan['title']}' marked as completed."

        elif action == "cancel":
            plan = await self._planner.get_active_plan(conv_id)
            if not plan:
                return "No active plan to cancel."
            await self._planner.set_plan_status(plan["id"], "cancelled")
            return f"Plan '{plan['title']}' cancelled."

        return f"[ERROR] Unknown plan action: {action}"

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions from the registry for LLM function calling.

        Tool ordering matters for LLM attention:
          1. pc (primary computer control)
          2. plan (task tracking — high priority)
          3. memory (persistent facts and goals)
          4. everything else
        """
        defs: list[ToolDefinition] = []

        if self._tool_registry:
            all_defs = self._tool_registry.get_definitions()
            pc_defs = [d for d in all_defs if d.name == "pc"]
            memory_defs = [d for d in all_defs if d.name == "memory"]
            other_defs = [d for d in all_defs if d.name not in ("pc", "memory")]

            # pc first
            defs.extend(pc_defs)

            # plan second (built-in, not in registry)
            if self._config.planner.enabled:
                defs.append(PLAN_TOOL_DEF)

            # memory third
            defs.extend(memory_defs)

            # everything else
            defs.extend(other_defs)
        else:
            # No registry — just add plan if enabled
            if self._config.planner.enabled:
                defs.append(PLAN_TOOL_DEF)

        return defs
