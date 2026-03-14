"""GitHub connector for Plutus.

Uses the GitHub REST API to manage repositories, issues, pull requests,
branches, and files:
  - List, create, and manage repositories
  - Create, update, close, and comment on issues
  - Create, merge, and review pull requests
  - Create, delete, and list branches
  - Read, create, update, and delete files in repos
  - List commits, releases, and workflows
  - Fork repos and manage collaborators

Setup:
  1. Go to https://github.com/settings/tokens → Generate new token (classic)
  2. Select scopes: repo, workflow, read:org (or use fine-grained tokens)
  3. Enter the token in the Plutus Connectors tab
  4. Optionally set a default owner/repo for convenience

Architecture:
  - Pure REST API connector (no polling or gateway needed)
  - All operations go through _api_call() with proper error handling
  - File content is base64-encoded/decoded per GitHub API requirements
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from plutus.connectors.base import BaseConnector

logger = logging.getLogger("plutus.connectors.github")

GITHUB_API = "https://api.github.com"


class GitHubConnector(BaseConnector):
    name = "github"
    display_name = "GitHub"
    description = "Manage repositories, issues, PRs, branches, and files on GitHub"
    icon = "GitBranch"
    category = "developer"

    def __init__(self):
        super().__init__()
        self._session = None

    def _sensitive_fields(self) -> list[str]:
        return ["personal_access_token"]

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "personal_access_token",
                "label": "Personal Access Token",
                "type": "password",
                "required": True,
                "placeholder": "ghp_... or github_pat_...",
                "help": (
                    "Generate at github.com/settings/tokens — "
                    "needs 'repo' scope for full access"
                ),
            },
            {
                "name": "default_owner",
                "label": "Default Owner",
                "type": "text",
                "required": False,
                "placeholder": "username or org",
                "help": "Default repository owner (can be overridden per request)",
            },
            {
                "name": "default_repo",
                "label": "Default Repository",
                "type": "text",
                "required": False,
                "placeholder": "my-repo",
                "help": "Default repository name (can be overridden per request)",
            },
        ]

    @property
    def _token(self) -> str:
        return self._config.get("personal_access_token", "")

    @property
    def _owner(self) -> str:
        return self._config.get("default_owner", "")

    @property
    def _repo(self) -> str:
        return self._config.get("default_repo", "")

    def _resolve(
        self, owner: str | None, repo: str | None
    ) -> tuple[str, str]:
        """Resolve owner/repo, falling back to defaults."""
        o = owner or self._owner
        r = repo or self._repo
        if not o or not r:
            raise ValueError(
                "owner and repo are required — set defaults in connector config "
                "or pass them explicitly"
            )
        return o, r

    async def _get_session(self):
        """Get or create an aiohttp session for API calls."""
        import aiohttp

        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def _api_call(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any] | list[Any]:
        """Make a GitHub REST API call."""
        session = await self._get_session()
        url = f"{GITHUB_API}{path}"
        try:
            async with session.request(
                method, url, json=json, params=params
            ) as resp:
                if resp.status == 204:
                    return {"success": True}
                data = await resp.json()
                if resp.status >= 400:
                    msg = data.get("message", str(data))
                    logger.error(f"GitHub API error ({method} {path}): {msg}")
                    raise Exception(f"GitHub API error: {msg}")
                return data
        except Exception as e:
            if "GitHub API error" in str(e):
                raise
            logger.error(f"GitHub HTTP error ({method} {path}): {e}")
            raise

    async def test_connection(self) -> dict[str, Any]:
        """Test the token by calling /user."""
        if not self._token:
            return {"success": False, "message": "Personal access token is required"}

        try:
            user = await self._api_call("GET", "/user")
            username = user.get("login", "")
            name = user.get("name", "")

            self._config["username"] = username
            self._config_store.save(self._config)

            display = f"{name} (@{username})" if name else f"@{username}"
            result: dict[str, Any] = {
                "success": True,
                "message": f"Authenticated as {display}",
                "username": username,
            }

            # Show rate limit info
            try:
                rate = await self._api_call("GET", "/rate_limit")
                core = rate.get("resources", {}).get("core", {})
                remaining = core.get("remaining", "?")
                limit = core.get("limit", "?")
                result["message"] += f" — API rate: {remaining}/{limit}"
            except Exception:
                pass

            return result

        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}
        finally:
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    async def send_message(self, text: str, **kwargs: Any) -> dict[str, Any]:
        """Create a GitHub issue with the text as the body.

        This satisfies the BaseConnector interface — for GitHub, 'sending a
        message' means creating an issue.
        """
        owner = kwargs.get("owner")
        repo = kwargs.get("repo")
        title = kwargs.get("title", text[:80])
        try:
            return await self.create_issue(
                title=title, body=text, owner=owner, repo=repo
            )
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def stop(self) -> None:
        """Stop the connector and close the HTTP session."""
        await super().stop()
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Repository operations ─────────────────────────────────

    async def list_repos(
        self,
        owner: str | None = None,
        repo_type: str = "owner",
        sort: str = "updated",
        per_page: int = 30,
    ) -> dict[str, Any]:
        """List repositories for the authenticated user or a specific owner."""
        try:
            if owner:
                repos = await self._api_call(
                    "GET",
                    f"/users/{owner}/repos",
                    params={"sort": sort, "per_page": per_page},
                )
            else:
                repos = await self._api_call(
                    "GET",
                    "/user/repos",
                    params={
                        "type": repo_type,
                        "sort": sort,
                        "per_page": per_page,
                    },
                )
            summary = [
                {
                    "name": r["full_name"],
                    "description": r.get("description", ""),
                    "private": r["private"],
                    "language": r.get("language"),
                    "stars": r.get("stargazers_count", 0),
                    "updated_at": r.get("updated_at", ""),
                    "default_branch": r.get("default_branch", "main"),
                }
                for r in repos
            ]
            return {"success": True, "repos": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_repo(
        self, owner: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Get detailed information about a repository."""
        try:
            o, r = self._resolve(owner, repo)
            data = await self._api_call("GET", f"/repos/{o}/{r}")
            return {"success": True, "repo": data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_repo(
        self,
        name: str,
        description: str = "",
        private: bool = True,
        auto_init: bool = True,
    ) -> dict[str, Any]:
        """Create a new repository for the authenticated user."""
        try:
            payload: dict[str, Any] = {
                "name": name,
                "description": description,
                "private": private,
                "auto_init": auto_init,
            }
            data = await self._api_call("POST", "/user/repos", json=payload)
            return {
                "success": True,
                "message": f"Created repository {data['full_name']}",
                "repo": data["full_name"],
                "url": data["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def delete_repo(
        self, owner: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Delete a repository (requires delete_repo scope)."""
        try:
            o, r = self._resolve(owner, repo)
            await self._api_call("DELETE", f"/repos/{o}/{r}")
            return {"success": True, "message": f"Deleted repository {o}/{r}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def fork_repo(
        self, owner: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Fork a repository."""
        try:
            o, r = self._resolve(owner, repo)
            data = await self._api_call("POST", f"/repos/{o}/{r}/forks")
            return {
                "success": True,
                "message": f"Forked {o}/{r} → {data['full_name']}",
                "fork": data["full_name"],
                "url": data["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Issue operations ──────────────────────────────────────

    async def list_issues(
        self,
        state: str = "open",
        labels: str = "",
        per_page: int = 30,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List issues in a repository."""
        try:
            o, r = self._resolve(owner, repo)
            params: dict[str, Any] = {"state": state, "per_page": per_page}
            if labels:
                params["labels"] = labels
            issues = await self._api_call(
                "GET", f"/repos/{o}/{r}/issues", params=params
            )
            summary = [
                {
                    "number": i["number"],
                    "title": i["title"],
                    "state": i["state"],
                    "author": i["user"]["login"],
                    "labels": [la["name"] for la in i.get("labels", [])],
                    "comments": i.get("comments", 0),
                    "created_at": i["created_at"],
                    "is_pr": "pull_request" in i,
                }
                for i in issues
            ]
            return {"success": True, "issues": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_issue(
        self,
        issue_number: int,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Get a single issue with its details."""
        try:
            o, r = self._resolve(owner, repo)
            issue = await self._api_call(
                "GET", f"/repos/{o}/{r}/issues/{issue_number}"
            )
            return {"success": True, "issue": issue}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_issue(
        self,
        title: str,
        body: str = "",
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Create a new issue."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {"title": title, "body": body}
            if labels:
                payload["labels"] = labels
            if assignees:
                payload["assignees"] = assignees
            issue = await self._api_call(
                "POST", f"/repos/{o}/{r}/issues", json=payload
            )
            return {
                "success": True,
                "message": f"Created issue #{issue['number']}: {title}",
                "number": issue["number"],
                "url": issue["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def update_issue(
        self,
        issue_number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {}
            if title is not None:
                payload["title"] = title
            if body is not None:
                payload["body"] = body
            if state is not None:
                payload["state"] = state
            if labels is not None:
                payload["labels"] = labels
            if assignees is not None:
                payload["assignees"] = assignees
            if not payload:
                return {"success": False, "message": "No fields to update"}
            issue = await self._api_call(
                "PATCH", f"/repos/{o}/{r}/issues/{issue_number}", json=payload
            )
            return {
                "success": True,
                "message": f"Updated issue #{issue_number}",
                "url": issue["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def comment_on_issue(
        self,
        issue_number: int,
        body: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Add a comment to an issue or pull request."""
        try:
            o, r = self._resolve(owner, repo)
            comment = await self._api_call(
                "POST",
                f"/repos/{o}/{r}/issues/{issue_number}/comments",
                json={"body": body},
            )
            return {
                "success": True,
                "message": f"Commented on #{issue_number}",
                "comment_id": comment["id"],
                "url": comment["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Pull request operations ───────────────────────────────

    async def list_pull_requests(
        self,
        state: str = "open",
        per_page: int = 30,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List pull requests in a repository."""
        try:
            o, r = self._resolve(owner, repo)
            prs = await self._api_call(
                "GET",
                f"/repos/{o}/{r}/pulls",
                params={"state": state, "per_page": per_page},
            )
            summary = [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "author": pr["user"]["login"],
                    "head": pr["head"]["ref"],
                    "base": pr["base"]["ref"],
                    "draft": pr.get("draft", False),
                    "mergeable": pr.get("mergeable"),
                    "created_at": pr["created_at"],
                }
                for pr in prs
            ]
            return {"success": True, "pull_requests": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_pull_request(
        self,
        pr_number: int,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Get detailed info about a pull request."""
        try:
            o, r = self._resolve(owner, repo)
            pr = await self._api_call(
                "GET", f"/repos/{o}/{r}/pulls/{pr_number}"
            )
            return {"success": True, "pull_request": pr}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_pull_request(
        self,
        title: str,
        head: str,
        base: str,
        body: str = "",
        draft: bool = False,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Create a new pull request."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {
                "title": title,
                "head": head,
                "base": base,
                "body": body,
                "draft": draft,
            }
            pr = await self._api_call(
                "POST", f"/repos/{o}/{r}/pulls", json=payload
            )
            return {
                "success": True,
                "message": f"Created PR #{pr['number']}: {title}",
                "number": pr["number"],
                "url": pr["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def merge_pull_request(
        self,
        pr_number: int,
        merge_method: str = "merge",
        commit_title: str = "",
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Merge a pull request. merge_method: merge, squash, or rebase."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {"merge_method": merge_method}
            if commit_title:
                payload["commit_title"] = commit_title
            result = await self._api_call(
                "PUT", f"/repos/{o}/{r}/pulls/{pr_number}/merge", json=payload
            )
            return {
                "success": True,
                "message": f"Merged PR #{pr_number} via {merge_method}",
                "sha": result.get("sha", ""),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def review_pull_request(
        self,
        pr_number: int,
        event: str = "COMMENT",
        body: str = "",
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Submit a review on a pull request. event: APPROVE, REQUEST_CHANGES, COMMENT."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {"event": event}
            if body:
                payload["body"] = body
            review = await self._api_call(
                "POST",
                f"/repos/{o}/{r}/pulls/{pr_number}/reviews",
                json=payload,
            )
            return {
                "success": True,
                "message": f"Submitted {event} review on PR #{pr_number}",
                "review_id": review.get("id"),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Branch operations ─────────────────────────────────────

    async def list_branches(
        self,
        per_page: int = 30,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List branches in a repository."""
        try:
            o, r = self._resolve(owner, repo)
            branches = await self._api_call(
                "GET",
                f"/repos/{o}/{r}/branches",
                params={"per_page": per_page},
            )
            summary = [
                {
                    "name": b["name"],
                    "sha": b["commit"]["sha"][:8],
                    "protected": b.get("protected", False),
                }
                for b in branches
            ]
            return {"success": True, "branches": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_branch(
        self,
        branch_name: str,
        from_branch: str = "main",
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Create a new branch from an existing branch."""
        try:
            o, r = self._resolve(owner, repo)
            # Get the SHA of the source branch
            ref = await self._api_call(
                "GET", f"/repos/{o}/{r}/git/ref/heads/{from_branch}"
            )
            sha = ref["object"]["sha"]
            # Create the new branch
            await self._api_call(
                "POST",
                f"/repos/{o}/{r}/git/refs",
                json={"ref": f"refs/heads/{branch_name}", "sha": sha},
            )
            return {
                "success": True,
                "message": f"Created branch '{branch_name}' from '{from_branch}'",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def delete_branch(
        self,
        branch_name: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Delete a branch."""
        try:
            o, r = self._resolve(owner, repo)
            await self._api_call(
                "DELETE", f"/repos/{o}/{r}/git/refs/heads/{branch_name}"
            )
            return {
                "success": True,
                "message": f"Deleted branch '{branch_name}'",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── File operations ───────────────────────────────────────

    async def get_file(
        self,
        path: str,
        ref: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Get file contents from a repository."""
        try:
            o, r = self._resolve(owner, repo)
            params = {}
            if ref:
                params["ref"] = ref
            data = await self._api_call(
                "GET", f"/repos/{o}/{r}/contents/{path}", params=params or None
            )
            if isinstance(data, list):
                # It's a directory listing
                entries = [
                    {
                        "name": e["name"],
                        "type": e["type"],
                        "path": e["path"],
                        "size": e.get("size", 0),
                    }
                    for e in data
                ]
                return {"success": True, "type": "directory", "entries": entries}

            # It's a file
            content = ""
            if data.get("encoding") == "base64" and data.get("content"):
                content = base64.b64decode(data["content"]).decode("utf-8")

            return {
                "success": True,
                "type": "file",
                "content": content,
                "sha": data.get("sha", ""),
                "size": data.get("size", 0),
                "path": data.get("path", path),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_or_update_file(
        self,
        path: str,
        content: str,
        message: str,
        branch: str | None = None,
        sha: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Create or update a file in a repository.

        For updates, provide the sha of the existing file (get it via get_file).
        """
        try:
            o, r = self._resolve(owner, repo)
            encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
            payload: dict[str, Any] = {
                "message": message,
                "content": encoded,
            }
            if branch:
                payload["branch"] = branch
            if sha:
                payload["sha"] = sha

            result = await self._api_call(
                "PUT", f"/repos/{o}/{r}/contents/{path}", json=payload
            )
            action = "Updated" if sha else "Created"
            return {
                "success": True,
                "message": f"{action} file {path}",
                "sha": result.get("content", {}).get("sha", ""),
                "commit_sha": result.get("commit", {}).get("sha", ""),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def delete_file(
        self,
        path: str,
        message: str,
        sha: str,
        branch: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Delete a file from a repository. Requires the file's current sha."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {"message": message, "sha": sha}
            if branch:
                payload["branch"] = branch
            await self._api_call(
                "DELETE", f"/repos/{o}/{r}/contents/{path}", json=payload
            )
            return {"success": True, "message": f"Deleted file {path}"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Commit & release operations ───────────────────────────

    async def list_commits(
        self,
        branch: str | None = None,
        per_page: int = 20,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List recent commits."""
        try:
            o, r = self._resolve(owner, repo)
            params: dict[str, Any] = {"per_page": per_page}
            if branch:
                params["sha"] = branch
            commits = await self._api_call(
                "GET", f"/repos/{o}/{r}/commits", params=params
            )
            summary = [
                {
                    "sha": c["sha"][:8],
                    "message": c["commit"]["message"].split("\n")[0],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                }
                for c in commits
            ]
            return {"success": True, "commits": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def list_releases(
        self,
        per_page: int = 10,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List releases in a repository."""
        try:
            o, r = self._resolve(owner, repo)
            releases = await self._api_call(
                "GET",
                f"/repos/{o}/{r}/releases",
                params={"per_page": per_page},
            )
            summary = [
                {
                    "tag": rel["tag_name"],
                    "name": rel.get("name", ""),
                    "draft": rel.get("draft", False),
                    "prerelease": rel.get("prerelease", False),
                    "published_at": rel.get("published_at", ""),
                }
                for rel in releases
            ]
            return {"success": True, "releases": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_release(
        self,
        tag_name: str,
        name: str = "",
        body: str = "",
        draft: bool = False,
        prerelease: bool = False,
        target: str = "main",
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Create a new release."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {
                "tag_name": tag_name,
                "name": name or tag_name,
                "body": body,
                "draft": draft,
                "prerelease": prerelease,
                "target_commitish": target,
            }
            release = await self._api_call(
                "POST", f"/repos/{o}/{r}/releases", json=payload
            )
            return {
                "success": True,
                "message": f"Created release {tag_name}",
                "url": release["html_url"],
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Workflow operations ───────────────────────────────────

    async def list_workflows(
        self,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List GitHub Actions workflows."""
        try:
            o, r = self._resolve(owner, repo)
            data = await self._api_call(
                "GET", f"/repos/{o}/{r}/actions/workflows"
            )
            workflows = data.get("workflows", [])
            summary = [
                {
                    "id": w["id"],
                    "name": w["name"],
                    "state": w.get("state", ""),
                    "path": w.get("path", ""),
                }
                for w in workflows
            ]
            return {"success": True, "workflows": summary}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def list_workflow_runs(
        self,
        workflow_id: int | str | None = None,
        status: str | None = None,
        per_page: int = 10,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List workflow runs, optionally filtered by workflow and status."""
        try:
            o, r = self._resolve(owner, repo)
            if workflow_id:
                path = f"/repos/{o}/{r}/actions/workflows/{workflow_id}/runs"
            else:
                path = f"/repos/{o}/{r}/actions/runs"
            params: dict[str, Any] = {"per_page": per_page}
            if status:
                params["status"] = status
            data = await self._api_call("GET", path, params=params)
            runs = data.get("workflow_runs", [])
            summary = [
                {
                    "id": run["id"],
                    "name": run.get("name", ""),
                    "status": run["status"],
                    "conclusion": run.get("conclusion"),
                    "branch": run["head_branch"],
                    "created_at": run["created_at"],
                    "url": run["html_url"],
                }
                for run in runs
            ]
            return {"success": True, "runs": summary, "count": len(summary)}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def trigger_workflow(
        self,
        workflow_id: int | str,
        ref: str = "main",
        inputs: dict[str, str] | None = None,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Trigger a workflow dispatch event."""
        try:
            o, r = self._resolve(owner, repo)
            payload: dict[str, Any] = {"ref": ref}
            if inputs:
                payload["inputs"] = inputs
            await self._api_call(
                "POST",
                f"/repos/{o}/{r}/actions/workflows/{workflow_id}/dispatches",
                json=payload,
            )
            return {
                "success": True,
                "message": f"Triggered workflow {workflow_id} on {ref}",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Collaborator operations ───────────────────────────────

    async def list_collaborators(
        self,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """List collaborators on a repository."""
        try:
            o, r = self._resolve(owner, repo)
            collabs = await self._api_call(
                "GET", f"/repos/{o}/{r}/collaborators"
            )
            summary = [
                {
                    "login": c["login"],
                    "permissions": c.get("permissions", {}),
                    "role_name": c.get("role_name", ""),
                }
                for c in collabs
            ]
            return {"success": True, "collaborators": summary}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def add_collaborator(
        self,
        username: str,
        permission: str = "push",
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Add a collaborator to a repository. permission: pull, push, admin."""
        try:
            o, r = self._resolve(owner, repo)
            await self._api_call(
                "PUT",
                f"/repos/{o}/{r}/collaborators/{username}",
                json={"permission": permission},
            )
            return {
                "success": True,
                "message": f"Invited {username} as {permission} collaborator",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def remove_collaborator(
        self,
        username: str,
        owner: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Remove a collaborator from a repository."""
        try:
            o, r = self._resolve(owner, repo)
            await self._api_call(
                "DELETE", f"/repos/{o}/{r}/collaborators/{username}"
            )
            return {
                "success": True,
                "message": f"Removed {username} from collaborators",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Search operations ─────────────────────────────────────

    async def search_repos(
        self, query: str, per_page: int = 10
    ) -> dict[str, Any]:
        """Search GitHub repositories."""
        try:
            data = await self._api_call(
                "GET",
                "/search/repositories",
                params={"q": query, "per_page": per_page},
            )
            repos = data.get("items", [])
            summary = [
                {
                    "name": r["full_name"],
                    "description": r.get("description", ""),
                    "stars": r.get("stargazers_count", 0),
                    "language": r.get("language"),
                    "url": r["html_url"],
                }
                for r in repos
            ]
            return {
                "success": True,
                "repos": summary,
                "total_count": data.get("total_count", 0),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def search_code(
        self,
        query: str,
        owner: str | None = None,
        repo: str | None = None,
        per_page: int = 10,
    ) -> dict[str, Any]:
        """Search code across GitHub or within a specific repo."""
        try:
            q = query
            if owner and repo:
                q = f"{query} repo:{owner}/{repo}"
            elif owner:
                q = f"{query} user:{owner}"
            data = await self._api_call(
                "GET",
                "/search/code",
                params={"q": q, "per_page": per_page},
            )
            items = data.get("items", [])
            summary = [
                {
                    "path": i["path"],
                    "repo": i["repository"]["full_name"],
                    "url": i["html_url"],
                }
                for i in items
            ]
            return {
                "success": True,
                "results": summary,
                "total_count": data.get("total_count", 0),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}
