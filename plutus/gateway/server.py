"""Plutus Gateway Server.

Plutus v0.3.2 — Multi-model, multi-worker, scheduled agent.

Architecture:
  - Model Router: auto-selects Claude Opus/Sonnet/Haiku or GPT-5.2 per task
  - Worker Pool: concurrent agent workers with configurable max concurrency
  - Scheduler: persistent cron-based task scheduling
  - Standard Agent: LLM + function-calling with accessibility tree snapshots
  - Computer Use Agent: Anthropic native (explicit only)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from plutus.config import PlutusConfig, SecretsStore
from plutus.core.agent import AgentEvent, AgentRuntime
from plutus.core.heartbeat import HeartbeatRunner
from plutus.core.memory import MemoryStore
from plutus.core.model_router import ModelRouter, ModelRoutingConfig
from plutus.core.scheduler import Scheduler, ScheduledJob
from plutus.core.worker_pool import WorkerPool, WorkerTask, WorkerStatus, WorkerState
from plutus.gateway.routes import create_router
from plutus.gateway.ws import create_ws_router, manager as ws_manager
from plutus.guardrails.engine import GuardrailEngine
from plutus.tools.registry import create_default_registry

logger = logging.getLogger("plutus.gateway")

# Shared application state
_state: dict[str, Any] = {}

# Lock to prevent concurrent agent.process_message() calls
# (e.g. heartbeat firing while user message is being processed)
_agent_lock = asyncio.Lock()


def get_state() -> dict[str, Any]:
    return _state


# ── Heartbeat callbacks ──────────────────────────────────────────────────────

async def _heartbeat_on_beat(prompt: str) -> None:
    """Called by the heartbeat runner — sends a synthetic message through the agent."""
    agent: AgentRuntime | None = _state.get("agent")
    if not agent:
        return
    # Use the lock to prevent concurrent process_message calls
    # (e.g. heartbeat firing while a user message is being processed)
    if _agent_lock.locked():
        logger.debug("Skipping heartbeat — agent is busy processing")
        return
    try:
        async with _agent_lock:
            async for event in agent.process_message(prompt):
                await ws_manager.broadcast(event.to_dict())
    except Exception as e:
        logger.exception("Heartbeat agent processing failed")
        await ws_manager.broadcast({
            "type": "error",
            "message": f"Heartbeat error: {e}",
        })


async def _heartbeat_on_event(event_data: dict[str, Any]) -> None:
    await ws_manager.broadcast(event_data)


# ── Worker executor ──────────────────────────────────────────────────────────

async def _worker_executor(task: WorkerTask, on_status: Any, *, deadline: float | None = None) -> str:
    """Execute a worker task with an independent multi-turn agent loop.

    Workers have access to ALL tools from the registry and can make multiple
    LLM calls in a loop (just like the coordinator), but they:
      - Have their OWN conversation context (no pollution)
      - Run independently (no self-await deadlocks)
      - Bypass guardrails (the coordinator already approved the spawn)
      - Have a configurable max tool rounds to prevent runaway workers
    """
    import json as _json
    import litellm

    config = _state.get("config")
    model_router: ModelRouter | None = _state.get("model_router")
    tool_registry = _state.get("tool_registry")

    # Select model for this worker
    model_string = "anthropic/claude-sonnet-4-6"  # fallback
    model_display = "Claude Sonnet 4-6"
    _worker_is_openai = False

    if model_router:
        spec = model_router.select_for_worker(task.prompt, model_key=task.model_key)
        model_string = model_router.get_litellm_model_string(spec)
        model_display = spec.display_name
        _worker_is_openai = (spec.provider == "openai")
        logger.info(f"Worker {task.id} selected model: {model_string} (openai={_worker_is_openai})")
        # Record usage
        try:
            from plutus.core.model_router import AVAILABLE_MODELS
            for key, s in AVAILABLE_MODELS.items():
                if s.id == spec.id:
                    model_router.record_usage(key)
                    break
        except Exception:
            pass

    # Update status
    status = WorkerStatus(
        task_id=task.id,
        state=WorkerState.RUNNING,
        name=task.name,
        current_step="Processing task...",
        model_used=model_display,
    )
    await on_status(status)

    # Broadcast to UI
    await ws_manager.broadcast({
        "type": "worker_started",
        "worker": {"task_id": task.id, "name": task.name, "model": model_display},
    })

    # Build tool definitions from the registry (exclude 'worker' to prevent recursion)
    # OpenAI Chat Completions (via litellm) uses the nested format, same as Anthropic.
    # The flat Responses API format is only needed when calling OpenAI SDK directly.
    tools_for_llm = []
    if tool_registry:
        for tool in tool_registry._tools.values():
            if tool.name == "worker":  # prevent workers from spawning workers
                continue
            try:
                defn = tool.get_definition()
                tools_for_llm.append({
                    "type": "function",
                    "function": {
                        "name": defn.name,
                        "description": defn.description,
                        "parameters": defn.parameters,
                    },
                })
            except Exception:
                pass

    # Inject Anthropic server-side web search/fetch tools for workers too
    from plutus.core.llm import (
        _ANTHROPIC_SERVER_TOOL_ID_PREFIX,
        _ANTHROPIC_WEB_FETCH_TOOL,
        _ANTHROPIC_WEB_SEARCH_TOOL,
    )

    config: PlutusConfig | None = _state.get("config")
    _is_anthropic = model_string.startswith("anthropic") or (
        config and config.model.provider == "anthropic"
    )
    if _is_anthropic and (not config or config.model.web_search):
        tools_for_llm.append(_ANTHROPIC_WEB_SEARCH_TOOL)
        tools_for_llm.append(_ANTHROPIC_WEB_FETCH_TOOL)

    # Worker system prompt — critical for proper completion behavior
    worker_system_prompt = (
        "You are a Plutus worker agent running on a Windows PC with WSL (Windows Subsystem "
        "for Linux) available. You have been assigned a specific task by the coordinator. "
        "Complete it efficiently using the available tools.\n\n"
        "BEHAVIOR RULES:\n"
        "1. Do NOT explain what you're about to do — just DO it. Use tools immediately.\n"
        "2. Do NOT ask follow-up questions — complete the work with what you have.\n"
        "3. When calling tools, do NOT include explanatory text alongside the tool calls.\n"
        "4. When you are FULLY DONE, respond with a clear summary of what you accomplished. "
        "This final message must have NO tool calls — it is your completion signal.\n"
        "5. Your final message is what gets shown to the user, so make it informative.\n\n"
        "TOOL USAGE GUIDE (critical — follow these to avoid errors):\n\n"
        "FILE OPERATIONS (use 'filesystem' tool — most reliable):\n"
        "- WRITE files: filesystem(operation='write', path='C:\\\\Users\\\\Public\\\\file.html', "
        "content='full file content here')\n"
        "- READ files: filesystem(operation='read', path='C:\\\\path\\\\to\\\\file.txt')\n"
        "- LIST directory: filesystem(operation='list', path='C:\\\\Users\\\\Public')\n"
        "- Do NOT use code_editor for simple file writes — use filesystem instead.\n\n"
        "SHELL COMMANDS (use 'shell' tool):\n"
        "- The shell tool supports three modes:\n"
        "  1. Default (cmd.exe): shell(command='dir C:\\\\Users')\n"
        "  2. WSL/bash: shell(command='ls -la /mnt/c/Users', use_wsl=true) — RECOMMENDED for scripting\n"
        "  3. PowerShell: shell(command='Get-Process', use_powershell=true)\n"
        "- WSL is PREFERRED for: bash scripts, text processing, curl, grep, sed, awk, python, node\n"
        "- WSL accesses Windows files at /mnt/c/ (e.g., /mnt/c/Users/Public/file.html)\n"
        "- Use cmd/PowerShell for: opening files, starting Windows apps, Windows-specific commands\n\n"
        "OPENING FILES:\n"
        "- In browser: shell(command='start msedge \"C:\\\\Users\\\\Public\\\\file.html\"')\n"
        "- In default app: shell(command='start \"\" \"C:\\\\path\\\\to\\\\file.ext\"')\n\n"
        "IMPORTANT TIPS:\n"
        "- File paths on Windows use backslashes: C:\\\\Users\\\\username\\\\Desktop\\\\file.txt\n"
        "- Common writable paths: C:\\\\Users\\\\Public, Desktop, Documents, Downloads\n"
        "- Do NOT pass large content (HTML, code) as inline shell arguments — write to file first\n"
        "- For complex scripts: write a .sh file with filesystem, then run with shell(use_wsl=true)\n\n"
        "STANDARD WORKFLOW for creating files:\n"
        "  Step 1: filesystem(operation='write', path='...', content='full content')\n"
        "  Step 2: Optionally shell(command='start ...') to open the file\n"
        "  Step 3: Respond with your final summary (no tool calls)"
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": worker_system_prompt},
        {"role": "user", "content": task.prompt},
    ]

    MAX_WORKER_ROUNDS = config.workers.max_tool_rounds if config else 15
    FORCE_SUMMARY_AT = MAX_WORKER_ROUNDS - 1  # Last round: no tools, force text
    result = "Task completed (no output)."
    final_texts: list[str] = []       # Only the FINAL text-only response
    thinking_texts: list[str] = []    # "Thinking" text from rounds with tool calls
    tool_outputs: list[str] = []      # Collected tool outputs as fallback context
    errored = False
    timed_out = False

    logger.info(f"Worker {task.id} ({task.name}) starting executor — model={model_string}, tools={len(tools_for_llm)}, deadline={deadline}")

    try:
        for round_num in range(MAX_WORKER_ROUNDS):
            # Check deadline BEFORE each round — with 60s buffer for final summary
            approaching_deadline = deadline and (time.time() >= deadline - 60)
            past_deadline = deadline and (time.time() >= deadline)

            if past_deadline:
                # Hard deadline hit — assemble whatever we have
                timed_out = True
                logger.warning(f"Worker {task.id} hit deadline at round {round_num + 1}")
                break

            # Determine if this round should force a final summary (no tools)
            force_summary = (round_num >= FORCE_SUMMARY_AT) or approaching_deadline

            status.current_step = f"Round {round_num + 1}/{MAX_WORKER_ROUNDS} — {model_display}"
            status.progress_pct = min(95.0, (round_num / MAX_WORKER_ROUNDS) * 100)
            try:
                await on_status(status)
            except Exception:
                pass

            call_kwargs: dict[str, Any] = {
                "model": model_string,
                "messages": messages,
                "max_tokens": 16384,  # Must be high — tool calls with file content can be 5000+ tokens
            }
            # OpenAI reasoning models (gpt-5.x) do NOT support the temperature
            # parameter — passing it causes a BadRequestError which previously
            # caused the worker to silently fall back to claude-haiku.
            # Non-OpenAI models (Anthropic) do support temperature.
            if not _worker_is_openai:
                call_kwargs["temperature"] = 0.7

            if force_summary:
                # Force the LLM to respond with text only.
                # We MUST still include tools= param if the conversation history
                # contains tool_calls — Anthropic's API requires it.
                # But we add a strong nudge to NOT use them.
                if tools_for_llm:
                    call_kwargs["tools"] = tools_for_llm
                messages.append({
                    "role": "user",
                    "content": (
                        "[SYSTEM] This is your FINAL round. You MUST respond with text only. "
                        "Do NOT call any tools. Provide a clear summary of what you accomplished "
                        "and include any relevant results, output, data, or file paths. "
                        "If you call a tool, the task will be terminated."
                    ),
                })
                logger.info(f"Worker {task.id} forced summary at round {round_num + 1}")
            elif tools_for_llm:
                call_kwargs["tools"] = tools_for_llm

            # LLM call with retry logic — litellm/httpx can raise CancelledError
            # on transient connection issues, so we retry up to 2 times
            response = None
            for attempt in range(3):
                try:
                    response = await litellm.acompletion(**call_kwargs)
                    break  # success
                except asyncio.CancelledError:
                    # Check if this is a real cancellation (from pool.cancel)
                    # or a transient error from httpx/aiohttp
                    current_task = asyncio.current_task()
                    if current_task and current_task.cancelled():
                        # Real cancellation — propagate
                        logger.info(f"Worker {task.id} truly cancelled on round {round_num + 1}")
                        raise
                    # Transient CancelledError from HTTP client — retry
                    logger.warning(f"Worker {task.id} got transient CancelledError on round {round_num + 1}, attempt {attempt + 1}/3")
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))  # backoff
                        continue
                    else:
                        logger.error(f"Worker {task.id} CancelledError persisted after 3 attempts")
                        result = f"[Worker Error] LLM call cancelled after 3 retries"
                        errored = True
                        break
                except Exception as llm_err:
                    logger.error(f"Worker {task.id} LLM call failed on round {round_num + 1}, attempt {attempt + 1}: {llm_err}")
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    else:
                        result = f"[Worker Error] LLM call failed after 3 retries: {llm_err}"
                        errored = True
                        break

            if errored or response is None:
                if not errored:
                    result = "[Worker Error] LLM call returned no response"
                    errored = True
                break

            choice = response.choices[0]
            msg = choice.message
            finish_reason = getattr(choice, 'finish_reason', 'unknown')
            has_content = bool(msg.content)
            has_tools = bool(msg.tool_calls)
            logger.info(f"Worker {task.id} round {round_num + 1}: finish_reason={finish_reason}, has_content={has_content}, has_tools={has_tools}, content_preview={repr(msg.content[:100]) if msg.content else 'None'}")

            # Handle finish_reason=length — response was truncated
            if finish_reason == 'length':
                logger.warning(f"Worker {task.id} response truncated (finish_reason=length) at round {round_num + 1}")
                # Save any partial content as thinking text
                if msg.content:
                    thinking_texts.append(msg.content)
                # Tell the LLM to retry with shorter content
                messages.append({"role": "assistant", "content": msg.content or ""})
                messages.append({
                    "role": "user",
                    "content": (
                        "[SYSTEM] Your previous response was truncated because it was too long. "
                        "Break your work into SMALLER steps. If you were writing a large file, "
                        "write it in multiple smaller append operations instead of one big write. "
                        "Continue from where you left off."
                    ),
                })
                continue

            # Filter out server-side tool calls (srvtoolu_*) — these are
            # Anthropic server-executed (web_search, web_fetch) and their
            # results are already in the response text.
            client_tool_calls = [
                tc for tc in (msg.tool_calls or [])
                if not (tc.id and tc.id.startswith(_ANTHROPIC_SERVER_TOOL_ID_PREFIX))
            ]

            # If no client-side tool calls, this is the FINAL response
            if not client_tool_calls:
                if msg.content:
                    final_texts.append(msg.content)
                    logger.info(f"Worker {task.id} completed with final text ({len(msg.content)} chars)")
                else:
                    logger.warning(f"Worker {task.id} sent stop response with NO content (finish_reason={finish_reason})")
                break

            # Has tool calls — text here is "thinking out loud". Keep as fallback.
            if msg.content:
                thinking_texts.append(msg.content)

            # Append the assistant message with tool calls
            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if msg.content:
                assistant_msg["content"] = msg.content
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments if isinstance(tc.function.arguments, str) else _json.dumps(tc.function.arguments),
                    },
                }
                for tc in client_tool_calls
            ]
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in client_tool_calls:
                tool_name = tc.function.name
                try:
                    args_raw = tc.function.arguments
                    args = _json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                except Exception as parse_err:
                    logger.error(f"Worker {task.id} failed to parse tool args for {tool_name}: {parse_err}")
                    logger.error(f"Worker {task.id} raw args (first 500 chars): {repr(str(args_raw)[:500])}")
                    # If JSON is truncated (finish_reason=length), tell the LLM
                    tool_result = (
                        f"[ERROR] Tool call arguments were malformed or truncated. "
                        f"This usually means your response was too long and got cut off. "
                        f"Try breaking the task into smaller steps — write smaller chunks of content."
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })
                    continue

                status.current_step = f"Using tool: {tool_name}"
                try:
                    await on_status(status)
                except Exception:
                    pass

                tool_result = "[ERROR] Tool not found"
                # Log tool args with content length for debugging file write issues
                args_summary = {}
                for k, v in args.items():
                    if isinstance(v, str) and len(v) > 100:
                        args_summary[k] = f"<string, {len(v)} chars>"
                    else:
                        args_summary[k] = repr(v)[:100]
                logger.info(f"Worker {task.id} calling tool: {tool_name}({args_summary})")
                if tool_registry:
                    tool_obj = tool_registry.get(tool_name)
                    if tool_obj and tool_name != "worker":
                        try:
                            tool_result = str(await tool_obj.execute(**args))
                        except asyncio.CancelledError:
                            # Check if real cancellation
                            current_task = asyncio.current_task()
                            if current_task and current_task.cancelled():
                                raise
                            tool_result = "[ERROR] Tool execution was interrupted, please retry"
                            logger.warning(f"Worker {task.id} tool {tool_name} got transient CancelledError")
                        except Exception as e:
                            tool_result = f"[ERROR] {e}"

                logger.info(f"Worker {task.id} tool {tool_name} result: {repr(tool_result[:200])}")

                # Track tool output for fallback
                if tool_result and not tool_result.startswith("[ERROR]"):
                    tool_outputs.append(f"[{tool_name}]: {tool_result[:2000]}")

                # Append tool result — ensure content is never empty
                # (Anthropic rejects tool messages without content)
                if not tool_result or not tool_result.strip():
                    tool_result = "(no output)"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": tool_result[:8000],  # cap to avoid context overflow
                })

        # Assemble the final result with fallback logic:
        # 1. Best case: the LLM gave a proper final text-only response
        # 2. Fallback: use thinking text + tool outputs if final response was empty
        logger.info(f"Worker {task.id} loop ended — final_texts={len(final_texts)}, thinking_texts={len(thinking_texts)}, tool_outputs={len(tool_outputs)}, errored={errored}, timed_out={timed_out}")

        if not errored:
            if final_texts:
                # Got a proper final summary from the LLM
                result = "\n".join(final_texts)
            elif thinking_texts or tool_outputs:
                # LLM didn't give a final summary, but we have context
                parts = []
                if thinking_texts:
                    parts.append("\n".join(thinking_texts))
                if tool_outputs:
                    parts.append("\n---\nTool outputs:\n" + "\n".join(tool_outputs[-5:]))
                if timed_out:
                    parts.append("\n[Worker timed out — partial results above]")
                result = "\n".join(parts)
            elif timed_out:
                result = f"[Worker timed out after {task.timeout}s with no output]"
            else:
                result = "Task completed but produced no output."

        # Update status
        status.current_step = "Done"
        status.steps_completed = 1
        status.progress_pct = 100.0
        try:
            await on_status(status)
        except Exception:
            pass

    except Exception as e:
        # Catch all non-cancellation errors. CancelledError is NOT caught here
        # (it's a BaseException in Python 3.9+) so it propagates to _run_worker.
        result = f"[Worker Error] {e}"
        logger.exception(f"Worker {task.id} failed: {e}")

    # Broadcast results to UI and coordinator.
    # Use asyncio.shield to protect broadcasts from cancellation.
    async def _broadcast_results() -> None:
        try:
            # Broadcast completion status to workers panel
            await ws_manager.broadcast({
                "type": "worker_completed",
                "worker": {
                    "task_id": task.id,
                    "name": task.name,
                    "result": result[:500],
                    "state": "timed_out" if timed_out else ("failed" if result.startswith("[Worker Error]") else "completed"),
                },
            })

            # Broadcast the full result to the chat — this is what the user sees
            await ws_manager.broadcast({
                "type": "worker_result",
                "task_id": task.id,
                "name": task.name,
                "model": model_display,
                "result": result,
                "duration": 0.0,
            })

            # Queue the result for the coordinator to pick up.
            # We do NOT inject directly into the conversation because
            # Anthropic requires strict tool_use → tool_result pairing.
            # Any message injected mid-tool-loop breaks this constraint.
            # Instead, we store it in a pending queue that the agent
            # drains at the start of each new process_message call.
            agent: AgentRuntime | None = _state.get("agent")
            if agent:
                worker_context_msg = (
                    f"[WORKER COMPLETED — {task.name} ({model_display})]\n"
                    f"{result}\n"
                    f"[You may reference this worker's output when responding to the user.]"
                )
                if not hasattr(agent, '_pending_worker_results'):
                    agent._pending_worker_results = []
                agent._pending_worker_results.append(worker_context_msg)
                # Cap pending results to prevent unbounded memory growth
                if len(agent._pending_worker_results) > 100:
                    agent._pending_worker_results = agent._pending_worker_results[-50:]
                logger.info(f"Worker {task.id} result queued for coordinator (queue size: {len(agent._pending_worker_results)})")
            else:
                logger.warning(f"Worker {task.id} could not queue result — no agent in state")
        except Exception as broadcast_err:
            logger.error(f"Worker {task.id} failed to broadcast results: {broadcast_err}")

    try:
        await asyncio.shield(_broadcast_results())
    except asyncio.CancelledError:
        # Shield was cancelled but the inner task continues
        # Try one more time synchronously-ish
        try:
            await _broadcast_results()
        except Exception:
            logger.error(f"Worker {task.id}: final broadcast attempt failed")

    return result


async def _worker_status_change(status: WorkerStatus) -> None:
    """Broadcast worker status changes to the UI."""
    await ws_manager.broadcast({
        "type": "worker_status",
        "worker": status.to_dict(),
    })


# ── Scheduler callback ──────────────────────────────────────────────────────

async def _scheduler_on_fire(job: ScheduledJob) -> str:
    """Called when a scheduled job fires."""
    pool: WorkerPool | None = _state.get("worker_pool")
    agent: AgentRuntime | None = _state.get("agent")

    if job.spawn_worker and pool:
        # Spawn as a worker
        task = WorkerTask(
            name=f"Scheduled: {job.name}",
            prompt=job.prompt,
            model_key=job.model_key,
            timeout=300.0,
        )
        status = await pool.submit(task)
        # Wait for it to complete
        final = await pool.wait_for(status.task_id, timeout=300.0)
        return final.result if final and final.result else "Job completed."
    elif agent:
        # Run on main agent — acquire the lock to prevent concurrent
        # process_message() calls (e.g. user chatting at the same time).
        if _agent_lock.locked():
            logger.warning(f"Skipping scheduled job '{job.name}' — agent is busy")
            return f"Job skipped: agent was busy processing another request."
        result_parts = []
        try:
            async with _agent_lock:
                async for event in agent.process_message(
                    f"[SCHEDULED JOB: {job.name}]\n{job.prompt}"
                ):
                    await ws_manager.broadcast(event.to_dict())
                    if hasattr(event, "content") and event.content:
                        result_parts.append(event.content)
        except Exception as e:
            logger.exception(f"Scheduled job '{job.name}' failed")
            return f"Job failed: {e}"
        return "\n".join(result_parts) if result_parts else "Job completed."
    else:
        raise RuntimeError("No agent or worker pool available")


async def _scheduler_on_event(event_data: dict[str, Any]) -> None:
    await ws_manager.broadcast(event_data)


# ── Computer Use agent ───────────────────────────────────────────────────────

def _init_computer_use_agent(config: PlutusConfig, secrets: SecretsStore) -> Any:
    """Initialize the Anthropic Computer Use agent if possible."""
    try:
        from plutus.core.computer_use_agent import ComputerUseAgent
        from plutus.pc.computer_use import ComputerUseExecutor

        api_key = secrets.get_key("anthropic")
        if not api_key:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("No Anthropic API key found — Computer Use agent disabled")
            return None

        cu_model = config.model.model
        if config.model.provider != "anthropic":
            cu_model = "claude-sonnet-4-6"

        executor = ComputerUseExecutor()
        agent = ComputerUseAgent(
            api_key=api_key,
            model=cu_model,
            executor=executor,
            max_iterations=config.agent.max_tool_rounds or 25,
        )
        logger.info(f"Computer Use agent initialized (model={cu_model})")
        return agent

    except ImportError as e:
        logger.warning(f"Computer Use agent not available: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize Computer Use agent: {e}")
        return None


# ── Connector auto-start ─────────────────────────────────────────────────────

async def _auto_start_connectors(connector_manager) -> None:
    """Auto-start connectors that have auto_start enabled."""
    for connector in connector_manager.get_configured():
        if not connector.auto_start:
            continue
        try:
            if connector.name == "telegram":
                from plutus.connectors.telegram_bridge import get_telegram_bridge
                bridge = get_telegram_bridge()
                await bridge.start()
                logger.info("Telegram bridge auto-started")
            elif connector.name == "discord":
                from plutus.connectors.discord_bridge import get_discord_bridge
                bridge = get_discord_bridge()
                await bridge.start()
                logger.info("Discord bridge auto-started")
            else:
                await connector.start()
                logger.info(f"Connector auto-started: {connector.name}")
        except Exception as e:
            logger.error(f"Failed to auto-start connector {connector.name}: {e}")


# ── Conversation auto-cleanup ───────────────────────────────────────────────

async def _conversation_cleanup_loop(
    memory: MemoryStore, config: "PlutusConfig"
) -> None:
    """Background task that periodically cleans up stale conversations.

    Runs once per hour. Deletes conversations with no activity for more than
    the configured number of days (default 30).
    """
    CLEANUP_INTERVAL = 3600  # Check every hour

    while True:
        try:
            await asyncio.sleep(CLEANUP_INTERVAL)
            days = config.memory.conversation_auto_delete_days
            if days <= 0:
                continue  # Disabled
            deleted = await memory.cleanup_stale_conversations(days)
            if deleted > 0:
                logger.info(
                    f"Auto-cleanup: deleted {deleted} conversations "
                    f"(inactive for >{days} days)"
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Conversation cleanup error: {e}")
            await asyncio.sleep(60)  # Wait a bit before retrying


# ── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    # Pre-declare resources so cleanup runs even if startup fails partway
    memory: MemoryStore | None = None
    scheduler: Scheduler | None = None
    heartbeat: HeartbeatRunner | None = None
    worker_pool: WorkerPool | None = None
    cleanup_task: asyncio.Task | None = None
    connector_manager = None
    keep_alive = None
    agent: AgentRuntime | None = None

    try:
        config = PlutusConfig.load()

        # Ensure the workspace directory exists (auto-created for existing users on upgrade)
        workspace_dir = Path.home() / "plutus-workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Initialize secrets store and inject stored keys into environment
        secrets = SecretsStore()
        secrets.inject_all()

        # Initialize model router
        routing_config = ModelRoutingConfig(
            enabled_models=config.model_routing.enabled_models,
            cost_conscious=config.model_routing.cost_conscious,
            default_worker_model=config.model_routing.default_worker_model,
            default_scheduler_model=config.model_routing.default_scheduler_model,
        )
        model_router = ModelRouter(config=routing_config, secrets=secrets)

        # Initialize memory
        memory = MemoryStore(config.resolve_memory_db())
        await memory.initialize()

        # Initialize guardrails
        guardrails = GuardrailEngine(config)

        # Initialize tool registry
        tool_registry = create_default_registry()

        # Initialize standard agent
        agent = AgentRuntime(
            config=config,
            guardrails=guardrails,
            memory=memory,
            tool_registry=tool_registry,
            secrets=secrets,
        )
        await agent.initialize()

        # Register memory tool
        from plutus.tools.memory_tool import MemoryTool
        memory_tool = MemoryTool(memory, agent.conversation)
        tool_registry.register(memory_tool)

        # Initialize worker pool
        worker_pool = WorkerPool(
            max_workers=config.workers.max_concurrent_workers,
            executor=_worker_executor,
            on_status_change=_worker_status_change,
        )

        # Register worker tool
        from plutus.tools.worker_tool import WorkerTool
        worker_tool = WorkerTool(worker_pool)
        tool_registry.register(worker_tool)

        # Initialize scheduler
        scheduler = Scheduler(
            on_fire=_scheduler_on_fire,
            on_event=_scheduler_on_event,
        )

        # Register scheduler tool
        from plutus.tools.scheduler_tool import SchedulerTool
        scheduler_tool = SchedulerTool(scheduler)
        tool_registry.register(scheduler_tool)

        # Start scheduler if enabled
        if config.scheduler.enabled:
            await scheduler.start()

        # Initialize Computer Use agent
        cu_agent = _init_computer_use_agent(config, secrets)

        # Initialize heartbeat
        heartbeat = HeartbeatRunner(
            config=config.heartbeat,
            on_beat=_heartbeat_on_beat,
            on_event=_heartbeat_on_event,
        )
        if config.heartbeat.enabled:
            heartbeat.start()

        # Initialize connector manager and register connector + git tools
        from plutus.connectors import create_connector_manager
        from plutus.tools.connector_tool import ConnectorTool
        from plutus.tools.git_tool import GitTool
        connector_manager = create_connector_manager()

        # Load user-created custom API connectors
        from plutus.connectors.custom_api import CustomConnectorManager
        for custom_conn in CustomConnectorManager.load_all_custom_connectors():
            connector_manager.register(custom_conn)
            logger.info(f"Loaded custom connector: {custom_conn.name}")

        connector_tool = ConnectorTool(connector_manager)
        tool_registry.register(connector_tool)
        git_tool = GitTool(connector_manager)
        tool_registry.register(git_tool)
        agent.set_connector_manager(connector_manager)

        # Register web deploy tool
        from plutus.tools.web_deploy import WebDeployTool
        web_deploy_tool = WebDeployTool(secrets=secrets)
        tool_registry.register(web_deploy_tool)
        logger.info("Registered web_deploy tool")

        # Start conversation auto-cleanup background task
        if config.memory.conversation_auto_delete_days > 0:
            cleanup_task = asyncio.create_task(
                _conversation_cleanup_loop(memory, config)
            )
            logger.info(
                f"Conversation auto-cleanup enabled: {config.memory.conversation_auto_delete_days} days"
            )

        # Store all state
        _state["config"] = config
        _state["secrets"] = secrets
        _state["memory"] = memory
        _state["guardrails"] = guardrails
        _state["tool_registry"] = tool_registry
        _state["agent"] = agent
        _state["cu_agent"] = cu_agent
        _state["heartbeat"] = heartbeat
        _state["connector_manager"] = connector_manager
        _state["model_router"] = model_router
        _state["worker_pool"] = worker_pool
        _state["scheduler"] = scheduler

        key_status = "configured" if agent.key_configured else "NOT configured"
        cu_status = "enabled" if cu_agent else "disabled"
        heartbeat_status = "enabled" if config.heartbeat.enabled else "disabled"
        scheduler_status = "enabled" if config.scheduler.enabled else "disabled"
        logger.info(
            f"Plutus v0.3.2 started — tier={config.guardrails.tier}, "
            f"model={config.model.provider}/{config.model.model}, "
            f"api_key={key_status}, computer_use={cu_status}, "
            f"heartbeat={heartbeat_status}, scheduler={scheduler_status}, "
            f"max_workers={config.workers.max_concurrent_workers}, "
            f"worker_model={config.model_routing.default_worker_model}, "
            f"scheduler_model={config.model_routing.default_scheduler_model}"
        )

        # Initialize keep-alive (prevent system sleep)
        from plutus.core.keep_alive import KeepAlive
        keep_alive = KeepAlive()
        if config.keep_alive.enabled:
            keep_alive.enable()
        _state["keep_alive"] = keep_alive

        # Auto-start connectors
        await _auto_start_connectors(connector_manager)

    except Exception:
        # Startup failed — clean up any resources that were initialized
        logger.exception("Startup failed — cleaning up partial resources")
        await _cleanup_resources(
            keep_alive=keep_alive,
            cleanup_task=cleanup_task,
            heartbeat=heartbeat,
            scheduler=scheduler,
            worker_pool=worker_pool,
            connector_manager=connector_manager,
            agent=agent,
        )
        raise

    yield

    # Normal shutdown — each step wrapped individually so one failure
    # doesn't prevent subsequent cleanup from running
    await _cleanup_resources(
        keep_alive=keep_alive,
        cleanup_task=cleanup_task,
        heartbeat=heartbeat,
        scheduler=scheduler,
        worker_pool=worker_pool,
        connector_manager=connector_manager,
        agent=agent,
    )
    logger.info("Plutus shut down")


async def _cleanup_resources(
    *,
    keep_alive: Any = None,
    cleanup_task: asyncio.Task | None = None,
    heartbeat: HeartbeatRunner | None = None,
    scheduler: Scheduler | None = None,
    worker_pool: WorkerPool | None = None,
    connector_manager: Any = None,
    agent: AgentRuntime | None = None,
) -> None:
    """Clean up server resources safely. Each step is independent."""
    if keep_alive:
        try:
            keep_alive.disable()
        except Exception as e:
            logger.error(f"Error disabling keep-alive: {e}")
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except (asyncio.CancelledError, Exception):
            pass
    if heartbeat:
        try:
            heartbeat.stop()
        except Exception as e:
            logger.error(f"Error stopping heartbeat: {e}")
    if scheduler:
        try:
            await scheduler.stop()
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    if worker_pool:
        try:
            await worker_pool.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up worker pool: {e}")
    if connector_manager:
        try:
            await connector_manager.stop_all()
        except Exception as e:
            logger.error(f"Error stopping connectors: {e}")
    if agent:
        try:
            await agent.shutdown()
        except Exception as e:
            logger.error(f"Error shutting down agent: {e}")


def create_app(config: PlutusConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    from plutus import __version__

    app = FastAPI(
        title="Plutus",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(create_router(), prefix="/api")
    app.include_router(create_ws_router())

    # Silence Chrome DevTools probe (prevents noisy 404s in the log)
    @app.get("/.well-known/appspecific/com.chrome.devtools.json")
    async def _chrome_devtools_probe():
        from fastapi.responses import JSONResponse

        return JSONResponse(content={}, status_code=200)

    # Serve the UI — check bundled location first (pip install), then dev location
    ui_dir = Path(__file__).parent.parent / "ui_dist"
    if not ui_dir.exists():
        ui_dir = Path(__file__).parent.parent.parent / "ui" / "dist"
    if ui_dir.exists():
        app.mount("/", StaticFiles(directory=str(ui_dir), html=True), name="ui")

    return app
