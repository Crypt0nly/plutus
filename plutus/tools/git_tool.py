"""Git tool — local git workflow using the GitHub connector token.

Provides full git operations (clone, commit, push, pull, branch, etc.)
that automatically authenticate using the GitHub personal access token
stored in the GitHub connector. This lets the agent work with repos
the same way a developer would from the command line.

The default working directory is ~/plutus-workspace/ — the agent's
persistent local workspace for projects and code.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
from pathlib import Path
from typing import Any

from plutus.tools.base import Tool

logger = logging.getLogger("plutus.tools.git")

MAX_OUTPUT_LENGTH = 50_000
WORKSPACE_DIR = str(Path.home() / "plutus-workspace")


class GitTool(Tool):
    """Git operations with automatic GitHub authentication."""

    def __init__(self, connector_manager: Any = None):
        self._connector_manager = connector_manager

    @property
    def name(self) -> str:
        return "git"

    @property
    def description(self) -> str:
        return (
            "Execute git operations on local repositories. Automatically authenticates "
            "with GitHub using the configured GitHub connector token. "
            "Supports: clone, init, status, add, commit, push, pull, fetch, branch, "
            "checkout, merge, diff, log, remote, stash, tag, reset. "
            f"Default working directory: {WORKSPACE_DIR}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "clone", "init", "status", "add", "commit", "push",
                        "pull", "fetch", "branch", "checkout", "merge",
                        "diff", "log", "remote", "stash", "tag", "reset",
                    ],
                    "description": "The git operation to perform",
                },
                "args": {
                    "type": "string",
                    "description": (
                        "Arguments for the git operation. Examples:\n"
                        "  clone: 'https://github.com/user/repo.git' or 'user/repo'\n"
                        "  add: '.' or 'file.py src/'\n"
                        "  commit: '-m \"feat: add new feature\"'\n"
                        "  push: 'origin main' or '' for default\n"
                        "  pull: 'origin main' or '' for default\n"
                        "  branch: 'new-branch' or '-d old-branch' or '' to list\n"
                        "  checkout: 'branch-name' or '-b new-branch'\n"
                        "  merge: 'feature-branch'\n"
                        "  diff: '' or '--staged' or 'HEAD~1'\n"
                        "  log: '--oneline -10' or '' for default\n"
                        "  remote: '-v' or 'add origin url'\n"
                        "  stash: '' or 'pop' or 'list'\n"
                        "  tag: 'v1.0.0' or '-l' to list\n"
                        "  reset: '--soft HEAD~1' or 'HEAD file.py'"
                    ),
                },
                "working_directory": {
                    "type": "string",
                    "description": (
                        f"Working directory for the git command. "
                        f"Defaults to {WORKSPACE_DIR}. "
                        f"For operations inside a cloned repo, set this to the repo directory."
                    ),
                },
            },
            "required": ["operation"],
        }

    def _get_github_token(self) -> str | None:
        """Retrieve the GitHub token from the connector manager."""
        if not self._connector_manager:
            return None
        try:
            github = self._connector_manager.get_connector("github")
            if github and github.is_configured():
                config = github.get_config()
                return config.get("personal_access_token")
        except Exception as e:
            logger.debug(f"Could not retrieve GitHub token: {e}")
        return None

    def _get_github_username(self) -> str | None:
        """Retrieve the default owner from GitHub connector config."""
        if not self._connector_manager:
            return None
        try:
            github = self._connector_manager.get_connector("github")
            if github and github.is_configured():
                config = github.get_config()
                return config.get("default_owner")
        except Exception:
            return None

    def _inject_token_into_url(self, url: str, token: str) -> str:
        """Inject the GitHub token into a clone URL for authentication.

        Converts:
          https://github.com/user/repo.git
        To:
          https://x-access-token:{token}@github.com/user/repo.git
        """
        if url.startswith("https://"):
            # Remove any existing credentials
            if "@" in url:
                url = "https://" + url.split("@", 1)[1]
            return url.replace("https://", f"https://x-access-token:{token}@", 1)
        return url

    def _expand_repo_shorthand(self, repo: str) -> str:
        """Expand 'user/repo' shorthand to full GitHub URL."""
        repo = repo.strip()
        if repo.startswith("http://") or repo.startswith("https://") or repo.startswith("git@"):
            return repo
        if "/" in repo and not os.path.exists(repo):
            # Looks like user/repo shorthand
            return f"https://github.com/{repo}.git"
        return repo

    async def execute(self, **kwargs: Any) -> str:
        operation: str = kwargs["operation"]
        args: str = kwargs.get("args", "")
        working_dir: str = kwargs.get("working_directory", WORKSPACE_DIR)

        # Ensure workspace exists
        workspace = Path(working_dir).expanduser().resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        token = self._get_github_token()

        # Build the git command
        try:
            command, env_override = self._build_command(operation, args, token, str(workspace))
        except ValueError as e:
            return f"[ERROR] {e}"

        # Execute
        try:
            env = os.environ.copy()
            if env_override:
                env.update(env_override)

            # On Windows, use git from PATH; on WSL/Linux it's just git
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workspace),
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=120
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Truncate large outputs
            if len(stdout_text) > MAX_OUTPUT_LENGTH:
                stdout_text = stdout_text[:MAX_OUTPUT_LENGTH] + "\n... [truncated]"
            if len(stderr_text) > MAX_OUTPUT_LENGTH:
                stderr_text = stderr_text[:MAX_OUTPUT_LENGTH] + "\n... [truncated]"

            # Sanitize output — remove tokens from any error messages
            if token:
                stdout_text = stdout_text.replace(token, "***")
                stderr_text = stderr_text.replace(token, "***")

            result_parts = []
            if stdout_text.strip():
                result_parts.append(stdout_text.strip())
            if stderr_text.strip():
                # Git uses stderr for progress info (not just errors)
                result_parts.append(stderr_text.strip())
            if process.returncode != 0:
                result_parts.append(f"\n[exit code: {process.returncode}]")

            return "\n".join(result_parts) if result_parts else f"git {operation}: OK"

        except asyncio.TimeoutError:
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            return f"[TIMEOUT] git {operation} timed out after 120 seconds"
        except FileNotFoundError:
            return (
                "[ERROR] git is not installed or not on PATH. "
                "Install git from https://git-scm.com/downloads"
            )
        except Exception as e:
            error_msg = str(e)
            if token:
                error_msg = error_msg.replace(token, "***")
            return f"[ERROR] {error_msg}"

    def _build_command(
        self, operation: str, args: str, token: str | None, working_dir: str
    ) -> tuple[str, dict[str, str] | None]:
        """Build the git command string and optional env overrides.

        Returns (command_string, env_dict_or_None).
        """
        env_override: dict[str, str] | None = None

        if operation == "clone":
            url = self._expand_repo_shorthand(args.split()[0] if args else "")
            if not url:
                raise ValueError("clone requires a repository URL or 'user/repo' shorthand")
            extra_args = " ".join(args.split()[1:]) if len(args.split()) > 1 else ""

            if token and url.startswith("https://"):
                url = self._inject_token_into_url(url, token)

            cmd = f'git clone {url} {extra_args}'.strip()
            return cmd, env_override

        if operation == "init":
            cmd = f"git init {args}".strip()
            return cmd, env_override

        if operation == "status":
            cmd = f"git status {args}".strip()
            return cmd, env_override

        if operation == "add":
            if not args:
                args = "."
            cmd = f"git add {args}"
            return cmd, env_override

        if operation == "commit":
            if not args:
                raise ValueError("commit requires args, e.g. '-m \"your message\"'")
            cmd = f"git commit {args}"
            return cmd, env_override

        if operation == "push":
            # Configure credential helper for this push using the token
            if token:
                env_override = self._credential_env(token)
            cmd = f"git push {args}".strip()
            return cmd, env_override

        if operation == "pull":
            if token:
                env_override = self._credential_env(token)
            cmd = f"git pull {args}".strip()
            return cmd, env_override

        if operation == "fetch":
            if token:
                env_override = self._credential_env(token)
            cmd = f"git fetch {args}".strip()
            return cmd, env_override

        if operation == "branch":
            cmd = f"git branch {args}".strip()
            return cmd, env_override

        if operation == "checkout":
            if not args:
                raise ValueError("checkout requires a branch name or '-b new-branch'")
            cmd = f"git checkout {args}"
            return cmd, env_override

        if operation == "merge":
            if not args:
                raise ValueError("merge requires a branch name")
            cmd = f"git merge {args}"
            return cmd, env_override

        if operation == "diff":
            cmd = f"git diff {args}".strip()
            return cmd, env_override

        if operation == "log":
            if not args:
                args = "--oneline -20"
            cmd = f"git log {args}"
            return cmd, env_override

        if operation == "remote":
            cmd = f"git remote {args}".strip()
            return cmd, env_override

        if operation == "stash":
            cmd = f"git stash {args}".strip()
            return cmd, env_override

        if operation == "tag":
            cmd = f"git tag {args}".strip()
            return cmd, env_override

        if operation == "reset":
            if not args:
                raise ValueError("reset requires args, e.g. '--soft HEAD~1'")
            cmd = f"git reset {args}"
            return cmd, env_override

        raise ValueError(f"Unknown git operation: {operation}")

    def _credential_env(self, token: str) -> dict[str, str]:
        """Create environment variables that make git use the token for auth.

        Uses GIT_ASKPASS with a script that echoes the token, which is the
        most portable approach across Windows/macOS/Linux.
        """
        is_windows = platform.system() == "Windows"

        if is_windows:
            # On Windows, create a small helper that echoes the token
            # GIT_TERMINAL_PROMPT=0 prevents interactive prompts
            return {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "echo",
                # Use the token as the password via credential helper
                "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "credential.helper",
                "GIT_CONFIG_VALUE_0": "",
                "GIT_CONFIG_KEY_1": "http.extraHeader",
                "GIT_CONFIG_VALUE_1": f"Authorization: Bearer {token}",
            }
        else:
            return {
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Bearer {token}",
            }
