"""Workflow engine — chain PC actions into replayable sequences.

Allows the AI to record, save, and replay multi-step workflows.
Think of it as a macro system: "open Chrome, navigate to URL, fill form, click submit"
becomes a single replayable action.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("plutus.pc.workflow")


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    action: str                    # e.g., "mouse.click", "keyboard.type_text", "screen.wait_for_text"
    params: dict[str, Any] = field(default_factory=dict)
    delay_after: float = 0.3      # seconds to wait after this step
    description: str = ""         # human-readable description
    condition: str | None = None  # optional: "screen.has_text:Loading" — skip if condition not met
    on_fail: str = "stop"         # "stop", "skip", "retry"
    max_retries: int = 2
    timeout: float = 30.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "params": self.params,
            "delay_after": self.delay_after,
            "description": self.description,
            "condition": self.condition,
            "on_fail": self.on_fail,
            "max_retries": self.max_retries,
            "timeout": self.timeout,
        }


@dataclass
class WorkflowResult:
    """Result of executing a workflow."""
    success: bool = True
    steps_completed: int = 0
    steps_total: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "results": self.results,
            "errors": self.errors,
            "duration": round(self.duration, 2),
        }


@dataclass
class Workflow:
    """A named sequence of steps that can be saved and replayed."""
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "tags": self.tags,
            "step_count": len(self.steps),
        }


class WorkflowEngine:
    """Execute and manage multi-step PC workflows.

    Usage:
        engine = WorkflowEngine(mouse, keyboard, screen, windows)

        # Build a workflow
        wf = engine.create("open_google", "Open Google and search")
        wf.steps = [
            WorkflowStep("keyboard.shortcut", {"name": "new_tab"}, description="Open new tab"),
            WorkflowStep("keyboard.type_text", {"text": "https://google.com"}, description="Type URL"),
            WorkflowStep("keyboard.press", {"key": "enter"}, description="Navigate"),
            WorkflowStep("screen.wait_for_text", {"target": "Google", "timeout": 10}, description="Wait for page"),
            WorkflowStep("keyboard.type_text", {"text": "hello world"}, description="Type search"),
            WorkflowStep("keyboard.press", {"key": "enter"}, description="Search"),
        ]

        # Execute
        result = await engine.run(wf)

        # Save and reload
        engine.save(wf)
        loaded = engine.load("open_google")
        result = await engine.run(loaded)
    """

    def __init__(self, mouse=None, keyboard=None, screen=None, windows=None):
        self._mouse = mouse
        self._keyboard = keyboard
        self._screen = screen
        self._windows = windows
        self._workflows_dir = Path.home() / ".plutus" / "workflows"
        self._workflows_dir.mkdir(parents=True, exist_ok=True)
        self._running: dict[str, bool] = {}  # track running workflows for cancellation

    def set_controllers(self, mouse=None, keyboard=None, screen=None, windows=None):
        """Set or update the controllers (for lazy initialization)."""
        if mouse:
            self._mouse = mouse
        if keyboard:
            self._keyboard = keyboard
        if screen:
            self._screen = screen
        if windows:
            self._windows = windows

    def create(self, name: str, description: str = "", steps: list[WorkflowStep] | None = None) -> Workflow:
        """Create a new workflow."""
        return Workflow(
            name=name,
            description=description,
            steps=steps or [],
        )

    async def run(
        self,
        workflow: Workflow,
        dry_run: bool = False,
        on_step: Any = None,  # callback(step_index, step, result)
    ) -> WorkflowResult:
        """Execute a workflow step by step.

        Args:
            workflow: The workflow to execute
            dry_run: If True, just validate steps without executing
            on_step: Optional callback after each step
        """
        result = WorkflowResult(steps_total=len(workflow.steps))
        start_time = time.time()
        self._running[workflow.name] = True

        for i, step in enumerate(workflow.steps):
            # Check if cancelled
            if not self._running.get(workflow.name, False):
                result.errors.append(f"Workflow cancelled at step {i}")
                result.success = False
                break

            step_result: dict[str, Any] = {
                "step": i,
                "action": step.action,
                "description": step.description,
            }

            if dry_run:
                step_result["status"] = "dry_run"
                result.results.append(step_result)
                result.steps_completed += 1
                continue

            # Execute with retries
            retries = 0
            success = False

            while retries <= step.max_retries and not success:
                try:
                    action_result = await asyncio.wait_for(
                        self._execute_step(step),
                        timeout=step.timeout,
                    )
                    step_result["result"] = action_result
                    step_result["status"] = "success"
                    success = True
                except asyncio.TimeoutError:
                    step_result["status"] = "timeout"
                    step_result["error"] = f"Step timed out after {step.timeout}s"
                    retries += 1
                except Exception as e:
                    step_result["status"] = "error"
                    step_result["error"] = str(e)
                    retries += 1

                if not success and retries <= step.max_retries:
                    logger.warning(f"Step {i} failed, retry {retries}/{step.max_retries}")
                    await asyncio.sleep(0.5)

            result.results.append(step_result)

            if success:
                result.steps_completed += 1
            else:
                result.errors.append(f"Step {i} ({step.action}): {step_result.get('error', 'unknown')}")
                if step.on_fail == "stop":
                    result.success = False
                    break
                elif step.on_fail == "skip":
                    result.steps_completed += 1
                    continue

            # Delay between steps
            if step.delay_after > 0:
                await asyncio.sleep(step.delay_after)

            # Callback
            if on_step:
                try:
                    cb_result = on_step(i, step, step_result)
                    if asyncio.iscoroutine(cb_result):
                        await cb_result
                except Exception:
                    pass

        result.duration = time.time() - start_time
        self._running.pop(workflow.name, None)

        if result.steps_completed == result.steps_total:
            result.success = True

        return result

    async def _execute_step(self, step: WorkflowStep) -> dict[str, Any]:
        """Execute a single workflow step by dispatching to the right controller."""
        parts = step.action.split(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid action format: {step.action} (expected 'controller.method')")

        controller_name, method_name = parts

        # Resolve controller
        controllers = {
            "mouse": self._mouse,
            "keyboard": self._keyboard,
            "screen": self._screen,
            "windows": self._windows,
        }

        controller = controllers.get(controller_name)
        if controller is None:
            raise ValueError(f"Unknown controller: {controller_name}")

        method = getattr(controller, method_name, None)
        if method is None:
            raise ValueError(f"Unknown method: {controller_name}.{method_name}")

        # Call the method with params
        result = method(**step.params)
        if asyncio.iscoroutine(result):
            result = await result

        return result if isinstance(result, dict) else {"result": str(result)}

    def cancel(self, workflow_name: str) -> bool:
        """Cancel a running workflow."""
        if workflow_name in self._running:
            self._running[workflow_name] = False
            return True
        return False

    # ─── Persistence ───

    def save(self, workflow: Workflow) -> str:
        """Save a workflow to disk."""
        path = self._workflows_dir / f"{workflow.name}.json"
        path.write_text(json.dumps(workflow.to_dict(), indent=2))
        return str(path)

    def load(self, name: str) -> Workflow | None:
        """Load a workflow from disk."""
        path = self._workflows_dir / f"{name}.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        steps = [
            WorkflowStep(**s) for s in data.get("steps", [])
        ]
        return Workflow(
            name=data["name"],
            description=data.get("description", ""),
            steps=steps,
            created_at=data.get("created_at", 0),
            tags=data.get("tags", []),
        )

    def list_workflows(self) -> list[dict[str, Any]]:
        """List all saved workflows."""
        workflows = []
        for path in sorted(self._workflows_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                workflows.append({
                    "name": data.get("name", path.stem),
                    "description": data.get("description", ""),
                    "step_count": data.get("step_count", len(data.get("steps", []))),
                    "tags": data.get("tags", []),
                    "created_at": data.get("created_at", 0),
                })
            except Exception:
                continue
        return workflows

    def delete(self, name: str) -> bool:
        """Delete a saved workflow."""
        path = self._workflows_dir / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ─── Pre-built Workflows ───

    def get_template(self, template_name: str) -> Workflow | None:
        """Get a pre-built workflow template."""
        templates = {
            "open_url": self._template_open_url,
            "screenshot_and_ocr": self._template_screenshot_ocr,
            "find_and_click": self._template_find_and_click,
            "fill_form": self._template_fill_form,
            "switch_and_type": self._template_switch_and_type,
        }
        builder = templates.get(template_name)
        return builder() if builder else None

    def list_templates(self) -> list[dict[str, str]]:
        """List available workflow templates."""
        return [
            {"name": "open_url", "description": "Open a URL in the browser"},
            {"name": "screenshot_and_ocr", "description": "Take a screenshot and read all text"},
            {"name": "find_and_click", "description": "Find text on screen and click it"},
            {"name": "fill_form", "description": "Fill a form field with text"},
            {"name": "switch_and_type", "description": "Switch to a window and type text"},
        ]

    def _template_open_url(self) -> Workflow:
        return Workflow(
            name="open_url",
            description="Open a URL in the default browser",
            steps=[
                WorkflowStep("keyboard.shortcut", {"name": "new_tab"}, description="Open new tab", delay_after=0.5),
                WorkflowStep("keyboard.shortcut", {"name": "address_bar"}, description="Focus address bar", delay_after=0.3),
                WorkflowStep("keyboard.type_text", {"text": "https://example.com", "speed": "fast"}, description="Type URL"),
                WorkflowStep("keyboard.press", {"key": "enter"}, description="Navigate", delay_after=2.0),
            ],
            tags=["browser", "navigation"],
        )

    def _template_screenshot_ocr(self) -> Workflow:
        return Workflow(
            name="screenshot_and_ocr",
            description="Capture the screen and read all visible text",
            steps=[
                WorkflowStep("screen.capture", {}, description="Take screenshot", delay_after=0.5),
                WorkflowStep("screen.read_text", {}, description="OCR the screen"),
            ],
            tags=["screen", "ocr"],
        )

    def _template_find_and_click(self) -> Workflow:
        return Workflow(
            name="find_and_click",
            description="Find text on screen and click its center",
            steps=[
                WorkflowStep("screen.find_text", {"target": "Button"}, description="Find target text"),
            ],
            tags=["screen", "click"],
        )

    def _template_fill_form(self) -> Workflow:
        return Workflow(
            name="fill_form",
            description="Click a field and type text into it",
            steps=[
                WorkflowStep("mouse.click", {"x": 500, "y": 300}, description="Click input field", delay_after=0.3),
                WorkflowStep("keyboard.shortcut", {"name": "select_all"}, description="Select existing text", delay_after=0.1),
                WorkflowStep("keyboard.type_text", {"text": "Hello World"}, description="Type new text"),
            ],
            tags=["form", "input"],
        )

    def _template_switch_and_type(self) -> Workflow:
        return Workflow(
            name="switch_and_type",
            description="Switch to a window and type text",
            steps=[
                WorkflowStep("windows.focus", {"query": "Notepad"}, description="Focus window", delay_after=0.5),
                WorkflowStep("keyboard.type_text", {"text": "Hello from Plutus!"}, description="Type text"),
            ],
            tags=["window", "typing"],
        )
