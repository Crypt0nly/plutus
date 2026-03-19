"""Discord connector for Plutus.

Uses discord.py to connect to Discord as a bot and fully manage servers:
  - Send and receive messages in channels
  - Manage channels (create, delete, modify)
  - Manage roles (create, delete, assign, remove)
  - Manage members (kick, ban, unban, change nicknames)
  - Manage server settings
  - Send files and images

Setup:
  1. Create a bot at https://discord.com/developers/applications
  2. Enable privileged intents (Message Content, Server Members, Presences)
  3. Generate a bot token and enter it in the Plutus Connectors tab
  4. Invite the bot to your server with Administrator permissions
  5. Send any message in a channel — Plutus auto-detects the guild and channel

Architecture:
  - Uses discord.py with a background asyncio task running the bot client
  - Separate from the main event loop — runs in its own task
  - Messages are delivered via the _on_message callback (set by DiscordBridge)
  - Guild management actions are exposed for the agent tool
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from plutus.connectors.base import BaseConnector
from plutus.utils.ssl_utils import make_aiohttp_connector

logger = logging.getLogger("plutus.connectors.discord")

DISCORD_API = "https://discord.com/api/v10"


class DiscordConnector(BaseConnector):
    name = "discord"
    display_name = "Discord"
    description = "Manage and communicate through a Discord server"
    icon = "MessageSquare"  # Lucide icon

    def __init__(self):
        super().__init__()
        self._client = None
        self._bot_task: asyncio.Task | None = None
        self._on_message: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None
        self._ready_event: asyncio.Event = asyncio.Event()
        self._session = None

    def _sensitive_fields(self) -> list[str]:
        return ["bot_token"]

    def config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "bot_token",
                "label": "Bot Token",
                "type": "password",
                "required": True,
                "placeholder": "MTIz...",
                "help": "Get this from Discord Developer Portal → Bot → Token",
            },
            {
                "name": "guild_id",
                "label": "Server ID",
                "type": "text",
                "required": False,
                "placeholder": "Auto-detected when bot receives a message",
                "help": (
                    "Right-click your server → Copy Server ID "
                    "(enable Developer Mode in Discord settings)"
                ),
            },
            {
                "name": "channel_id",
                "label": "Default Channel ID",
                "type": "text",
                "required": False,
                "placeholder": "Auto-detected from first message",
                "help": (
                    "Channel where Plutus sends messages by default. "
                    "Right-click a channel → Copy Channel ID"
                ),
            },
            {
                "name": "bot_username",
                "label": "Bot Username",
                "type": "text",
                "required": False,
                "placeholder": "Auto-detected",
                "help": "Filled automatically after testing connection",
            },
        ]

    @property
    def _token(self) -> str:
        return self._config.get("bot_token", "")

    @property
    def _guild_id(self) -> int | None:
        gid = self._config.get("guild_id", "")
        return int(gid) if gid and str(gid).isdigit() else None

    @property
    def _channel_id(self) -> int | None:
        cid = self._config.get("channel_id", "")
        return int(cid) if cid and str(cid).isdigit() else None

    async def _get_session(self):
        """Get or create an aiohttp session for REST API calls."""
        import aiohttp
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                connector=make_aiohttp_connector(),
                headers={"Authorization": f"Bot {self._token}"},
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    async def _api_call(
        self, method: str, path: str, json: dict | None = None, **kwargs: Any
    ) -> dict[str, Any] | list[Any]:
        """Make a Discord REST API call."""
        session = await self._get_session()
        url = f"{DISCORD_API}{path}"
        try:
            async with session.request(method, url, json=json, **kwargs) as resp:
                if resp.status == 204:
                    return {"success": True}
                data = await resp.json()
                if resp.status >= 400:
                    msg = data.get("message", str(data))
                    logger.error(f"Discord API error ({method} {path}): {msg}")
                    raise Exception(f"Discord API error: {msg}")
                return data
        except Exception as e:
            if "Discord API error" in str(e):
                raise
            logger.error(f"Discord HTTP error ({method} {path}): {e}")
            raise

    async def test_connection(self) -> dict[str, Any]:
        """Test the bot token by calling /users/@me."""
        if not self._token:
            return {"success": False, "message": "Bot token is required"}

        try:
            me = await self._api_call("GET", "/users/@me")
            bot_username = me.get("username", "")
            bot_id = me.get("id", "")
            discriminator = me.get("discriminator", "0")

            # Save bot info
            display = f"{bot_username}#{discriminator}" if discriminator != "0" else bot_username
            self._config["bot_username"] = display
            self._config["bot_id"] = bot_id
            self._config_store.save(self._config)

            result: dict[str, Any] = {
                "success": True,
                "message": f"Connected as {display}",
                "bot_username": display,
                "bot_id": bot_id,
            }

            # Try to get guilds the bot is in
            try:
                guilds = await self._api_call("GET", "/users/@me/guilds")
                if guilds:
                    guild_names = [g["name"] for g in guilds[:5]]
                    result["message"] += f" — In servers: {', '.join(guild_names)}"
                    # Auto-detect guild_id if not set and bot is in exactly one guild
                    if not self._guild_id and len(guilds) == 1:
                        self._config["guild_id"] = str(guilds[0]["id"])
                        self._config["guild_name"] = guilds[0]["name"]
                        self._config_store.save(self._config)
                        result["guild_id"] = str(guilds[0]["id"])
                        result["message"] += " (auto-selected)"
                else:
                    result["message"] += (
                        " — Bot is not in any servers yet. "
                        "Invite it with Administrator permissions."
                    )
                    result["needs_invite"] = True
            except Exception as e:
                logger.debug(f"Could not list guilds: {e}")

            return result

        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}
        finally:
            # Close the session created for testing
            if self._session and not self._session.closed:
                await self._session.close()
                self._session = None

    async def send_message(
        self,
        text: str,
        channel_id: int | str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a message to a Discord channel."""
        target = channel_id or self._channel_id
        if not target:
            return {
                "success": False,
                "message": "No channel_id configured — set a default channel or specify one",
            }

        if not self._token:
            return {"success": False, "message": "Bot token not configured"}

        try:
            target_int = int(target)
            # Discord has a 2000 char limit — split long messages
            chunks = _split_message(text, 1950)
            results = []
            for chunk in chunks:
                result = await self._api_call(
                    "POST",
                    f"/channels/{target_int}/messages",
                    json={"content": chunk},
                )
                results.append(result)
                logger.info(
                    f"Sent Discord message to channel {target_int} "
                    f"(msg_id={result.get('id')})"
                )

            return {
                "success": True,
                "message": (
                    f"Sent to Discord "
                    f"({len(chunks)} message{'s' if len(chunks) > 1 else ''})"
                ),
                "message_ids": [r.get("id") for r in results],
            }
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return {"success": False, "message": f"Failed to send: {str(e)}"}

    async def send_file(
        self,
        file_path: str,
        caption: str = "",
        channel_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Send a file to a Discord channel."""
        import os

        import aiohttp

        target = channel_id or self._channel_id
        if not target:
            return {"success": False, "message": "No channel_id configured"}

        try:
            session = await self._get_session()
            url = f"{DISCORD_API}/channels/{int(target)}/messages"

            data = aiohttp.FormData()
            if caption:
                # payload_json allows setting content alongside file uploads
                import json as json_mod
                data.add_field(
                    "payload_json",
                    json_mod.dumps({"content": caption[:2000]}),
                    content_type="application/json",
                )
            data.add_field(
                "files[0]",
                open(file_path, "rb"),
                filename=os.path.basename(file_path),
            )

            async with session.post(url, data=data) as resp:
                result = await resp.json()
                if resp.status < 400:
                    return {"success": True, "message": "File sent via Discord"}
                else:
                    return {
                        "success": False,
                        "message": result.get("message", "Failed to send file"),
                    }
        except Exception as e:
            return {"success": False, "message": f"Failed to send file: {str(e)}"}

    # ── Server management methods ──────────────────────────────

    async def list_channels(self, guild_id: int | None = None) -> dict[str, Any]:
        """List all channels in the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            channels = await self._api_call("GET", f"/guilds/{gid}/channels")
            return {"success": True, "channels": channels}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_channel(
        self,
        name: str,
        channel_type: int = 0,
        guild_id: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a channel in the guild.

        channel_type: 0=text, 2=voice, 4=category, 5=announcement, 13=stage, 15=forum
        """
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            payload: dict[str, Any] = {"name": name, "type": channel_type}
            if kwargs.get("topic"):
                payload["topic"] = kwargs["topic"]
            if kwargs.get("parent_id"):
                payload["parent_id"] = int(kwargs["parent_id"])
            channel = await self._api_call(
                "POST", f"/guilds/{gid}/channels", json=payload
            )
            return {"success": True, "channel": channel}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def delete_channel(self, channel_id: int) -> dict[str, Any]:
        """Delete a channel."""
        try:
            await self._api_call("DELETE", f"/channels/{channel_id}")
            return {"success": True, "message": f"Channel {channel_id} deleted"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def edit_channel(
        self, channel_id: int, **kwargs: Any
    ) -> dict[str, Any]:
        """Edit a channel (name, topic, etc.)."""
        try:
            payload = {}
            for key in ("name", "topic", "nsfw", "position", "rate_limit_per_user"):
                if key in kwargs:
                    payload[key] = kwargs[key]
            if not payload:
                return {"success": False, "message": "No fields to update"}
            channel = await self._api_call(
                "PATCH", f"/channels/{channel_id}", json=payload
            )
            return {"success": True, "channel": channel}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def list_members(
        self, limit: int = 100, guild_id: int | None = None
    ) -> dict[str, Any]:
        """List guild members (requires Server Members Intent)."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            members = await self._api_call(
                "GET", f"/guilds/{gid}/members?limit={min(limit, 1000)}"
            )
            return {"success": True, "members": members}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def kick_member(
        self, user_id: int, reason: str = "", guild_id: int | None = None
    ) -> dict[str, Any]:
        """Kick a member from the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            kwargs: dict[str, Any] = {}
            if reason:
                kwargs["headers"] = {"X-Audit-Log-Reason": reason}
            await self._api_call(
                "DELETE", f"/guilds/{gid}/members/{user_id}", **kwargs
            )
            return {"success": True, "message": f"User {user_id} kicked"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def ban_member(
        self,
        user_id: int,
        reason: str = "",
        delete_message_seconds: int = 0,
        guild_id: int | None = None,
    ) -> dict[str, Any]:
        """Ban a member from the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            payload: dict[str, Any] = {}
            if delete_message_seconds:
                payload["delete_message_seconds"] = min(
                    delete_message_seconds, 604800
                )  # Max 7 days
            kwargs: dict[str, Any] = {}
            if reason:
                kwargs["headers"] = {"X-Audit-Log-Reason": reason}
            await self._api_call(
                "PUT", f"/guilds/{gid}/bans/{user_id}", json=payload or None, **kwargs
            )
            return {"success": True, "message": f"User {user_id} banned"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def unban_member(
        self, user_id: int, guild_id: int | None = None
    ) -> dict[str, Any]:
        """Unban a member from the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            await self._api_call("DELETE", f"/guilds/{gid}/bans/{user_id}")
            return {"success": True, "message": f"User {user_id} unbanned"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def list_roles(self, guild_id: int | None = None) -> dict[str, Any]:
        """List all roles in the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            roles = await self._api_call("GET", f"/guilds/{gid}/roles")
            return {"success": True, "roles": roles}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def create_role(
        self,
        name: str,
        permissions: int | None = None,
        color: int = 0,
        guild_id: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create a role in the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            payload: dict[str, Any] = {"name": name, "color": color}
            if permissions is not None:
                payload["permissions"] = str(permissions)
            if kwargs.get("hoist") is not None:
                payload["hoist"] = kwargs["hoist"]
            if kwargs.get("mentionable") is not None:
                payload["mentionable"] = kwargs["mentionable"]
            role = await self._api_call(
                "POST", f"/guilds/{gid}/roles", json=payload
            )
            return {"success": True, "role": role}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def delete_role(
        self, role_id: int, guild_id: int | None = None
    ) -> dict[str, Any]:
        """Delete a role from the guild."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            await self._api_call("DELETE", f"/guilds/{gid}/roles/{role_id}")
            return {"success": True, "message": f"Role {role_id} deleted"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def assign_role(
        self, user_id: int, role_id: int, guild_id: int | None = None
    ) -> dict[str, Any]:
        """Assign a role to a member."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            await self._api_call(
                "PUT", f"/guilds/{gid}/members/{user_id}/roles/{role_id}"
            )
            return {
                "success": True,
                "message": f"Role {role_id} assigned to user {user_id}",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def remove_role(
        self, user_id: int, role_id: int, guild_id: int | None = None
    ) -> dict[str, Any]:
        """Remove a role from a member."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            await self._api_call(
                "DELETE", f"/guilds/{gid}/members/{user_id}/roles/{role_id}"
            )
            return {
                "success": True,
                "message": f"Role {role_id} removed from user {user_id}",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def delete_message(
        self, channel_id: int, message_id: int
    ) -> dict[str, Any]:
        """Delete a message in a channel."""
        try:
            await self._api_call(
                "DELETE", f"/channels/{channel_id}/messages/{message_id}"
            )
            return {"success": True, "message": "Message deleted"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def get_guild_info(self, guild_id: int | None = None) -> dict[str, Any]:
        """Get guild information."""
        gid = guild_id or self._guild_id
        if not gid:
            return {"success": False, "message": "No guild_id configured"}
        try:
            guild = await self._api_call(
                "GET", f"/guilds/{gid}?with_counts=true"
            )
            return {"success": True, "guild": guild}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def purge_messages(
        self,
        channel_id: int,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Bulk delete messages in a channel (max 100, messages < 14 days old)."""
        try:
            # First fetch the messages
            messages = await self._api_call(
                "GET", f"/channels/{channel_id}/messages?limit={min(limit, 100)}"
            )
            if not messages:
                return {"success": True, "message": "No messages to delete", "deleted": 0}

            message_ids = [m["id"] for m in messages]

            if len(message_ids) == 1:
                await self._api_call(
                    "DELETE", f"/channels/{channel_id}/messages/{message_ids[0]}"
                )
            else:
                await self._api_call(
                    "POST",
                    f"/channels/{channel_id}/messages/bulk-delete",
                    json={"messages": message_ids},
                )

            return {
                "success": True,
                "message": f"Deleted {len(message_ids)} messages",
                "deleted": len(message_ids),
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Polling for incoming messages (discord.py gateway) ─────

    def set_message_handler(
        self, handler: Callable[[str, dict[str, Any]], Awaitable[None]]
    ) -> None:
        """Set the callback for incoming messages."""
        self._on_message = handler

    async def start(self) -> None:
        """Start the Discord bot client for receiving messages."""
        if self._running:
            return
        self._running = True

        if not self._token:
            logger.warning("Cannot start Discord bot — no bot token")
            self._running = False
            return

        self._ready_event.clear()
        self._bot_task = asyncio.create_task(self._run_bot())
        logger.info("Discord bot starting...")

        # Wait for the bot to be ready (max 15s)
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=15)
            logger.info("Discord bot is ready and listening")
        except TimeoutError:
            logger.warning("Discord bot did not become ready within 15s, continuing anyway")

    async def stop(self) -> None:
        """Stop the Discord bot client."""
        self._running = False

        if self._client and not self._client.is_closed():
            await self._client.close()

        if self._bot_task and not self._bot_task.done():
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
        self._bot_task = None
        self._client = None

        # Close REST session
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

        logger.info("Discord bot stopped")

    async def _run_bot(self) -> None:
        """Run the discord.py client in the background."""
        try:
            import discord

            intents = discord.Intents.default()
            intents.message_content = True
            intents.members = True
            intents.guilds = True

            client = discord.Client(intents=intents)
            self._client = client

            @client.event
            async def on_ready():
                logger.info(f"Discord bot logged in as {client.user}")
                self._ready_event.set()

                # Auto-detect guild if not set and bot is in one guild
                if not self._guild_id and len(client.guilds) > 0:
                    guild = client.guilds[0]
                    self._config["guild_id"] = str(guild.id)
                    self._config["guild_name"] = guild.name
                    self._config_store.save(self._config)
                    logger.info(f"Auto-detected guild: {guild.name} ({guild.id})")

            @client.event
            async def on_message(message):
                # Ignore messages from the bot itself
                if message.author == client.user:
                    return

                # Auto-save guild_id and channel_id if not set
                if not self._guild_id and message.guild:
                    self._config["guild_id"] = str(message.guild.id)
                    self._config["guild_name"] = message.guild.name
                    self._config_store.save(self._config)
                    logger.info(f"Auto-detected guild: {message.guild.name}")

                if not self._channel_id and message.channel:
                    self._config["channel_id"] = str(message.channel.id)
                    self._config_store.save(self._config)
                    logger.info(f"Auto-detected channel: {message.channel.id}")

                text = message.content
                if text and self._on_message:
                    metadata = {
                        "channel_id": message.channel.id,
                        "guild_id": message.guild.id if message.guild else None,
                        "guild_name": message.guild.name if message.guild else None,
                        "author_id": message.author.id,
                        "author_name": str(message.author),
                        "author_display_name": message.author.display_name,
                        "message_id": message.id,
                        "source": "discord",
                    }
                    try:
                        await self._on_message(text, metadata)
                    except Exception as e:
                        logger.exception(f"Error in message handler: {e}")
                        try:
                            await message.channel.send(
                                f"⚠️ Error processing your message: {str(e)[:200]}"
                            )
                        except Exception:
                            pass

            await client.start(self._token)

        except asyncio.CancelledError:
            if self._client and not self._client.is_closed():
                await self._client.close()
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
            self._running = False
            self._ready_event.set()  # Unblock anyone waiting

    async def send_typing(self, channel_id: int | str | None = None) -> None:
        """Send a typing indicator to a channel."""
        target = channel_id or self._channel_id
        if not target:
            return
        try:
            await self._api_call("POST", f"/channels/{int(target)}/typing")
        except Exception:
            pass


def _split_message(text: str, max_len: int = 1950) -> list[str]:
    """Split a long message into chunks that fit Discord's 2000 char limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break
        # Try to split at a newline
        split_at = text.rfind("\n", 0, max_len)
        if split_at == -1:
            split_at = max_len
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
