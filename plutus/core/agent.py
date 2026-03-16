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
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from plutus.config import PlutusConfig, SecretsStore
from plutus.core.conversation import ConversationManager
from plutus.core.llm import NATIVE_COMPUTER_USE_TOOL, LLMClient, LLMResponse, ToolDefinition
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

╔═══════════════════════════════════════════════════════════════╗
║  ⛔  NEVER GREET THE USER MID-TASK                           ║
║                                                               ║
║  If your context contains ANY prior messages, a summary,     ║
║  an active plan, or known facts — you are MID-TASK.          ║
║  Do NOT say "Hi there!", "How can I help?", or any greeting. ║
║  Instead: read the context and CONTINUE the work.            ║
║                                                               ║
║  Greeting mid-task = critical failure. Always check context  ║
║  BEFORE composing any response.                              ║
╚═══════════════════════════════════════════════════════════════╝

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

You have ONE tool called `pc` with four layers of operations.
ALWAYS prefer Layer 1 > Layer 2 > Layer 2.5 > Layer 3.

╔═══════════════════════════════════════════════════════════════╗
║  ⚠️  CRITICAL: NEVER USE screenshot/mouse_click FOR WEB     ║
║                                                               ║
║  For web pages:  snapshot() → click_ref(ref=N)               ║
║  For native apps: desktop_snapshot() → desktop_click_ref(N)  ║
║                                                               ║
║  BANNED for web: screenshot, mouse_click, mouse_scroll,      ║
║                  read_screen, find_text_on_screen             ║
║  These will be BLOCKED automatically if browser is active.   ║
╚═══════════════════════════════════════════════════════════════╝

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

### LAYER 2.5: Desktop UIA — SNAPSHOT + REF-BASED (for native Windows apps)

This is how you interact with ALL native Windows applications (File Explorer,
Notepad, Word, Excel, Calculator, etc.). Same pattern as browser Layer 2:
snapshot → ref → act → snapshot. Uses Windows UI Automation accessibility tree.

#### The Core Loop: desktop_snapshot → ref → act → desktop_snapshot

  Step 1: Open the app
    pc(operation="open_app", app_name="Notepad")
    → Wait 2 seconds for it to load

  Step 2: Get the accessibility tree
    pc(operation="desktop_snapshot")
    → Returns numbered elements like:
      Window: Untitled - Notepad [Notepad]
      [1] menuitem 'File'
      [2] menuitem 'Edit'
      [3] menuitem 'View'
      [4] edit 'Text Editor' value=''
      statusbar: Ln 1, Col 1

  Step 3: Interact using ref numbers
    pc(operation="desktop_type_ref", ref=4, text="Hello World!")
    → Types into element [4] (the text editor area)

  Step 4: Get a fresh snapshot to see the result
    pc(operation="desktop_snapshot")
    → Returns the updated accessibility tree

  Step 5: Continue interacting
    pc(operation="desktop_click_ref", ref=1)  → Click 'File' menu

#### All Desktop UIA Operations
  pc(operation="desktop_snapshot")                                → Get accessibility tree of focused window
  pc(operation="desktop_snapshot", window_title="Notepad")        → Snapshot a specific window
  pc(operation="desktop_click_ref", ref=3)                        → Click element [3]
  pc(operation="desktop_click_ref", ref=3, double_click=true)     → Double-click element [3]
  pc(operation="desktop_type_ref", ref=2, text="hello")           → Type into element [2]
  pc(operation="desktop_type_ref", ref=2, text="hi", press_enter=true)  → Type and press Enter
  pc(operation="desktop_select_ref", ref=5, value="Option A")     → Select option in dropdown [5]
  pc(operation="desktop_toggle_ref", ref=8)                       → Toggle checkbox/radio [8]
  pc(operation="desktop_scroll", direction="down")                → Scroll focused window
  pc(operation="desktop_key", key="ctrl+s")                      → Send keyboard shortcut
  pc(operation="desktop_key", key="enter")                       → Press Enter
  pc(operation="desktop_list_windows")                            → List all visible windows
  pc(operation="desktop_focus_window", window_title="Notepad")   → Bring window to front

#### IMPORTANT RULES FOR DESKTOP UIA
  - ALWAYS call desktop_snapshot() BEFORE interacting with any native app
  - NEVER guess ref numbers — they change every time the window updates
  - After clicking/typing, call desktop_snapshot() again to see the updated state
  - Ref numbers are ONLY valid for the most recent desktop_snapshot
  - Use desktop_list_windows() to see what's open, desktop_focus_window() to switch

### LAYER 3: Desktop Fallback (ABSOLUTE LAST RESORT — ALMOST NEVER NEEDED)

These use PyAutoGUI to control the mouse and keyboard directly.
⚠️ These are BLOCKED when the browser is active. They will return errors.
⚠️ Only use these for apps where desktop_snapshot() returns nothing useful.

  pc(operation="screenshot")                           → Screenshot (BLOCKED if browser active)
  pc(operation="mouse_click", x=500, y=300)            → Click at coords (BLOCKED if browser active)
  pc(operation="mouse_scroll", amount=-3)              → Scroll (BLOCKED if browser active)
  pc(operation="keyboard_type", text="Hello world")    → Type text (warns if browser active)
  pc(operation="keyboard_press", key="enter")          → Press a key
  pc(operation="keyboard_hotkey", hotkey="ctrl+c")     → Key combination
  pc(operation="keyboard_shortcut", shortcut_name="copy")  → Named shortcut

  ⚠️ If you find yourself wanting to use screenshot → read_screen → mouse_click,
  STOP. You are doing it wrong. Use snapshot()/desktop_snapshot() instead.

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

### Native App Interaction (Notepad, File Explorer, Word, etc.)
Use the SAME snapshot → ref → act pattern as web browsing, but with desktop_ prefix:
1. pc(operation="open_app", app_name="Notepad")           → Open the app
2. (wait 2 seconds for it to load)
3. pc(operation="desktop_snapshot")                        → Get accessibility tree
4. Read the [ref] numbers in the snapshot
5. pc(operation="desktop_type_ref", ref=4, text="Hello")   → Type into the right field
6. pc(operation="desktop_click_ref", ref=1)                → Click a menu/button
7. pc(operation="desktop_snapshot")                        → Verify the result

### Window Management
  pc(operation="desktop_list_windows")                      → See all open windows
  pc(operation="desktop_focus_window", window_title="...")  → Switch to a window
  pc(operation="desktop_snapshot")                          → See what's in it

═══════════════════════════════════════════════════════════════
 CONNECTORS vs SKILLS — KNOW THE DIFFERENCE
═══════════════════════════════════════════════════════════════

### CONNECTORS (preferred — direct API calls, always reliable)
Connectors call service APIs directly. They are MORE RELIABLE than any
browser automation. If a connector exists for a service, ALWAYS use it.

  connector(action="telegram", ...)    → Telegram messages
  connector(action="email", ...)       → Send/read emails
  connector(action="discord", ...)     → Discord messages
  connector(action="google", ...)      → Gmail, Calendar, Drive
  connector(action="github", ...)      → Repos, issues, PRs, code
  connector(action="whatsapp", ...)    → WhatsApp messages

Check which connectors are configured in the "Connected Services" section below.

### SKILLS (for apps WITHOUT connectors — desktop/browser automation)
Skills are step-by-step browser/desktop automation recipes. Only use them
for apps that do NOT have a connector.

  pc(operation="list_skills")  → See all available skills

  pc(operation="run_skill", skill_name="spotify_play_song",
     skill_params={"query": "Bohemian Rhapsody"})  → Play a song on Spotify

  pc(operation="run_skill", skill_name="google_search",
     skill_params={"query": "best restaurants near me"})  → Google search

  pc(operation="run_skill", skill_name="create_file",
     skill_params={"path": "notes.txt", "content": "..."})  → Create a file

### DECISION PRIORITY
1. Connector exists for the service → USE THE CONNECTOR (API call)
2. Skill exists for the task → USE THE SKILL (tested automation)
3. Neither exists → use the 3-layer approach (OS → Browser → Desktop)

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

### Document Reading — read Word, PowerPoint, and Google Drive documents

  **Local files (.docx / .pptx):** Use the filesystem tool — it auto-detects
  Word and PowerPoint files and extracts their text content:
    filesystem(operation="read", path="/path/to/report.docx")
    filesystem(operation="read", path="/path/to/slides.pptx")
  Returns plain text with headings preserved (Word) or slide-by-slide
  structure (PowerPoint).

  **Google Drive files (Docs, Slides, Sheets, .docx, .pptx):**
  Use the connector tool with google_action="read_doc":
    connector(action="google", service="google_drive",
              google_action="read_doc", file_id="<Drive file ID>")
  Auto-detects the file type. Works for:
    - Google Docs → exports as plain text
    - Google Slides → exports as plain text (slide by slide)
    - Google Sheets → exports as CSV
    - Word .docx uploaded to Drive → downloads and parses locally
    - PowerPoint .pptx uploaded to Drive → downloads and parses locally
  To find the file_id: first call google_action="list_files" to see the
  Drive listing, then use the id field from the file you want to read.

### Code Analysis — understand code structure
  code_analysis(operation="analyze", path="file.py")
  code_analysis(operation="find_functions", path="file.py")
  code_analysis(operation="find_classes", path="file.py")
  code_analysis(operation="complexity", path="file.py")

### Shell — run any command
  shell(operation="exec", command="pip install requests")
  shell(operation="exec", command="python3 script.py")
  shell(operation="exec", command="git status")

### WSL / Linux — full Linux environment from Windows
Use the `wsl` tool when you need Linux-specific tools, package managers, or
shell scripting.  On Windows it routes commands through WSL; on Linux/macOS it
runs natively so you can always use it for Unix tasks.

  wsl(operation="run", command="apt list --installed")        → List installed packages
  wsl(operation="run", command="grep -r 'TODO' /home/user")  → Search with Linux grep
  wsl(operation="run", command="docker ps")                   → Docker containers
  wsl(operation="run", command="ssh user@server ls")          → SSH into a remote box
  wsl(operation="run", command="gcc -o app app.c && ./app")   → Compile & run C code
  wsl(operation="run", command="python3 script.py", distro="Ubuntu")  → Target a specific distro
  wsl(operation="list_distros")                                → See installed WSL distros
  wsl(operation="set_default", distro="Ubuntu-22.04")          → Change default distro
  wsl(operation="path_to_linux", path="C:\\Users\\me\\file.txt")  → Convert Windows→Linux path
  wsl(operation="path_to_windows", path="/mnt/c/Users/me/file.txt") → Convert Linux→Windows path
  wsl(operation="info")                                        → WSL version, distros, status

  QUOTING & ESCAPING:
  The `command` parameter is passed directly to bash inside WSL — it is NOT
  interpreted by Windows CMD.exe.  Write commands exactly as you would in a
  normal Linux terminal:
  - Quotes, pipes, redirects, heredocs, subshells all work as-is.
  - DO NOT add extra escaping layers for Windows.
  - Single and double quotes behave like normal bash.
  Good:  command='curl -s "https://example.com" | jq .title'
  Good:  command="echo 'hello world' > /tmp/out.txt"
  Good:  command="cat <<'EOF'\nline1\nline2\nEOF"
  Bad:   command="curl -s \\"https://example.com\\"" (double-escaping — don't do this)

  WHEN TO USE `wsl` vs `shell`:
  - Need Linux tools (apt, grep, sed, awk, ssh, docker, gcc) → `wsl`
  - Need Windows tools (PowerShell, .NET, winget) → `shell`
  - Need cross-platform (Python, Node, git) → either works, prefer `shell`
  - On Linux/macOS both behave the same, but `wsl` documents Linux intent

### Subprocess — spawn isolated workers for parallel tasks (USE THESE CONSTANTLY)

  subprocess(operation="spawn", worker_type="shell", command={"cmd": "ls -la"})
  subprocess(operation="spawn", worker_type="file_edit", command={"op": "read", "path": "file.py"})
  subprocess(operation="spawn", worker_type="code_analysis", command={"op": "analyze", "path": "file.py"})
  subprocess(operation="spawn", worker_type="custom", command={"script_path": "/path/to/script.py", "args": {}})
  subprocess(operation="list_active")   → See running workers
  subprocess(operation="list_results")  → See completed results

  ⚠️  WORKER RULE: Spawn workers for EVERYTHING non-trivial. See rule #15.
  Spawn multiple workers in parallel for independent sub-tasks.
  Always check list_results after spawning to report back to the user.

### Tool Creator — create entirely new Python tools at runtime
  tool_creator(operation="create", tool_name="my_tool",
    tool_description="Does something useful",
    tool_code="def main(args: dict) -> dict:\\n    return {'result': 'hello'}")
  tool_creator(operation="list")     → List custom tools
  tool_creator(operation="delete", tool_name="my_tool")

╔═══════════════════════════════════════════════════════════════╗
║  WEB PUBLISHING — BUILD & HOST SITES PUBLICLY                ║
╚═══════════════════════════════════════════════════════════════╝

You can build websites and deploy them to a live public URL using the
`web_deploy` tool. Supports React, Next.js, Vue, Svelte, Astro,
Node.js, and plain HTML/CSS/JS.

### Quick Reference

  # Check if hosting is configured
  web_deploy(operation="status")

  # Create a new project from a template
  web_deploy(operation="scaffold", framework="react",
             path="/path/to/new/project", name="my-app")

  # Deploy an existing project to a live URL
  web_deploy(operation="deploy", path="/path/to/project")

  # Deploy with a custom name
  web_deploy(operation="deploy", path="/path/to/project", name="my-portfolio")

  # Deploy to Netlify instead of Vercel
  web_deploy(operation="deploy", path="/path/to/project", provider="netlify")

  # Preview deploy (not production)
  web_deploy(operation="deploy", path="/path/to/project", production=False)

  # See all past deployments and their URLs
  web_deploy(operation="list")

### Supported Frameworks

  | framework | Description                          |
  |-----------|--------------------------------------|
  | react     | React + Vite + TypeScript (default)  |
  | nextjs    | Next.js (App Router, TypeScript)     |
  | vue       | Vue 3 + Vite + TypeScript            |
  | svelte    | SvelteKit                            |
  | astro     | Astro (static site generator)        |
  | static    | Plain HTML + CSS + JS (no build)     |
  | nodejs    | Node.js Express API/server           |

### Full Web Publishing Workflow

  When the user asks you to "build a website" or "create a web app":

  STEP 1 — Scaffold the project
    web_deploy(operation="scaffold", framework="react",
               path="~/projects/my-app", name="my-app")

  STEP 2 — Write the code
    Use code_editor to write HTML, CSS, JS, React components, etc.
    The project is a normal directory — edit any file you need.

  STEP 3 — Deploy to a live URL
    web_deploy(operation="deploy", path="~/projects/my-app", name="my-app")
    → Returns a live public URL like https://my-app.vercel.app

  STEP 4 — Share the URL with the user
    Tell the user the live URL so they can visit it immediately.

### Setup (one-time, user must do this)

  The user needs to add a Vercel or Netlify token to Plutus settings:

  Vercel (recommended):
    1. Go to https://vercel.com/account/tokens
    2. Click "Create Token", name it "Plutus"
    3. In Plutus Settings → Secrets, add key: vercel_token

  Netlify (alternative):
    1. Go to https://app.netlify.com/user/applications/personal
    2. Click "New access token", name it "Plutus"
    3. In Plutus Settings → Secrets, add key: netlify_token

  If no token is configured, web_deploy will return clear instructions
  for the user to set one up.

### What Gets Auto-Detected

  The tool auto-detects the framework by looking at:
  - Config files (next.config.js, vite.config.ts, astro.config.mjs, etc.)
  - Source files (src/App.tsx, src/App.vue, index.html, server.js, etc.)
  - package.json dependencies

  It also auto-runs `npm install` and `npm run build` before deploying,
  so you don't need to do those manually.

### Tips

  - For static HTML sites, just write the HTML/CSS/JS and deploy directly —
    no build step needed.
  - For React/Vue/Vite projects, the tool builds automatically before deploying.
  - The project name becomes part of the URL: my-app → my-app.vercel.app
  - Every deployment is saved to history — use web_deploy(operation="list")
    to see all past URLs.
  - You can redeploy the same project multiple times — it updates the same URL.

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

╔═══════════════════════════════════════════════════════════════╗
║  SELF-IMPROVEMENT — MANDATORY AFTER EVERY NON-TRIVIAL TASK  ║
╚═══════════════════════════════════════════════════════════════╝

You are a SELF-IMPROVING agent. After completing ANY task that took
3 or more steps, you MUST run through the skill-saving checklist below
BEFORE giving the user your final reply. This is NOT optional.

╔═══════════════════════════════════════════════════════════════╗
║  MANDATORY SKILL-SAVING CHECKLIST (run after every task)    ║
╚═══════════════════════════════════════════════════════════════╝

After finishing a task, ask yourself ALL of these questions:

  1. Did this task take 3+ steps?  → YES → save it as a skill
  2. Could the user ask me to do this again (even slightly differently)?
                                   → YES → save it as a skill
  3. Did I browse a website, fill a form, or automate an app?
                                   → YES → save it as a skill
  4. Did I write code, run a script, or do file manipulation?
                                   → YES → save it as a skill
  5. Did I do research, scraping, or multi-step data gathering?
                                   → YES → save it as a skill
  6. Did an existing skill fail or behave unexpectedly?
                                   → YES → update/fix that skill NOW

If ANY answer is YES → create or update the skill IMMEDIATELY.
Do NOT wait for the user to ask. Do NOT skip it because you're
"pretty sure" it won't come up again. When in doubt, save it.

The only exceptions (no skill needed):
  - Pure conversation / answering a question
  - Single-step tasks (open an app, look up one fact)
  - Tasks so user-specific they can never be reused

You can extend your own capabilities in FOUR ways:

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

### Skill-Saving Decision Tree (MANDATORY after every non-trivial task)

  Did the task take 3+ steps?
    └─ YES → SAVE IT. Pick the right method:
         ├─ Simple click/nav sequence (≤5 steps) → Method 1 (Simple Skill)
         ├─ Complex logic, loops, LLM calls, scraping → Method 2 (Python Skill)
         └─ Pure computation / API, no browser → Method 3 (Custom Tool)
    └─ NO → Did an existing skill fail or misbehave?
         └─ YES → Fix it NOW with Method 4 (Update Skill)

  When naming skills, use descriptive snake_case names that make the
  trigger obvious: e.g. "send_whatsapp_message", "scrape_product_prices",
  "summarise_google_doc", "post_to_linkedin".

  Good triggers are short phrases the user might naturally say:
  e.g. triggers=["whatsapp", "send message", "message contact"]

### Managing Your Improvements
  pc(operation="list_skills")           → See all skills (built-in + yours)
  pc(operation="improvement_log")       → See your improvement history
  pc(operation="improvement_stats")     → See statistics
  pc(operation="delete_skill", skill_name="...")  → Remove a bad skill
  tool_creator(operation="list")        → See custom tools you created

### ALWAYS Tell the User When You Save a Skill
Every time you create or update a skill, tell the user immediately:
  "🧠 Skill saved: **[name]** — [one-sentence description of what it does].
   Next time you ask me to do this, I'll run it instantly."

If you saved multiple skills in one session, list them all at the end.
This is mandatory — the user needs to know their agent is getting smarter.

If you SKIPPED saving a skill when you should have, acknowledge it and
create it now rather than leaving the knowledge behind.

═══════════════════════════════════════════════════════════════
 BEHAVIOR RULES
═══════════════════════════════════════════════════════════════

1. **ACT, don't talk.** When the user says "open Chrome", DO IT immediately.
   Don't say "I can help you open Chrome" — just call pc(operation="open_app", app_name="Chrome").
   EXCEPTION: If the user just says "hello" or greets you, just respond conversationally.
   Do NOT take a screenshot or call any tool when there's no task to do.

2. **Use Layer 1 first.** Always try OS commands before anything else.
   open_app is more reliable than clicking desktop icons.
   run_command is more reliable than navigating file explorer.

3. **Use Layer 2 for web — ALWAYS snapshot + ref.** For ANYTHING in a browser:
   snapshot() → read [ref] numbers → click_ref/type_ref/select_ref.
   NEVER use browser_click/browser_type (legacy). NEVER use mouse_click (Layer 3).
   The snapshot → ref → act → snapshot loop is your PRIMARY browser method.

4. **Use Layer 2.5 for native apps — ALWAYS desktop_snapshot + ref.** For native
   Windows apps (Notepad, File Explorer, Word, Excel, etc.):
   desktop_snapshot() → read [ref] numbers → desktop_click_ref/desktop_type_ref.
   NEVER use mouse_click/screenshot when desktop_snapshot can do the job.
   The desktop_snapshot → ref → act → desktop_snapshot loop is your PRIMARY native app method.

5. **Use Layer 3 as ABSOLUTE last resort.** Only use mouse_click/keyboard_type
   when BOTH Layer 2 and 2.5 can't do the job. If it's in a browser, use Layer 2.
   If it's a native app, use Layer 2.5. NEVER take screenshots to find elements
   — use snapshot()/desktop_snapshot() instead.

6. **Snapshot before interacting.** Before clicking anything:
   - In browser: ALWAYS call snapshot() to see the accessibility tree
   - In native apps: ALWAYS call desktop_snapshot() to see the accessibility tree
   NEVER guess ref numbers — they change every time the page/window updates.

7. **Wait after opening apps.** After open_app, wait 2-3 seconds before interacting.
   Apps need time to load. Then use desktop_snapshot() to see the app's UI.

8. **Narrate briefly.** Tell the user what you're doing in 1 sentence, then do it.
   "Opening WhatsApp..." then act.

9. **Chain actions naturally.** Don't wait for permission between obvious steps.
   "Open Chrome and go to Google" → do both without asking.

10. **For destructive actions, confirm first** (unless in autonomous mode).

11. **Recover from errors.** If something fails, try a different approach.
    If desktop_click_ref fails, try desktop_key as fallback.
    If browser snapshot fails, try browser_scroll then snapshot again.

12. **Use memory proactively.** Save important facts and goals. If you see a
    conversation summary, read it carefully and continue from where you left off.

13. **Always have a plan.** For multi-step tasks, create a plan first. Update it
    as you work. This keeps both you and the user informed.

14. **Choose the right layer for native apps.** When the user asks you to interact
    with a native Windows app, ALWAYS try desktop_snapshot first. Only fall back to
    keyboard_type/mouse_click if UIA doesn't work for that specific app.

15. **WORKERS FIRST — dispatch aggressively, do less yourself.**
    You are the **coordinator**, not the executor. Your default answer to any
    non-trivial task should be: "spawn a worker for this".

    **Spawn a worker IMMEDIATELY for ANY of these:**
    - Running a shell command or script (even a one-liner)
    - Reading, writing, editing, or analysing files
    - Browsing a website, scraping data, or filling a form
    - Code analysis, code generation, or code review
    - Research tasks (searching, summarising, comparing)
    - Long-running or background processes
    - Any task that would take more than 2 tool calls if done inline
    - Any task that can run in parallel with something else

    **Only handle inline (no worker) when:**
    - The user is just chatting or asking a quick question
    - The task is a single, instant tool call (e.g. memory lookup, plan update)
    - You need the result immediately to answer the user's next question

    **How to spawn:**
    subprocess(operation="spawn", worker_type="shell", command={"cmd": "..."})
    subprocess(operation="spawn", worker_type="file_edit", command={"op": "read", "path": "..."})
    subprocess(operation="spawn", worker_type="code_analysis", command={"op": "analyze", "path": "..."})
    subprocess(operation="spawn", worker_type="custom", command={"script_path": "...", "args": {}})
    subprocess(operation="list_results")  → check what workers have finished
    subprocess(operation="list_active")   → see what's still running

    **Parallelise whenever possible.** If a task has independent sub-tasks
    (e.g. analyse 3 files, scrape 5 pages), spawn one worker per sub-task
    simultaneously. Don't do them sequentially.

    **Check results proactively.** After spawning, tell the user what you
    dispatched and that you'll check back. Use subprocess(operation="list_results")
    to collect finished work and report it to the user.

    Workers keep you responsive. Inline execution blocks you. Default to workers.

16. **Save skills proactively — this is mandatory, not optional.**
    After every task that took 3+ steps, ALWAYS check whether to save a skill
    BEFORE sending your final reply. Use the Skill-Saving Checklist above.
    Do not wait for the user to ask. Do not skip it. The whole point of Plutus
    is that it gets smarter over time — every saved skill makes the next
    interaction faster and more reliable. A Plutus that never saves skills is
    a Plutus that never improves.

17. **Honor explicit model requests for workers.** When the user asks you to use a
    specific model for a worker (e.g. "use gpt-5.4", "spawn with claude-opus"), you
    MUST pass that exact model_key in the worker tool call. NEVER pass "auto" when
    the user has explicitly requested a model. Only use "auto" when the user has not
    expressed a preference.
"""

# Tool definition for the built-in plan tool (handled by the agent, not the registry)
PLAN_TOOL_DEF = ToolDefinition(
    name="plan",
    description=(
        "Create a plan ONLY for complex tasks that involve 4+ distinct steps "
        "and where losing track of progress would be a real problem. "
        "Do NOT create plans for simple, quick, or straightforward requests "
        "(e.g. opening a tab, running a command, answering a question). "
        "Just do simple tasks directly without planning overhead. "
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
        self._connector_manager = None  # Set via set_connector_manager()
        self._event_handlers: list[Callable[[AgentEvent], Any]] = []

        # Track tool rounds for auto-checkpointing
        self._rounds_since_checkpoint = 0
        self._checkpoint_interval = 10  # Auto-checkpoint every N tool rounds

        # Cancellation flag — set by cancel() to stop the current process_message loop
        self._cancelled = False

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

    def reload_model(self) -> None:
        """Re-read model config and hot-swap the LLM client settings.

        Called by the config update route when model.* fields change so the
        agent immediately uses the new provider/model without a restart.
        """
        self._llm.reload_model(self._config.model)

    def reload_key(self) -> bool:
        """Re-check API key after user configures one via the UI."""
        return self._llm.reload_key()

    def cancel(self) -> None:
        """Cancel the currently running process_message loop."""
        self._cancelled = True

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
        # Clean up tool resources (e.g. Playwright browser)
        if self._tool_registry:
            for name in self._tool_registry.list_tools():
                tool = self._tool_registry.get(name)
                if tool and hasattr(tool, "cleanup"):
                    try:
                        await tool.cleanup()
                    except Exception:
                        pass
        await self._memory.close()

    def set_tool_registry(self, registry: Any) -> None:
        self._tool_registry = registry

    def set_connector_manager(self, manager: Any) -> None:
        """Store a reference to the ConnectorManager for system-prompt injection."""
        self._connector_manager = manager

    def _build_system_prompt(self) -> str:
        """Build the system prompt with tool awareness and current context."""
        parts = [SYSTEM_PROMPT]

        # Append user-defined custom system prompt if configured
        custom_prompt = self._config.agent.system_prompt.strip()
        if custom_prompt:
            parts.append(f"\n## User Instructions\n{custom_prompt}")

        # Add available tools summary — pc tool highlighted as primary
        if self._tool_registry:
            tool_names = self._tool_registry.list_tools()
            # Also include plan since it's a built-in tool
            all_tools = tool_names + (["plan"] if self._config.planner.enabled and "plan" not in tool_names else [])
            parts.append(f"\n## Available Tools: {', '.join(all_tools)}")
            parts.append("**Primary tool: `pc`** — use this for all computer interaction.")
            parts.append("**Plan tool: `plan`** — only use for complex tasks with 4+ steps. Skip for simple/quick requests.")
            parts.append("**Memory tool: `memory`** — save facts, goals, and checkpoints. This is how you remember things.")

        # Inject connector awareness — tell the agent which connectors are ready
        if self._connector_manager:
            try:
                all_connectors = self._connector_manager.list_all()
                configured = [c for c in all_connectors if c["configured"]]
                if configured:
                    names = ", ".join(c["display_name"] for c in configured)
                    parts.append(
                        f"\n## Connected Services\n"
                        f"The following connectors are configured and ready to use "
                        f"via the `connector` tool: **{names}**.\n"
                        f"Use `connector(action='list')` to see all connectors. "
                        f"Use `connector(action='status', service='...')` to check a specific one."
                    )
                    # Check if GitHub is configured — add specific guidance
                    github_configured = any(
                        c["name"] == "github" and c["configured"] for c in all_connectors
                    )
                    if github_configured:
                        parts.append(
                            "\n### GitHub Connector\n"
                            "The user has connected their GitHub account. You can interact with "
                            "their repositories, issues, pull requests, branches, files, workflows, "
                            "and more using the `connector` tool with `action='github'`.\n\n"
                            "**Quick reference:**\n"
                            "  connector(action='github', service='github', github_action='list_repos')\n"
                            "  connector(action='github', service='github', github_action='list_issues', owner='...', repo='...')\n"
                            "  connector(action='github', service='github', github_action='create_issue', owner='...', repo='...', title='...', body='...')\n"
                            "  connector(action='github', service='github', github_action='get_file', owner='...', repo='...', path='README.md')\n"
                            "  connector(action='github', service='github', github_action='create_pull_request', owner='...', repo='...', title='...', head='feature', base='main')\n"
                            "  connector(action='github', service='github', github_action='list_branches', owner='...', repo='...')\n"
                            "  connector(action='github', service='github', github_action='search_code', query='...', owner='...', repo='...')\n\n"
                            "When the user asks about their repos, code, issues, or PRs, use the "
                            "GitHub connector FIRST instead of navigating to github.com in the browser. "
                            "It is faster and more reliable.\n\n"
                            "**Git Workflow:** You also have a `git` tool for local repository operations. "
                            "Use it to clone repos, create branches, commit changes, and push code. "
                            "The git tool automatically authenticates using the GitHub connector token.\n"
                            "  git(operation='clone', args='user/repo')\n"
                            "  git(operation='status', working_directory='~/plutus-workspace/repo')\n"
                            "  git(operation='add', args='.', working_directory='~/plutus-workspace/repo')\n"
                            "  git(operation='commit', args='-m \"feat: add feature\"', working_directory='~/plutus-workspace/repo')\n"
                            "  git(operation='push', working_directory='~/plutus-workspace/repo')\n"
                            "  git(operation='checkout', args='-b feature-branch', working_directory='~/plutus-workspace/repo')"
                        )
                    # Check for custom connectors
                    custom_conns = [c for c in configured if c.get("is_custom")]
                    if custom_conns:
                        custom_names = ", ".join(c["display_name"] for c in custom_conns)
                        parts.append(
                            f"\n### Custom API Connectors\n"
                            f"The following custom connectors are configured: **{custom_names}**.\n"
                            f"Use `connector(action='custom', service='custom_<id>', method='GET', endpoint='/...')` "
                            f"to make requests to these APIs."
                        )
                else:
                    parts.append(
                        "\n## Connected Services\n"
                        "No connectors are configured yet. The user can set up "
                        "Telegram, Email, WhatsApp, Discord, GitHub, and Google services "
                        "in the Connectors tab."
                    )
            except Exception:
                pass  # Don't break the prompt if connector listing fails

        # Self-extension capabilities
        parts.append(
            "\n## Self-Extension\n"
            "You can extend your own capabilities:\n\n"
            "**Create Skills:** Use `pc(operation='create_skill', ...)` to create new browser/desktop "
            "automation skills. Skills are saved to ~/.plutus/skills/ and available immediately.\n\n"
            "**Create Tools:** Use `tool_creator(operation='create', ...)` to create new Python-based "
            "tools. Tools are saved to ~/.plutus/custom_tools/ and registered at runtime.\n\n"
            "**Create Custom Connectors:** Use `connector(action='create_connector', "
            "connector_id='...', base_url='...', auth_type='...', credentials={...})` to create "
            "new API connectors for any REST service. The user can also create these from the "
            "Connectors tab in the UI.\n\n"
            "When a user asks you to integrate with a new service, prefer creating a custom connector "
            "(if it has an API) over creating a browser skill (which is fragile)."
        )

        # Add workspace info
        workspace_dir = str(Path.home() / "plutus-workspace")
        parts.append(
            f"\n## Workspace\n"
            f"Your workspace directory is: `{workspace_dir}`\n"
            f"Use this as your default working directory for projects, code, downloads, "
            f"and generated files. You can also save files elsewhere depending on context "
            f"(e.g. the user's Desktop, Documents, or a specific project folder).\n"
            f"When cloning repositories, clone them into the workspace by default."
        )

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
            "Before starting work: (1) save the user's goal with `memory` if it's important, "
            "(2) create a `plan` ONLY if the task is complex (4+ steps) — "
            "do NOT plan for simple requests like opening apps, running commands, or quick questions. "
            "If you see a Conversation History Summary or Active Plan above, "
            "READ IT and continue from where you left off. Do NOT start over.\n"
            "For web pages: snapshot() → click_ref/type_ref. "
            "For native apps: desktop_snapshot() → desktop_click_ref/desktop_type_ref. "
            "NEVER use mouse_click/screenshot when snapshot-based methods are available."
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

    async def process_message(
        self,
        user_message: str,
        attachments: list[dict[str, str]] | None = None,
    ) -> AsyncIterator[AgentEvent]:
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

        # Ensure we have an active conversation.
        # On server restart the in-memory conversation_id is None even though
        # a conversation exists in the DB.  Try to resume the most recent one
        # before starting a brand-new conversation so we don't lose context.
        if not self._conversation.conversation_id:
            try:
                recent = await self._conversation.list_conversations(limit=1)
                if recent:
                    latest_id = recent[0]["id"]
                    await self._conversation.resume_conversation(latest_id)
                    logger.info(
                        "Resumed most recent conversation %s after context reset",
                        latest_id,
                    )
                else:
                    await self._conversation.start_conversation(title=user_message[:50])
            except Exception as _resume_err:
                logger.warning(
                    "Could not resume conversation: %s — starting fresh", _resume_err
                )
                await self._conversation.start_conversation(title=user_message[:50])

        await self._conversation.add_user_message(user_message)

        # Store attachments for the current message (transient, not persisted)
        self._conversation.pending_attachments = attachments or []

        # If the conversation was just resumed from DB (context reset recovery),
        # inject a brief system reminder so the LLM knows it's mid-task and
        # should not greet the user.  This is a belt-and-suspenders guard
        # alongside the system prompt rule and the summary injection.
        if getattr(self._conversation, '_just_resumed', False):
            self._conversation._just_resumed = False
            summary = self._conversation._current_summary
            if summary and (summary.get('goals') or summary.get('key_facts')):
                goals_text = '; '.join(summary.get('goals', [])[:3])
                facts_text = '; '.join(summary.get('key_facts', [])[:3])
                reminder = (
                    "[SYSTEM: Context restored after restart. "
                    "You are mid-task — DO NOT greet the user. "
                    f"Active goals: {goals_text or 'see summary above'}. "
                    f"Key facts: {facts_text or 'see summary above'}. "
                    "Continue from where you left off.]"
                )
                logger.info("Injecting mid-task context reminder after conversation resume")
                # Prepend to the user message that was just added
                msgs = self._conversation._messages  # type: ignore[attr-defined]
                if msgs and msgs[-1].get('role') == 'user':
                    original = msgs[-1].get('content', '')
                    if isinstance(original, str):
                        msgs[-1]['content'] = f"{reminder}\n\n{original}"

        # Drain any pending worker results into the conversation.
        # These are queued by background workers to avoid injecting
        # messages mid-tool-loop (which breaks Anthropic's tool_use/tool_result pairing).
        if hasattr(self, '_pending_worker_results') and self._pending_worker_results:
            for wr_msg in self._pending_worker_results:
                await self._conversation.add_user_message(
                    f"[SYSTEM NOTIFICATION]\n{wr_msg}"
                )
            logger.info(f"Drained {len(self._pending_worker_results)} pending worker results into conversation")
            self._pending_worker_results.clear()

        self._cancelled = False
        yield AgentEvent("thinking", {"message": "Processing your request..."})

        tool_defs = self._get_tool_definitions()

        external_rounds = 0  # only count rounds with real (non-plan) tool calls

        max_rounds = self._max_tool_rounds or self.DEFAULT_MAX_TOOL_ROUNDS

        for round_num in range(max_rounds):
            if self._cancelled:
                yield AgentEvent("cancelled", {"message": "Task stopped by user"})
                return
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

            if self._cancelled:
                yield AgentEvent("cancelled", {"message": "Task stopped by user"})
                return

            # Handle truncated responses (finish_reason=length)
            if response.finish_reason == "length":
                logger.warning(f"Response truncated (finish_reason=length) at round {round_num + 1}")
                # If there are tool calls with parse errors, don't execute them.
                # Instead, tell the LLM to retry with smaller content.
                has_parse_errors = any(
                    "__parse_error" in tc.arguments for tc in response.tool_calls
                ) if response.tool_calls else False

                if has_parse_errors or response.tool_calls:
                    # Add a user message telling the LLM its response was truncated
                    truncation_msg = (
                        "[SYSTEM] Your previous response was truncated (hit max_tokens limit). "
                        "Your tool call arguments were cut off and could not be parsed. "
                        "Please retry with SHORTER content. For large files, break them into "
                        "multiple smaller write operations, or use the shell tool to write "
                        "content via a script file."
                    )
                    await self._conversation.add_user_message(truncation_msg)
                    yield AgentEvent("info", {"message": "Response was truncated, asking to retry with shorter content..."})
                    continue  # Retry the round

            # If there's text content, emit it
            if response.content:
                yield AgentEvent("text", {"content": response.content})

            # If no tool calls, we're done
            if not response.tool_calls:
                await self._conversation.add_assistant_message(content=response.content)
                yield AgentEvent("done", {})
                return

            # Check for tool calls with parse errors and skip them
            valid_tool_calls = []
            for tc in response.tool_calls:
                if "__parse_error" in tc.arguments:
                    logger.warning(f"Skipping tool call {tc.name} with parse error: {tc.arguments.get('__parse_error')}")
                    # We still need to add a tool_result for Anthropic pairing
                    # This will be handled after we add the assistant message
                else:
                    valid_tool_calls.append(tc)

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
                decision = None

                if tc.name not in _INTERNAL_TOOLS:
                    # Check guardrails for external tools.
                    # Native computer use maps to the same guardrail rules
                    # as the openai_computer wrapper tool.
                    guardrail_name = (
                        "openai_computer" if tc.name == NATIVE_COMPUTER_USE_TOOL else tc.name
                    )
                    operation = tc.arguments.get("operation")
                    decision = self._guardrails.check(guardrail_name, operation, tc.arguments)

                    if not decision.allowed:
                        result_text = f"[DENIED] {decision.reason}"
                        yield AgentEvent(
                            "tool_result",
                            {"id": tc.id, "tool": tc.name, "result": result_text, "denied": True},
                        )
                        await self._conversation.add_tool_result(tc.id, result_text)
                        continue

                if (
                    tc.name not in _INTERNAL_TOOLS
                    and decision is not None
                    and decision.requires_approval
                ):
                    # Create the approval request first so we have an ID,
                    # then emit the event with that ID, then block.
                    approval_req = self._guardrails.create_approval(
                        tc.name, operation, tc.arguments, decision.reason
                    )
                    yield AgentEvent(
                        "tool_approval_needed",
                        {
                            "approval_id": approval_req.id,
                            "tool": tc.name,
                            "arguments": tc.arguments,
                            "reason": decision.reason,
                        },
                    )

                    approved = await self._guardrails.await_approval(approval_req)

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

                # Execute the tool (plan and native computer use handled internally)
                try:
                    if tc.name == "plan":
                        result = await self._handle_plan_tool(tc.arguments)
                        result_text = str(result)
                        # Emit plan update event for UI
                        await self._emit(AgentEvent("plan_update", {"result": result_text}))
                    elif tc.name == NATIVE_COMPUTER_USE_TOOL:
                        result_text = await self._execute_native_computer_use(tc.arguments)
                    else:
                        result = await self._execute_tool(tc.name, tc.arguments)
                        result_text = str(result)
                except Exception as e:
                    result_text = f"[ERROR] Tool execution failed: {e}"
                    logger.exception(f"Tool {tc.name} failed")

                # Ensure tool result content is never empty (Anthropic requirement)
                if not result_text or not result_text.strip():
                    result_text = "(no output)"

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

    async def _execute_native_computer_use(self, arguments: dict[str, Any]) -> str:
        """Execute OpenAI native computer use actions and return screenshot result.

        Called when the coordinator model (e.g. GPT-5.4) returns a ``computer_call``
        directly. Executes each action via ``ComputerUseExecutor`` and captures a
        screenshot to feed back to the model.
        """
        from plutus.core.openai_computer_use import (
            capture_screenshot_data_uri,
            execute_openai_computer_action,
        )
        from plutus.pc.computer_use import ComputerUseExecutor

        if not hasattr(self, "_computer_executor"):
            self._computer_executor = ComputerUseExecutor(native_resolution=True)

        executor = self._computer_executor
        actions = arguments.get("actions", [])

        for action in actions:
            try:
                await asyncio.to_thread(execute_openai_computer_action, executor, action)
            except Exception as e:
                logger.exception(f"Computer use action failed: {action.get('type')}")
                return json.dumps({"error": str(e)})
            await asyncio.sleep(0.5)

        # Capture screenshot after all actions
        try:
            screenshot_url = await asyncio.to_thread(capture_screenshot_data_uri, executor)
        except Exception as e:
            logger.exception("Screenshot capture failed after computer use actions")
            return json.dumps({"error": f"Screenshot capture failed: {e}"})

        if not screenshot_url:
            return json.dumps({"error": "Failed to capture screenshot"})

        return json.dumps({"screenshot_url": screenshot_url})

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

        When the model supports native computer use (e.g. GPT-5.4), the
        ``openai_computer`` wrapper tool is excluded — the model uses its
        built-in computer use capability directly via the Responses API.
        """
        defs: list[ToolDefinition] = []

        # When the model handles computer use natively, exclude the wrapper
        # tool so the model doesn't try to delegate to itself.
        native_cu = self._llm.supports_native_computer_use
        _excluded = {"openai_computer"} if native_cu else set()

        if self._tool_registry:
            all_defs = self._tool_registry.get_definitions()
            all_defs = [d for d in all_defs if d.name not in _excluded]
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
