"""AWS Lambda entry point for Scala 40 Telegram bot.

This is a thin adapter that routes Telegram webhook updates to the
appropriate bot command or callback handler. All business logic lives
in src/game/, src/lobby/, and src/bot/.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger("scala40.handler")
logger.setLevel(logging.INFO)

# Module-level deps for Lambda warm starts
_deps = None


def _init_deps(overrides: dict | None = None):
    """Initialize dependencies (lazily, once per Lambda container)."""
    global _deps

    if overrides:
        from src.bot.deps import Deps

        _deps = Deps(**overrides)
        return _deps

    from src.bot.deps import Deps
    from src.db.dynamodb import (
        DynamoDBGameRepository,
        DynamoDBLobbyRepository,
        DynamoDBUserRepository,
    )
    from src.game.engine import GameEngine
    from src.lobby.manager import LobbyManager
    from src.utils.telegram import TelegramClient

    game_repo = DynamoDBGameRepository()
    lobby_repo = DynamoDBLobbyRepository()
    user_repo = DynamoDBUserRepository()
    engine = GameEngine(game_repo)
    lobby_manager = LobbyManager(lobby_repo, user_repo, engine)
    telegram = TelegramClient()

    _deps = Deps(
        engine=engine,
        lobby_manager=lobby_manager,
        game_repo=game_repo,
        lobby_repo=lobby_repo,
        user_repo=user_repo,
        telegram=telegram,
    )
    return _deps


def lambda_handler(event: dict, context: Any = None) -> dict:
    """Handle incoming Telegram webhook update via API Gateway."""
    global _deps

    # Validate webhook secret
    headers = event.get("headers", {})
    expected_secret = os.environ.get("WEBHOOK_SECRET", "")
    if expected_secret:
        received = headers.get("x-telegram-bot-api-secret-token", "")
        if received != expected_secret:
            logger.warning("Invalid webhook secret")
            return {"statusCode": 403, "body": "Forbidden"}

    try:
        body = json.loads(event.get("body", "{}"))
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON"}

    logger.info(
        json.dumps({"event": "webhook_received", "update_id": body.get("update_id")})
    )

    try:
        if _deps is None:
            _init_deps()

        from src.bot.router import route_update

        assert _deps is not None
        route_update(body, _deps)
    except Exception:
        logger.exception("Error processing update")

    # Always return 200 to Telegram
    return {"statusCode": 200, "body": json.dumps({"ok": True})}
