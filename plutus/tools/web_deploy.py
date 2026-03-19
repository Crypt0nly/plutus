"""Web Deploy Tool — scaffold, build, and publicly host websites.

Supports React, Next.js, Vue, Vite, Node.js, and plain HTML/CSS/JS.
Deploys to Vercel (primary) or Netlify (fallback) with a single call.
Returns a live public URL immediately after deployment.

Usage:
  web_deploy(operation="deploy", path="/path/to/project")
  web_deploy(operation="deploy", path="/path/to/project", provider="netlify")
  web_deploy(operation="scaffold", framework="react", path="/path/to/new/project", name="my-app")
  web_deploy(operation="list")
  web_deploy(operation="delete", deployment_url="https://my-app.vercel.app")
  web_deploy(operation="status")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shutil
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.web_deploy")

IS_WINDOWS = platform.system() == "Windows"
HAS_WSL = IS_WINDOWS and shutil.which("wsl") is not None

DEPLOY_HISTORY_FILE = Path.home() / ".plutus" / "deployments.json"

# ── Framework detection ────────────────────────────────────────────────────────

FRAMEWORK_SIGNATURES: list[tuple[str, list[str]]] = [
    ("nextjs",    ["next.config.js", "next.config.ts", "next.config.mjs"]),
    ("react",     ["src/App.tsx", "src/App.jsx", "src/index.tsx", "src/index.jsx"]),
    ("vue",       ["vue.config.js", "src/App.vue"]),
    ("vite",      ["vite.config.js", "vite.config.ts", "vite.config.mjs"]),
    ("astro",     ["astro.config.mjs", "astro.config.ts"]),
    ("svelte",    ["svelte.config.js", "svelte.config.ts"]),
    ("nuxt",      ["nuxt.config.js", "nuxt.config.ts"]),
    ("angular",   ["angular.json"]),
    ("nodejs",    ["server.js", "server.ts", "app.js", "app.ts", "index.js"]),
    ("static",    ["index.html"]),
]

SCAFFOLD_TEMPLATES: dict[str, dict[str, Any]] = {
    "react": {
        "description": "React + Vite + TypeScript",
        "cmd_unix": "npm create vite@latest {name} -- --template react-ts && cd {name} && npm install",
        "cmd_win":  "npm create vite@latest {name} -- --template react-ts && cd {name} && npm install",
        "build_cmd": "npm run build",
        "output_dir": "dist",
    },
    "nextjs": {
        "description": "Next.js (App Router, TypeScript)",
        "cmd_unix": "npx create-next-app@latest {name} --typescript --tailwind --eslint --app --src-dir --import-alias '@/*' --yes",
        "cmd_win":  "npx create-next-app@latest {name} --typescript --tailwind --eslint --app --src-dir --import-alias @/* --yes",
        "build_cmd": "npm run build",
        "output_dir": ".next",
    },
    "vue": {
        "description": "Vue 3 + Vite + TypeScript",
        "cmd_unix": "npm create vite@latest {name} -- --template vue-ts && cd {name} && npm install",
        "cmd_win":  "npm create vite@latest {name} -- --template vue-ts && cd {name} && npm install",
        "build_cmd": "npm run build",
        "output_dir": "dist",
    },
    "svelte": {
        "description": "SvelteKit",
        "cmd_unix": "npm create svelte@latest {name} && cd {name} && npm install",
        "cmd_win":  "npm create svelte@latest {name} && cd {name} && npm install",
        "build_cmd": "npm run build",
        "output_dir": "build",
    },
    "astro": {
        "description": "Astro (static site)",
        "cmd_unix": "npm create astro@latest {name} -- --yes && cd {name} && npm install",
        "cmd_win":  "npm create astro@latest {name} -- --yes && cd {name} && npm install",
        "build_cmd": "npm run build",
        "output_dir": "dist",
    },
    "static": {
        "description": "Plain HTML/CSS/JS (no build step)",
        "cmd_unix": None,
        "cmd_win":  None,
        "build_cmd": None,
        "output_dir": ".",
    },
    "nodejs": {
        "description": "Node.js Express API/server",
        "cmd_unix": "mkdir -p {name} && cd {name} && npm init -y && npm install express",
        "cmd_win":  "mkdir {name} && cd {name} && npm init -y && npm install express",
        "build_cmd": None,
        "output_dir": ".",
    },
}


def _detect_framework(project_path: Path) -> str:
    """Auto-detect the framework used in a project directory."""
    for framework, signatures in FRAMEWORK_SIGNATURES:
        for sig in signatures:
            if (project_path / sig).exists():
                return framework
    # Check package.json dependencies
    pkg = project_path / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text())
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            if "next" in deps:
                return "nextjs"
            if "react" in deps:
                return "react"
            if "vue" in deps:
                return "vue"
            if "@sveltejs/kit" in deps or "svelte" in deps:
                return "svelte"
            if "astro" in deps:
                return "astro"
            if "express" in deps or "fastify" in deps or "koa" in deps:
                return "nodejs"
        except Exception:
            pass
    return "static"


def _load_history() -> list[dict[str, Any]]:
    """Load deployment history from disk."""
    if DEPLOY_HISTORY_FILE.exists():
        try:
            return json.loads(DEPLOY_HISTORY_FILE.read_text())
        except Exception:
            pass
    return []


def _save_history(history: list[dict[str, Any]]) -> None:
    """Save deployment history to disk."""
    DEPLOY_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    DEPLOY_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def _add_to_history(entry: dict[str, Any]) -> None:
    """Add a deployment entry to history."""
    history = _load_history()
    history.insert(0, entry)
    history = history[:50]  # Keep last 50 deployments
    _save_history(history)


async def _run_cmd(
    cmd: str,
    cwd: str | None = None,
    timeout: int = 300,
    use_wsl: bool = False,
) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    if use_wsl and HAS_WSL:
        escaped = cmd.replace("'", "'\\''")
        actual_cmd = f"wsl bash -c '{escaped}'"
    else:
        actual_cmd = cmd

    process = await asyncio.create_subprocess_shell(
        actual_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
            await process.wait()
        except Exception:
            pass
        return -1, "", f"[TIMEOUT] Command timed out after {timeout}s"


def _extract_url(output: str, provider: str) -> str | None:
    """Extract the deployment URL from CLI output."""
    if provider == "vercel":
        # Vercel outputs: "✅  Production: https://xxx.vercel.app [1s]"
        # or "🔍  Inspect: https://vercel.com/..."
        # or just the URL on its own line
        patterns = [
            r"Production:\s+(https://[^\s\[]+)",
            r"Preview:\s+(https://[^\s\[]+)",
            r"(https://[a-z0-9\-]+\.vercel\.app)",
            r"Deployed to (https://[^\s]+)",
        ]
        for pat in patterns:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    elif provider == "netlify":
        patterns = [
            r"Website URL:\s+(https://[^\s]+)",
            r"Website draft URL:\s+(https://[^\s]+)",
            r"(https://[a-z0-9\-]+\.netlify\.app)",
        ]
        for pat in patterns:
            m = re.search(pat, output, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return None


class WebDeployTool(Tool):
    """Deploy websites and web apps to public hosting (Vercel / Netlify)."""

    def __init__(self, secrets: Any = None) -> None:
        self._secrets = secrets  # PlutusConfig SecretsStore

    @property
    def name(self) -> str:
        return "web_deploy"

    @property
    def description(self) -> str:
        return (
            "Build and publicly host websites and web apps. "
            "Supports React, Next.js, Vue, Svelte, Astro, Node.js, and plain HTML/CSS/JS. "
            "Operations: "
            "'scaffold' — create a new project from a framework template; "
            "'deploy' — build and publish a project to a live public URL (Vercel or Netlify); "
            "'list' — show all past deployments with their URLs; "
            "'status' — check if the hosting CLI is installed and tokens are configured. "
            "After deploying, the tool returns the live public URL immediately. "
            "Requires a Vercel or Netlify auth token stored in Plutus settings "
            "(key: 'vercel_token' or 'netlify_token')."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["scaffold", "deploy", "list", "status"],
                    "description": (
                        "scaffold: Create a new project from a template. "
                        "deploy: Build and publish to a live public URL. "
                        "list: Show all past deployments. "
                        "status: Check CLI installation and token config."
                    ),
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Absolute path to the project directory. "
                        "Required for 'scaffold' and 'deploy'."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": (
                        "Project name (used as directory name for scaffold, "
                        "and as the Vercel/Netlify project name for deploy). "
                        "Use lowercase-with-hyphens format."
                    ),
                },
                "framework": {
                    "type": "string",
                    "enum": list(SCAFFOLD_TEMPLATES.keys()),
                    "description": (
                        "Framework to scaffold. Auto-detected for deploy. "
                        "Options: react, nextjs, vue, svelte, astro, static, nodejs."
                    ),
                },
                "provider": {
                    "type": "string",
                    "enum": ["vercel", "netlify"],
                    "description": "Hosting provider. Default: vercel.",
                },
                "production": {
                    "type": "boolean",
                    "description": (
                        "Deploy to production URL (default: true). "
                        "Set false for a preview/staging deployment."
                    ),
                },
                "build_cmd": {
                    "type": "string",
                    "description": (
                        "Override the build command (e.g. 'npm run build'). "
                        "Auto-detected from framework if not provided."
                    ),
                },
                "output_dir": {
                    "type": "string",
                    "description": (
                        "Override the build output directory (e.g. 'dist', 'build', 'out'). "
                        "Auto-detected from framework if not provided."
                    ),
                },
            },
            "required": ["operation"],
        }

    def _get_token(self, provider: str) -> str | None:
        """Get auth token for the given provider from secrets store."""
        # Check environment variables first (VERCEL_TOKEN / NETLIFY_TOKEN)
        env_key = os.environ.get(f"{provider.upper()}_TOKEN")
        if env_key:
            return env_key
        # Fall back to SecretsStore (stored as 'vercel_token' / 'netlify_token')
        if self._secrets is not None:
            try:
                return self._secrets.get_key(f"{provider}_token")
            except Exception:
                pass
        return None

    async def execute(self, **kwargs: Any) -> str:
        operation = kwargs.get("operation", "status")

        if operation == "status":
            return await self._status()
        elif operation == "scaffold":
            return await self._scaffold(**kwargs)
        elif operation == "deploy":
            return await self._deploy(**kwargs)
        elif operation == "list":
            return await self._list_deployments()
        else:
            return f"[ERROR] Unknown operation: {operation}"

    # ── Status ─────────────────────────────────────────────────────────────────

    async def _status(self) -> str:
        lines = ["## Web Deploy Status\n"]

        # Check Node.js
        rc, out, _ = await _run_cmd("node --version")
        node_ver = out.strip() if rc == 0 else "NOT FOUND"
        lines.append(f"- Node.js: {node_ver}")

        # Check npm
        rc, out, _ = await _run_cmd("npm --version")
        npm_ver = out.strip() if rc == 0 else "NOT FOUND"
        lines.append(f"- npm: {npm_ver}")

        # Check Vercel CLI
        rc, out, _ = await _run_cmd("vercel --version")
        vercel_ver = out.strip().split("\n")[0] if rc == 0 else "NOT INSTALLED"
        lines.append(f"- Vercel CLI: {vercel_ver}")

        # Check Netlify CLI
        rc, out, _ = await _run_cmd("netlify --version")
        netlify_ver = out.strip().split("\n")[0] if rc == 0 else "NOT INSTALLED"
        lines.append(f"- Netlify CLI: {netlify_ver}")

        # Check tokens
        vercel_token = self._get_token("vercel")
        netlify_token = self._get_token("netlify")
        lines.append(f"- Vercel token: {'✅ configured' if vercel_token else '❌ not set (add vercel_token to settings)'}")
        lines.append(f"- Netlify token: {'✅ configured' if netlify_token else '❌ not set (add netlify_token to settings)'}")

        history = _load_history()
        lines.append(f"\n**Deployments in history:** {len(history)}")
        if history:
            lines.append(f"**Last deployment:** {history[0].get('url', 'unknown')} ({history[0].get('name', '')})")

        return "\n".join(lines)

    # ── Scaffold ───────────────────────────────────────────────────────────────

    async def _scaffold(self, **kwargs: Any) -> str:
        framework = kwargs.get("framework", "react")
        path = kwargs.get("path")
        name = kwargs.get("name", "my-app")

        if framework not in SCAFFOLD_TEMPLATES:
            return f"[ERROR] Unknown framework '{framework}'. Choose from: {', '.join(SCAFFOLD_TEMPLATES.keys())}"

        template = SCAFFOLD_TEMPLATES[framework]

        if path:
            parent_dir = str(Path(path).parent)
            project_name = Path(path).name
        else:
            parent_dir = str(Path.home() / "projects")
            project_name = name

        Path(parent_dir).mkdir(parents=True, exist_ok=True)

        if framework == "static":
            # Create a minimal static site
            project_dir = Path(parent_dir) / project_name
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / "index.html").write_text(
                f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{project_name}</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <h1>Welcome to {project_name}</h1>
  <script src="main.js"></script>
</body>
</html>
""")
            (project_dir / "style.css").write_text(
                "body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; }\n"
            )
            (project_dir / "main.js").write_text(
                "console.log('Hello from " + project_name + "');\n"
            )
            return (
                f"✅ Static project scaffolded at: {project_dir}\n"
                f"Files created: index.html, style.css, main.js\n"
                f"Next step: edit the files, then call web_deploy(operation='deploy', path='{project_dir}')"
            )

        cmd_key = "cmd_win" if IS_WINDOWS else "cmd_unix"
        cmd = template[cmd_key]
        if cmd is None:
            return f"[ERROR] No scaffold command for framework '{framework}' on this platform."

        cmd = cmd.format(name=project_name)
        lines = [f"🔨 Scaffolding {template['description']} project '{project_name}'...\n"]

        rc, stdout, stderr = await _run_cmd(cmd, cwd=parent_dir, timeout=180)
        if rc != 0:
            return (
                f"[ERROR] Scaffold failed (exit {rc}):\n"
                f"stdout: {stdout[-2000:]}\nstderr: {stderr[-2000:]}"
            )

        project_dir = Path(parent_dir) / project_name
        lines.append(f"✅ Project created at: {project_dir}")
        lines.append(f"Framework: {template['description']}")
        lines.append(f"\nNext steps:")
        lines.append(f"  1. Edit your project files in: {project_dir}")
        lines.append(f"  2. Deploy with: web_deploy(operation='deploy', path='{project_dir}')")

        return "\n".join(lines)

    # ── Deploy ─────────────────────────────────────────────────────────────────

    async def _deploy(self, **kwargs: Any) -> str:
        path = kwargs.get("path")
        if not path:
            return "[ERROR] 'path' is required for deploy operation."

        project_path = Path(path).expanduser().resolve()
        if not project_path.exists():
            return f"[ERROR] Project directory does not exist: {project_path}"

        provider = kwargs.get("provider", "vercel").lower()
        production = kwargs.get("production", True)
        name = kwargs.get("name") or project_path.name
        # Sanitize name: lowercase, hyphens only
        name = re.sub(r"[^a-z0-9\-]", "-", name.lower()).strip("-")

        token = self._get_token(provider)
        if not token:
            return (
                f"[ERROR] No {provider}_token found in Plutus settings.\n"
                f"To fix this:\n"
                f"  1. Go to https://{'vercel.com/account/tokens' if provider == 'vercel' else 'app.netlify.com/user/applications/personal'}\n"
                f"  2. Create a new token\n"
                f"  3. In Plutus Settings → Secrets, add key '{provider}_token' with the token value\n"
                f"  4. Then retry this deploy command."
            )

        # Detect framework
        framework = kwargs.get("framework") or _detect_framework(project_path)
        template = SCAFFOLD_TEMPLATES.get(framework, SCAFFOLD_TEMPLATES["static"])
        build_cmd = kwargs.get("build_cmd") or template.get("build_cmd")
        output_dir = kwargs.get("output_dir") or template.get("output_dir", ".")

        lines = [f"🚀 Deploying **{name}** ({framework}) to {provider}...\n"]

        # Step 1: Install dependencies if package.json exists
        pkg_json = project_path / "package.json"
        if pkg_json.exists():
            lines.append("📦 Installing dependencies...")
            rc, stdout, stderr = await _run_cmd(
                "npm install --legacy-peer-deps",
                cwd=str(project_path),
                timeout=180,
            )
            if rc != 0:
                lines.append(f"⚠️  npm install had warnings (continuing):\n{stderr[-500:]}")

        # Step 2: Build if needed
        if build_cmd and output_dir != ".":
            lines.append(f"🔨 Building ({build_cmd})...")
            rc, stdout, stderr = await _run_cmd(
                build_cmd,
                cwd=str(project_path),
                timeout=300,
            )
            if rc != 0:
                return (
                    "\n".join(lines) + "\n\n"
                    f"[ERROR] Build failed (exit {rc}):\n"
                    f"stdout: {stdout[-3000:]}\nstderr: {stderr[-3000:]}"
                )
            lines.append("✅ Build successful.")

        # Step 3: Deploy
        if provider == "vercel":
            return await self._deploy_vercel(
                project_path, name, token, production, output_dir, framework, lines
            )
        elif provider == "netlify":
            return await self._deploy_netlify(
                project_path, name, token, production, output_dir, lines
            )
        else:
            return f"[ERROR] Unknown provider: {provider}"

    async def _deploy_vercel(
        self,
        project_path: Path,
        name: str,
        token: str,
        production: bool,
        output_dir: str,
        framework: str,
        lines: list[str],
    ) -> str:
        # Ensure Vercel CLI is installed
        rc, _, _ = await _run_cmd("vercel --version")
        if rc != 0:
            lines.append("📥 Installing Vercel CLI...")
            rc2, _, stderr2 = await _run_cmd("npm install -g vercel", timeout=120)
            if rc2 != 0:
                return "\n".join(lines) + f"\n[ERROR] Failed to install Vercel CLI:\n{stderr2}"

        # Determine what to deploy
        deploy_dir = project_path
        if output_dir and output_dir != "." and (project_path / output_dir).exists():
            deploy_dir = project_path / output_dir

        prod_flag = "--prod" if production else ""
        cmd = (
            f'vercel deploy "{deploy_dir}" '
            f'--token {token} '
            f'--name {name} '
            f'--yes '
            f'{prod_flag} '
            f'--no-clipboard'
        ).strip()

        lines.append(f"☁️  Uploading to Vercel{' (production)' if production else ' (preview)'}...")
        rc, stdout, stderr = await _run_cmd(cmd, cwd=str(project_path), timeout=300)

        combined = stdout + "\n" + stderr
        url = _extract_url(combined, "vercel")

        if rc != 0 and not url:
            return (
                "\n".join(lines) + "\n\n"
                f"[ERROR] Vercel deploy failed (exit {rc}):\n"
                f"stdout: {stdout[-3000:]}\nstderr: {stderr[-2000:]}"
            )

        if not url:
            # Try to find any https URL in output
            m = re.search(r"(https://\S+)", combined)
            url = m.group(1) if m else "URL not found in output"

        lines.append(f"\n✅ **Deployed successfully!**")
        lines.append(f"🌐 **Live URL:** {url}")
        lines.append(f"📁 Project: {name}")
        lines.append(f"☁️  Provider: Vercel")

        _add_to_history({
            "name": name,
            "url": url,
            "provider": "vercel",
            "path": str(project_path),
            "production": production,
        })

        return "\n".join(lines)

    async def _deploy_netlify(
        self,
        project_path: Path,
        name: str,
        token: str,
        production: bool,
        output_dir: str,
        lines: list[str],
    ) -> str:
        # Ensure Netlify CLI is installed
        rc, _, _ = await _run_cmd("netlify --version")
        if rc != 0:
            lines.append("📥 Installing Netlify CLI...")
            rc2, _, stderr2 = await _run_cmd("npm install -g netlify-cli", timeout=120)
            if rc2 != 0:
                return "\n".join(lines) + f"\n[ERROR] Failed to install Netlify CLI:\n{stderr2}"

        deploy_dir = project_path
        if output_dir and output_dir != "." and (project_path / output_dir).exists():
            deploy_dir = project_path / output_dir

        prod_flag = "--prod" if production else ""
        cmd = (
            f'netlify deploy '
            f'--dir "{deploy_dir}" '
            f'--auth {token} '
            f'--site {name} '
            f'{prod_flag} '
            f'--json'
        ).strip()

        lines.append(f"☁️  Uploading to Netlify{' (production)' if production else ' (preview)'}...")
        rc, stdout, stderr = await _run_cmd(cmd, cwd=str(project_path), timeout=300)

        # Try to parse JSON output
        url = None
        try:
            data = json.loads(stdout)
            url = data.get("deploy_url") or data.get("url") or data.get("ssl_url")
        except Exception:
            pass

        combined = stdout + "\n" + stderr
        if not url:
            url = _extract_url(combined, "netlify")

        if rc != 0 and not url:
            # Netlify may fail on first deploy if site doesn't exist yet — create it
            lines.append("⚙️  Site not found, creating new Netlify site...")
            create_cmd = f"netlify sites:create --name {name} --auth {token}"
            await _run_cmd(create_cmd, timeout=60)
            # Retry deploy
            rc, stdout, stderr = await _run_cmd(cmd, cwd=str(project_path), timeout=300)
            try:
                data = json.loads(stdout)
                url = data.get("deploy_url") or data.get("url") or data.get("ssl_url")
            except Exception:
                pass
            combined = stdout + "\n" + stderr
            if not url:
                url = _extract_url(combined, "netlify")
            if rc != 0 and not url:
                return (
                    "\n".join(lines) + "\n\n"
                    f"[ERROR] Netlify deploy failed (exit {rc}):\n"
                    f"stdout: {stdout[-3000:]}\nstderr: {stderr[-2000:]}"
                )

        lines.append(f"\n✅ **Deployed successfully!**")
        lines.append(f"🌐 **Live URL:** {url}")
        lines.append(f"📁 Project: {name}")
        lines.append(f"☁️  Provider: Netlify")

        _add_to_history({
            "name": name,
            "url": url,
            "provider": "netlify",
            "path": str(project_path),
            "production": production,
        })

        return "\n".join(lines)

    # ── List ───────────────────────────────────────────────────────────────────

    async def _list_deployments(self) -> str:
        history = _load_history()
        if not history:
            return "No deployments yet. Use web_deploy(operation='deploy', path='...') to publish your first site."

        lines = [f"## Deployment History ({len(history)} total)\n"]
        for i, entry in enumerate(history[:20], 1):
            prod = "🟢 production" if entry.get("production") else "🔵 preview"
            lines.append(
                f"{i}. **{entry.get('name', 'unknown')}** — {entry.get('url', 'no url')} "
                f"({entry.get('provider', '?')}, {prod})"
            )
        return "\n".join(lines)
