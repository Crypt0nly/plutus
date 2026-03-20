from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_session
from app.services.agent_service import AgentService

router = APIRouter()

# ---------------------------------------------------------------------------
# Built-in cloud skills — mirroring the local Plutus skill registry.
# These are always available to every user; user-created skills are appended.
# ---------------------------------------------------------------------------

_BUILTIN_SKILLS = [
    # ── Web / Browser ────────────────────────────────────────────────────────
    {
        "name": "google_search",
        "display_name": "Google Search",
        "description": "Search the web using Google and return top results.",
        "app": "browser",
        "category": "browser",
        "triggers": ["search", "google", "look up", "find online"],
        "required_params": ["query"],
        "optional_params": ["num_results"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "open_website",
        "display_name": "Open Website",
        "description": "Navigate to a URL and extract its content.",
        "app": "browser",
        "category": "browser",
        "triggers": ["open", "visit", "browse", "navigate to"],
        "required_params": ["url"],
        "optional_params": [],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "download_file",
        "display_name": "Download File",
        "description": "Download a file from a URL to the workspace.",
        "app": "browser",
        "category": "browser",
        "triggers": ["download", "fetch file", "save from url"],
        "required_params": ["url"],
        "optional_params": ["filename"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    # ── Files / Workspace ────────────────────────────────────────────────────
    {
        "name": "create_file",
        "display_name": "Create File",
        "description": "Create a new file in the user workspace with given content.",
        "app": "files",
        "category": "files",
        "triggers": ["create file", "write file", "save file", "new file"],
        "required_params": ["filename", "content"],
        "optional_params": ["path"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "read_file",
        "display_name": "Read File",
        "description": "Read the contents of a file from the user workspace.",
        "app": "files",
        "category": "files",
        "triggers": ["read file", "open file", "show file", "cat"],
        "required_params": ["filename"],
        "optional_params": [],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "list_files",
        "display_name": "List Files",
        "description": "List files and folders in the user workspace.",
        "app": "files",
        "category": "files",
        "triggers": ["list files", "show files", "ls", "dir"],
        "required_params": [],
        "optional_params": ["path"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "find_files",
        "display_name": "Find Files",
        "description": "Search for files by name or content in the workspace.",
        "app": "files",
        "category": "files",
        "triggers": ["find file", "search file", "locate file"],
        "required_params": ["pattern"],
        "optional_params": ["path"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "zip_files",
        "display_name": "Zip Files",
        "description": "Compress files or folders into a zip archive.",
        "app": "files",
        "category": "files",
        "triggers": ["zip", "compress", "archive"],
        "required_params": ["source"],
        "optional_params": ["output_name"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    # ── Code ─────────────────────────────────────────────────────────────────
    {
        "name": "run_python",
        "display_name": "Run Python",
        "description": "Execute Python code in a sandboxed environment.",
        "app": "code",
        "category": "development",
        "triggers": ["run python", "execute python", "python script"],
        "required_params": ["code"],
        "optional_params": ["timeout"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "run_shell",
        "display_name": "Run Shell Command",
        "description": "Execute a shell command in the user workspace.",
        "app": "code",
        "category": "development",
        "triggers": ["run command", "shell", "bash", "terminal"],
        "required_params": ["command"],
        "optional_params": ["cwd"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    # ── GitHub ────────────────────────────────────────────────────────────────
    {
        "name": "github_clone",
        "display_name": "Clone Repository",
        "description": "Clone a GitHub repository into the workspace.",
        "app": "github",
        "category": "development",
        "triggers": ["clone", "git clone", "clone repo"],
        "required_params": ["repo_url"],
        "optional_params": ["branch", "directory"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "github_push",
        "display_name": "Push to GitHub",
        "description": "Commit and push changes to a GitHub repository.",
        "app": "github",
        "category": "development",
        "triggers": ["push", "git push", "commit and push"],
        "required_params": ["message"],
        "optional_params": ["branch"],
        "steps_count": 2,
        "dynamic": False,
        "version": 1,
    },
    # ── Email ─────────────────────────────────────────────────────────────────
    {
        "name": "send_email",
        "display_name": "Send Email",
        "description": "Send an email via the configured email connector.",
        "app": "email",
        "category": "email",
        "triggers": ["send email", "email", "mail"],
        "required_params": ["to", "subject", "body"],
        "optional_params": ["cc", "bcc"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    # ── Calendar ──────────────────────────────────────────────────────────────
    {
        "name": "create_calendar_event",
        "display_name": "Create Calendar Event",
        "description": "Create a new event in Google Calendar.",
        "app": "google_calendar",
        "category": "calendar",
        "triggers": ["create event", "schedule meeting", "add to calendar"],
        "required_params": ["title", "start_time", "end_time"],
        "optional_params": ["description", "attendees", "location"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "list_calendar_events",
        "display_name": "List Calendar Events",
        "description": "List upcoming events from Google Calendar.",
        "app": "google_calendar",
        "category": "calendar",
        "triggers": ["list events", "show calendar", "upcoming events", "my schedule"],
        "required_params": [],
        "optional_params": ["days_ahead", "max_results"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    # ── Productivity ──────────────────────────────────────────────────────────
    {
        "name": "summarize_text",
        "display_name": "Summarize Text",
        "description": "Summarize a long piece of text using the AI model.",
        "app": "ai",
        "category": "productivity",
        "triggers": ["summarize", "tldr", "brief", "condense"],
        "required_params": ["text"],
        "optional_params": ["max_length", "style"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "translate_text",
        "display_name": "Translate Text",
        "description": "Translate text to another language using the AI model.",
        "app": "ai",
        "category": "productivity",
        "triggers": ["translate", "translation"],
        "required_params": ["text", "target_language"],
        "optional_params": ["source_language"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
    {
        "name": "draft_document",
        "display_name": "Draft Document",
        "description": "Draft a document, report or email based on a prompt.",
        "app": "ai",
        "category": "productivity",
        "triggers": ["draft", "write document", "compose", "create report"],
        "required_params": ["prompt"],
        "optional_params": ["format", "tone", "length"],
        "steps_count": 1,
        "dynamic": False,
        "version": 1,
    },
]

# ── Tools/Details categories (for the ToolsView) ────────────────────────────

_TOOLS_CATEGORIES = {
    "sandbox": {
        "label": "Sandbox Tools",
        "description": (
            "Run code and commands in a secure cloud sandbox (or your local machine if connected)"
        ),
        "icon": "terminal",
        "tools": [
            {
                "name": "shell_exec",
                "description": (
                    "Run any shell command in a secure Linux environment"
                    " — install packages, run scripts, manage files."
                ),
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "command": {"description": "The shell command to execute"},
                        "timeout": {"description": "Timeout in seconds (default 30)"},
                    }
                },
            },
            {
                "name": "python_exec",
                "description": (
                    "Execute Python code in a persistent kernel."
                    " Variables and imports persist across calls within the same conversation."
                ),
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "code": {"description": "Python code to execute"},
                    }
                },
            },
            {
                "name": "file_read",
                "description": "Read the contents of any file in the sandbox.",
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "path": {"description": "Absolute path to the file"},
                    }
                },
            },
            {
                "name": "file_write",
                "description": "Write or overwrite a file in the sandbox.",
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "path": {"description": "Absolute path to the file"},
                        "content": {"description": "Content to write"},
                    }
                },
            },
            {
                "name": "file_list",
                "description": "List files and directories at a given path in the sandbox.",
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "path": {"description": "Directory path to list (default: /home/user)"},
                    }
                },
            },
        ],
    },
    "web": {
        "label": "Web Tools",
        "description": "Search the web and read web pages",
        "icon": "code",
        "tools": [
            {
                "name": "web_search",
                "description": (
                    "Search the web using DuckDuckGo and return the top results."
                    " Use for finding current information, news, or documentation."
                ),
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "query": {"description": "Search query"},
                        "num_results": {
                            "description": "Number of results to return (default 5, max 10)"
                        },
                    }
                },
            },
            {
                "name": "web_browse",
                "description": (
                    "Fetch the full text content of any web page."
                    " Use after web_search to read the complete content of a result."
                ),
                "enabled": True,
                "status": "available",
                "parameters": {
                    "properties": {
                        "url": {"description": "URL to fetch"},
                    }
                },
            },
        ],
    },
    "memory": {
        "label": "Memory",
        "description": "Persistent memory across conversations",
        "icon": "cpu",
        "tools": [
            {
                "name": "memory",
                "description": (
                    "Store and recall facts about you across conversations"
                    " so Plutus remembers your preferences and context."
                ),
                "enabled": True,
                "status": "available",
            },
        ],
    },
    "connectors": {
        "label": "Connectors",
        "description": "Integrations with external services",
        "icon": "puzzle",
        "tools": [
            {
                "name": "email",
                "description": "Send emails via configured email connector",
                "enabled": False,
                "status": "coming_soon",
            },
            {
                "name": "calendar",
                "description": "Manage Google Calendar events",
                "enabled": False,
                "status": "coming_soon",
            },
            {
                "name": "telegram",
                "description": "Send messages via Telegram bot",
                "enabled": False,
                "status": "coming_soon",
            },
        ],
    },
    "local_only": {
        "label": "Local-Only Tools",
        "description": (
            "These tools require the self-hosted version with your local machine connected"
        ),
        "icon": "monitor",
        "tools": [
            {
                "name": "browser",
                "description": (
                    "Control a real browser — open pages, click, fill forms, take screenshots"
                ),
                "enabled": False,
                "status": "local_only",
            },
            {
                "name": "desktop",
                "description": (
                    "Control your desktop — move mouse, type, interact with any application"
                ),
                "enabled": False,
                "status": "local_only",
            },
            {
                "name": "app_manager",
                "description": "Open, close and manage applications on your computer",
                "enabled": False,
                "status": "local_only",
            },
            {
                "name": "scheduler",
                "description": "Schedule tasks and cron jobs to run automatically",
                "enabled": False,
                "status": "local_only",
            },
        ],
    },
    "custom": {
        "label": "Custom Tools",
        "description": "Tools you have created",
        "icon": "puzzle",
        "tools": [],
    },
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status")
async def agent_status(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    state = await svc.get_agent_state(user["user_id"])
    return {
        "status": state.status if state else "not_initialized",
        "user_id": user["user_id"],
    }


@router.post("/restart")
async def restart_agent(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    state = await svc.ensure_agent_state(user["user_id"])
    state.status = "idle"
    await session.commit()
    return {"status": "restarted"}


@router.get("/memory")
async def list_memory(
    category: str = Query(None),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    memories = await svc.recall_memories(user["user_id"], category=category)
    return {
        "memories": [
            {
                "id": m.id,
                "category": m.category,
                "content": m.content,
                "created_at": str(m.created_at),
            }
            for m in memories
        ]
    }


@router.post("/memory")
async def save_memory(
    payload: dict,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    mem = await svc.save_memory(
        user["user_id"],
        category=payload.get("category", "general"),
        content=payload["content"],
    )
    return {"id": mem.id, "category": mem.category, "content": mem.content}


@router.delete("/memory/{fact_id}")
async def delete_memory(
    fact_id: int,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import delete as sql_delete

    from app.models.agent_state import Memory

    await session.execute(
        sql_delete(Memory).where(Memory.id == fact_id, Memory.user_id == user["user_id"])
    )
    await session.commit()
    return {"deleted": fact_id}


@router.get("/skills")
async def list_skills(
    category: str = Query(None),
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Return built-in cloud skills plus any user-created skills.
    The SkillsView expects: { skills: [...], categories: [...] }
    The ToolsView (via getTools) expects a plain array.
    We return the object shape; getTools uses the same endpoint but
    the frontend uses data?.skills ?? data (handled in api.ts).
    """
    svc = AgentService(session)
    user_skills = await svc.list_skills(user["user_id"])

    user_skill_dicts = [
        {
            "name": s.name,
            "display_name": s.name.replace("_", " ").title(),
            "description": s.description or "",
            "app": "custom",
            "category": "custom",
            "triggers": [],
            "required_params": [],
            "optional_params": [],
            "steps_count": 1,
            "dynamic": True,
            "version": s.sync_version,
        }
        for s in user_skills
    ]

    all_skills = _BUILTIN_SKILLS + user_skill_dicts

    # Apply category filter if provided
    if category and category != "all":
        all_skills = [s for s in all_skills if s["category"] == category]

    categories = sorted({s["category"] for s in all_skills})

    return {"skills": all_skills, "categories": categories}


@router.get("/skills/saved")
async def list_saved_skills(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return user-created/saved custom skills."""
    svc = AgentService(session)
    user_skills = await svc.list_skills(user["user_id"])
    return {
        "skills": [
            {
                "name": s.name,
                "display_name": s.name.replace("_", " ").title(),
                "description": s.description or "",
                "app": "custom",
                "category": "custom",
                "triggers": [],
                "required_params": [],
                "optional_params": [],
                "steps_count": 1,
                "dynamic": True,
                "version": s.sync_version,
            }
            for s in user_skills
        ]
    }


@router.get("/skills/details")
async def get_skills_details(_user=Depends(get_current_user)):
    """Return tools grouped by category for the ToolsView."""
    all_tools = [t for cat in _TOOLS_CATEGORIES.values() for t in cat["tools"]]
    return {
        "categories": _TOOLS_CATEGORIES,
        "total": sum(len(cat["tools"]) for cat in _TOOLS_CATEGORIES.values()),
        "tools": all_tools,
    }


@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str, _user=Depends(get_current_user)):
    for s in _BUILTIN_SKILLS:
        if s["name"] == skill_name:
            return s
    return {}


@router.delete("/skills/{skill_name}")
async def delete_skill(
    skill_name: str,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import delete as sql_delete

    from app.models.agent_state import Skill

    await session.execute(
        sql_delete(Skill).where(Skill.name == skill_name, Skill.user_id == user["user_id"])
    )
    await session.commit()
    return {"deleted": skill_name}


@router.post("/skills/import")
async def import_skill(
    payload: dict,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.models.agent_state import Skill

    skill = Skill(
        user_id=user["user_id"],
        name=payload.get("name", "imported_skill"),
        description=payload.get("description", ""),
        skill_type=payload.get("skill_type", "simple"),
        definition=payload,
    )
    session.add(skill)
    await session.commit()
    return {"message": "imported", "name": skill.name}


@router.get("/skills/{skill_name}/export")
async def export_skill(skill_name: str, _user=Depends(get_current_user)):
    for s in _BUILTIN_SKILLS:
        if s["name"] == skill_name:
            return s
    return {}


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    tasks = await svc.list_scheduled_tasks(user["user_id"])
    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "schedule": t.schedule,
                "prompt": t.prompt,
            }
            for t in tasks
        ]
    }


@router.post("/scheduled-tasks")
async def create_scheduled_task(
    payload: dict,
    user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = AgentService(session)
    task = await svc.create_scheduled_task(
        user["user_id"],
        name=payload["name"],
        schedule=payload["schedule"],
        prompt=payload["prompt"],
        description=payload.get("description", ""),
    )
    return {"id": task.id, "name": task.name, "schedule": task.schedule}
