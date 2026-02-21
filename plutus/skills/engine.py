"""Skill Engine — executes pre-built app workflows step-by-step.

A skill is a reliable, tested sequence of pc tool operations for a specific
task in a specific app. Instead of the LLM guessing how to navigate WhatsApp,
it follows a proven recipe.

The engine:
  1. Receives a skill name + parameters from the LLM
  2. Looks up the skill in the registry
  3. Executes each step via the pc tool
  4. Handles errors, retries, and waits between steps
  5. Returns a structured result
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger("plutus.skills.engine")


@dataclass
class SkillStep:
    """A single step in a skill execution."""
    description: str
    operation: str
    params: dict[str, Any] = field(default_factory=dict)
    wait_after: float = 1.0  # seconds to wait after this step
    retry_on_fail: bool = False
    max_retries: int = 2
    optional: bool = False  # if True, failure doesn't stop the skill
    condition: str | None = None  # optional condition description


@dataclass
class SkillResult:
    """Result of a skill execution."""
    success: bool
    skill_name: str
    steps_completed: int
    steps_total: int
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    duration: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "skill_name": self.skill_name,
            "steps_completed": self.steps_completed,
            "steps_total": self.steps_total,
            "results": self.results,
            "error": self.error,
            "duration_seconds": round(self.duration, 2),
        }


class SkillDefinition:
    """A complete skill definition with metadata and steps.
    
    Subclasses override build_steps() to create dynamic step lists
    based on the provided parameters.
    """

    name: str = ""
    description: str = ""
    app: str = ""  # primary app this skill targets
    triggers: list[str] = []  # keywords that trigger this skill
    category: str = "general"  # whatsapp, calendar, email, music, files, etc.
    required_params: list[str] = []
    optional_params: list[str] = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        """Build the step list based on parameters. Override in subclasses."""
        return []

    def validate_params(self, params: dict[str, Any]) -> tuple[bool, str]:
        """Check that all required params are provided."""
        missing = [p for p in self.required_params if p not in params or not params[p]]
        if missing:
            return False, f"Missing required parameters: {', '.join(missing)}"
        return True, ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "app": self.app,
            "triggers": self.triggers,
            "category": self.category,
            "required_params": self.required_params,
            "optional_params": self.optional_params,
        }


class SkillEngine:
    """Executes skills step-by-step using the pc tool."""

    def __init__(self, pc_tool_executor: Callable[..., Awaitable[str]]):
        """
        Args:
            pc_tool_executor: async function that executes pc tool operations.
                              Signature: async def execute(**kwargs) -> str
        """
        self._execute_pc = pc_tool_executor
        self._running: dict[str, bool] = {}  # skill_name -> is_running

    async def run(
        self,
        skill: SkillDefinition,
        params: dict[str, Any],
        on_step: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> SkillResult:
        """Execute a skill step-by-step.
        
        Args:
            skill: The skill definition to execute
            params: Parameters for the skill (e.g., contact_name, message)
            on_step: Optional callback called before each step with (step_index, description)
        """
        # Validate parameters
        valid, error = skill.validate_params(params)
        if not valid:
            return SkillResult(
                success=False,
                skill_name=skill.name,
                steps_completed=0,
                steps_total=0,
                error=error,
            )

        # Build steps
        steps = skill.build_steps(params)
        if not steps:
            return SkillResult(
                success=False,
                skill_name=skill.name,
                steps_completed=0,
                steps_total=0,
                error="Skill produced no steps",
            )

        self._running[skill.name] = True
        start_time = time.time()
        results = []
        steps_completed = 0

        for i, step in enumerate(steps):
            if not self._running.get(skill.name, False):
                return SkillResult(
                    success=False,
                    skill_name=skill.name,
                    steps_completed=steps_completed,
                    steps_total=len(steps),
                    results=results,
                    error="Skill cancelled",
                    duration=time.time() - start_time,
                )

            # Notify about current step
            if on_step:
                try:
                    await on_step(i, step.description)
                except Exception:
                    pass

            logger.info(f"[{skill.name}] Step {i+1}/{len(steps)}: {step.description}")

            # Execute the step with retries
            step_result = await self._execute_step(step)
            results.append({
                "step": i,
                "description": step.description,
                "operation": step.operation,
                "result": step_result,
            })

            # Check for failure
            if isinstance(step_result, dict) and step_result.get("error"):
                if step.optional:
                    logger.warning(f"[{skill.name}] Optional step {i+1} failed: {step_result['error']}")
                else:
                    logger.error(f"[{skill.name}] Step {i+1} failed: {step_result['error']}")
                    self._running.pop(skill.name, None)
                    return SkillResult(
                        success=False,
                        skill_name=skill.name,
                        steps_completed=steps_completed,
                        steps_total=len(steps),
                        results=results,
                        error=f"Step {i+1} failed: {step_result.get('error')}",
                        duration=time.time() - start_time,
                    )

            steps_completed += 1

            # Wait between steps
            if step.wait_after > 0 and i < len(steps) - 1:
                await asyncio.sleep(step.wait_after)

        self._running.pop(skill.name, None)
        return SkillResult(
            success=True,
            skill_name=skill.name,
            steps_completed=steps_completed,
            steps_total=len(steps),
            results=results,
            duration=time.time() - start_time,
        )

    async def _execute_step(self, step: SkillStep) -> dict:
        """Execute a single skill step via the pc tool."""
        attempts = 1 + (step.max_retries if step.retry_on_fail else 0)

        for attempt in range(attempts):
            try:
                result_str = await self._execute_pc(
                    operation=step.operation,
                    **step.params,
                )
                try:
                    result = json.loads(result_str)
                except (json.JSONDecodeError, TypeError):
                    result = {"raw": str(result_str)}

                # Check if the result indicates an error
                if isinstance(result, dict) and result.get("error"):
                    if attempt < attempts - 1:
                        logger.warning(
                            f"Step failed (attempt {attempt+1}/{attempts}): {result['error']}"
                        )
                        await asyncio.sleep(1.0)
                        continue
                return result

            except Exception as e:
                if attempt < attempts - 1:
                    logger.warning(f"Step exception (attempt {attempt+1}/{attempts}): {e}")
                    await asyncio.sleep(1.0)
                    continue
                return {"error": str(e)}

        return {"error": "All retry attempts exhausted"}

    def cancel(self, skill_name: str) -> bool:
        """Cancel a running skill."""
        if skill_name in self._running:
            self._running[skill_name] = False
            return True
        return False
