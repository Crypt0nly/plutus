"""
connector_service.py — Cloud-side connector bridge manager.

Manages per-user background asyncio tasks that poll Telegram (and in future
WhatsApp) for incoming messages and route them through the CloudAgentRuntime.

Each user can independently start/stop their connectors.  State is kept in
memory (a dict keyed by user_id + connector name) and also persisted to the
user's ``connector_credentials`` JSON column so that the UI can show the
correct running/stopped status across requests.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory registry of running bridge tasks
# { user_id: { connector_name: asyncio.Task } }
# ---------------------------------------------------------------------------
_running: dict[str, dict[str, asyncio.Task]] = {}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def is_running(user_id: str, connector: str) -> bool:
    return bool(
        _running.get(user_id, {}).get(connector) and not _running[user_id][connector].done()
    )


def running_connectors(user_id: str) -> list[str]:
    return [name for name, task in _running.get(user_id, {}).items() if not task.done()]


async def start_connector(
    user_id: str,
    connector: str,
    credentials: dict,
    db_session_factory,
) -> dict:
    """Start a background bridge task for *connector* for *user_id*.

    Returns a status dict that the API endpoint can return directly.
    """
    if is_running(user_id, connector):
        return {"status": "already_running", "listening": True}

    if connector == "telegram":
        task = asyncio.create_task(
            _telegram_poll_loop(user_id, credentials, db_session_factory),
            name=f"telegram-{user_id}",
        )
    elif connector == "whatsapp":
        # WhatsApp uses the same Node.js bridge approach but runs server-side.
        # For now we start the bridge process and return a pairing_code if needed.
        task = asyncio.create_task(
            _whatsapp_bridge_loop(user_id, credentials, db_session_factory),
            name=f"whatsapp-{user_id}",
        )
    elif connector == "discord":
        task = asyncio.create_task(
            _discord_gateway_loop(user_id, credentials, db_session_factory),
            name=f"discord-{user_id}",
        )
    else:
        return {"status": "unsupported", "listening": False}

    _running.setdefault(user_id, {})[connector] = task

    # Give the task a moment to fail fast (e.g. bad token)
    await asyncio.sleep(0.3)
    if task.done():
        exc = task.exception()
        return {
            "status": "error",
            "listening": False,
            "message": str(exc) if exc else "Bridge task exited immediately",
        }

    return {"status": "running", "listening": True}


async def stop_connector(user_id: str, connector: str) -> dict:
    task = _running.get(user_id, {}).get(connector)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    _running.get(user_id, {}).pop(connector, None)
    return {"status": "stopped", "listening": False}


# ---------------------------------------------------------------------------
# Telegram long-poll bridge
# ---------------------------------------------------------------------------

_TG_BASE = "https://api.telegram.org/bot{token}/{method}"


async def _tg_call(client: httpx.AsyncClient, token: str, method: str, **params: Any) -> dict:
    url = _TG_BASE.format(token=token, method=method)
    resp = await client.post(url, json=params, timeout=35)
    return resp.json()


async def _telegram_poll_loop(
    user_id: str,
    credentials: dict,
    db_session_factory,
) -> None:
    """Long-poll Telegram getUpdates and route messages to the cloud agent."""
    token = credentials.get("bot_token", "")
    if not token:
        raise ValueError("No Telegram bot_token in credentials")

    logger.info(f"[Telegram] Starting poll loop for user {user_id}")
    offset = 0
    # Conversation tracking: map telegram chat_id → plutus conversation_id
    conversations: dict[int, str] = {}

    async with httpx.AsyncClient() as client:
        # Verify the token first
        me = await _tg_call(client, token, "getMe")
        if not me.get("ok"):
            raise ValueError(f"Telegram getMe failed: {me.get('description', 'invalid token')}")
        logger.info(
            f"[Telegram] Authenticated as @{me['result'].get('username')} for user {user_id}"
        )

        while True:
            try:
                data = await _tg_call(
                    client,
                    token,
                    "getUpdates",
                    offset=offset,
                    timeout=25,
                    allowed_updates=["message"],
                )
            except asyncio.CancelledError:
                logger.info(f"[Telegram] Poll loop cancelled for user {user_id}")
                raise
            except Exception as exc:
                logger.warning(f"[Telegram] getUpdates error: {exc}, retrying in 5s")
                await asyncio.sleep(5)
                continue

            if not data.get("ok"):
                logger.warning(f"[Telegram] getUpdates not ok: {data}")
                await asyncio.sleep(5)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message")
                if not msg or "text" not in msg:
                    continue

                chat_id: int = msg["chat"]["id"]
                text: str = msg["text"]
                from_user = msg.get("from", {})
                sender = from_user.get("first_name", "User")

                logger.info(f"[Telegram] Message from {sender} (chat {chat_id}): {text[:80]}")

                # Send typing indicator
                asyncio.create_task(
                    _tg_call(client, token, "sendChatAction", chat_id=chat_id, action="typing")
                )

                # Route to agent
                try:
                    conv_id = conversations.get(chat_id)
                    reply, conv_id = await _process_message(
                        user_id, text, conv_id, db_session_factory
                    )
                    conversations[chat_id] = conv_id
                except Exception as exc:
                    logger.exception("[Telegram] Agent processing error")
                    reply = f"⚠️ Error: {exc}"

                # Send reply
                try:
                    await _tg_call(
                        client,
                        token,
                        "sendMessage",
                        chat_id=chat_id,
                        text=reply[:4096],
                    )
                except Exception as exc:
                    logger.error(f"[Telegram] Failed to send reply: {exc}")


# ---------------------------------------------------------------------------
# Discord gateway bridge (simplified HTTP polling via channel webhook)
# ---------------------------------------------------------------------------


async def _discord_gateway_loop(
    user_id: str,
    credentials: dict,
    db_session_factory,
) -> None:
    """Poll a Discord channel for new messages and reply via bot token."""
    bot_token = credentials.get("bot_token", "")
    channel_id = credentials.get("channel_id", "")
    if not bot_token:
        raise ValueError("No Discord bot_token in credentials")
    if not channel_id:
        raise ValueError(
            "No Discord channel_id in credentials. "
            "Please add the channel ID to the Discord connector config."
        )

    logger.info(f"[Discord] Starting poll loop for user {user_id}")
    headers = {"Authorization": f"Bot {bot_token}"}
    last_message_id: str | None = None
    conversations: dict[str, str] = {}  # channel_id → conv_id

    async with httpx.AsyncClient() as client:
        # Verify token
        me = await client.get("https://discord.com/api/v10/users/@me", headers=headers)
        if me.status_code != 200:
            raise ValueError(f"Discord auth failed: {me.json().get('message', 'invalid token')}")
        logger.info(f"[Discord] Authenticated as {me.json().get('username')} for user {user_id}")

        while True:
            try:
                params = {"limit": 10}
                if last_message_id:
                    params["after"] = last_message_id

                resp = await client.get(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers=headers,
                    params=params,
                    timeout=10,
                )
                if resp.status_code == 200:
                    messages = resp.json()
                    # Messages are newest-first; reverse for chronological order
                    for msg in reversed(messages):
                        msg_id = msg["id"]
                        last_message_id = msg_id
                        # Skip bot's own messages
                        if msg.get("author", {}).get("bot"):
                            continue
                        text = msg.get("content", "").strip()
                        if not text:
                            continue

                        logger.info(
                            f"[Discord] Message from {msg['author'].get('username')}: {text[:80]}"
                        )

                        try:
                            conv_id = conversations.get(channel_id)
                            reply, conv_id = await _process_message(
                                user_id, text, conv_id, db_session_factory
                            )
                            conversations[channel_id] = conv_id
                        except Exception as exc:
                            logger.exception("[Discord] Agent processing error")
                            reply = f"⚠️ Error: {exc}"

                        # Reply in the same channel
                        try:
                            await client.post(
                                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                                headers=headers,
                                json={"content": reply[:2000]},
                                timeout=10,
                            )
                        except Exception as exc:
                            logger.error(f"[Discord] Failed to send reply: {exc}")

                await asyncio.sleep(3)  # Poll every 3 seconds

            except asyncio.CancelledError:
                logger.info(f"[Discord] Poll loop cancelled for user {user_id}")
                raise
            except Exception as exc:
                logger.warning(f"[Discord] Poll error: {exc}, retrying in 10s")
                await asyncio.sleep(10)


# ---------------------------------------------------------------------------
# WhatsApp bridge (Node.js subprocess, server-side)
# ---------------------------------------------------------------------------


async def _whatsapp_bridge_loop(
    user_id: str,
    credentials: dict,
    db_session_factory,
) -> None:
    """Run the whatsapp-web.js bridge as a subprocess on the cloud server."""
    import json
    import os

    phone_number = credentials.get("phone_number", "")
    if not phone_number:
        raise ValueError("No phone_number in WhatsApp credentials")

    # Find the bridge script (same directory as the local version's bridge)
    bridge_script = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "..",
        "plutus",
        "connectors",
        "whatsapp_bridge.js",
    )
    bridge_script = os.path.normpath(bridge_script)

    if not os.path.exists(bridge_script):
        raise FileNotFoundError(
            f"whatsapp_bridge.js not found at {bridge_script}. "
            "Make sure the plutus package is installed alongside the cloud backend."
        )

    # Session directory per user
    session_dir = os.path.join(os.path.expanduser("~"), ".plutus_whatsapp_sessions", user_id)
    os.makedirs(session_dir, exist_ok=True)

    logger.info(f"[WhatsApp] Starting bridge for user {user_id}")
    proc = await asyncio.create_subprocess_exec(
        "node",
        bridge_script,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "WA_SESSION_DIR": session_dir,
            "WA_PHONE_NUMBER": phone_number,
            # Cloud Docker image sets WA_NODE_MODULES; local installs use
            # node_modules next to the bridge script (auto-resolved by the JS).
            **(
                {"WA_NODE_MODULES": os.environ["WA_NODE_MODULES"]}
                if "WA_NODE_MODULES" in os.environ
                else {}
            ),
        },
    )

    conversations: dict[str, str] = {}

    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            logger.debug(f"[WhatsApp/node] {line.decode().rstrip()}")

    asyncio.create_task(read_stderr())

    # Send init command with phone number
    init_cmd = json.dumps({"type": "init", "phone_number": phone_number}) + "\n"
    proc.stdin.write(init_cmd.encode())
    await proc.stdin.drain()

    try:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            try:
                event = json.loads(line.decode().strip())
            except json.JSONDecodeError:
                continue

            etype = event.get("type")
            if etype == "pairing_code":
                code = event.get("code", "")
                logger.info(f"[WhatsApp] Pairing code for {user_id}: {code}")
                # Persist pairing code to DB so the UI can show it
                await _update_connector_state(
                    user_id, "whatsapp", {"pairing_code": code, "ready": False}, db_session_factory
                )
            elif etype == "ready":
                logger.info(f"[WhatsApp] Connected for user {user_id}")
                await _update_connector_state(
                    user_id, "whatsapp", {"pairing_code": None, "ready": True}, db_session_factory
                )
            elif etype == "message":
                from_id = event.get("from", "unknown")
                text = event.get("body", "")
                if not text:
                    continue
                logger.info(f"[WhatsApp] Message from {from_id}: {text[:80]}")
                try:
                    conv_id = conversations.get(from_id)
                    reply, conv_id = await _process_message(
                        user_id, text, conv_id, db_session_factory
                    )
                    conversations[from_id] = conv_id
                except Exception as exc:
                    logger.exception("[WhatsApp] Agent processing error")
                    reply = f"⚠️ Error: {exc}"

                # Send reply back via bridge
                send_cmd = (
                    json.dumps(
                        {
                            "type": "send",
                            "to": from_id,
                            "body": reply,
                        }
                    )
                    + "\n"
                )
                proc.stdin.write(send_cmd.encode())
                await proc.stdin.drain()

    except asyncio.CancelledError:
        logger.info(f"[WhatsApp] Bridge loop cancelled for user {user_id}")
        proc.terminate()
        raise
    finally:
        if proc.returncode is None:
            proc.terminate()


# ---------------------------------------------------------------------------
# Shared: route a message through the cloud agent runtime
# ---------------------------------------------------------------------------


async def _process_message(
    user_id: str,
    text: str,
    conversation_id: str | None,
    db_session_factory,
) -> tuple[str, str]:
    """Process a message through CloudAgentRuntime. Returns (reply, conv_id)."""
    from app.agent.runtime import CloudAgentRuntime
    from app.models.user import User

    async with db_session_factory() as session:
        user_row = await session.get(User, user_id)
        config = {}
        if user_row:
            config = user_row.settings or {}

        runtime = CloudAgentRuntime(user_id, session, config)
        result = await runtime.process_message(text, conversation_id)
        return result["response"], result["conversation_id"]


# ---------------------------------------------------------------------------
# Shared: persist connector state (pairing code, ready flag) to DB
# ---------------------------------------------------------------------------


async def _update_connector_state(
    user_id: str,
    connector: str,
    state: dict,
    db_session_factory,
) -> None:
    from app.models.user import User

    async with db_session_factory() as session:
        user_row = await session.get(User, user_id)
        if user_row:
            creds = dict(user_row.connector_credentials or {})
            existing = dict(creds.get(connector, {}))
            existing.update(state)
            creds[connector] = existing
            user_row.connector_credentials = creds
            await session.commit()
