"""Update router — dispatches Telegram updates to handlers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.bot.deps import Deps

logger = logging.getLogger("scala40.router")


def route_update(update: dict, deps: Deps) -> None:
    """Route a Telegram update to the appropriate handler."""
    from src.bot.callbacks import handle_callback
    from src.bot.commands import handle_command

    if "callback_query" in update:
        cq = update["callback_query"]
        user_id = str(cq["from"]["id"])
        chat_id = str(cq["message"]["chat"]["id"])
        message_id = cq["message"]["message_id"]
        data = cq.get("data", "")
        cq_id = cq["id"]
        handle_callback(user_id, chat_id, message_id, data, cq_id, deps)
        return

    message = update.get("message")
    if message is None:
        return

    text = message.get("text", "")
    if not text.startswith("/"):
        return

    user_id = str(message["from"]["id"])
    chat_id = str(message["chat"]["id"])

    # Strip @botname suffix
    parts = text.split(None, 1)
    command = parts[0].split("@")[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handle_command(command, args, user_id, chat_id, deps)
