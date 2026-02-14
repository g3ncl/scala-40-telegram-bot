"""AWS Lambda entry point for Scala 40 Telegram bot.

This is a thin adapter that routes Telegram webhook updates to the
appropriate bot command or callback handler. All business logic lives
in src/game/, src/lobby/, and src/bot/.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("scala40.handler")
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    """Handle incoming Telegram webhook update via API Gateway."""
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

    logger.info(json.dumps({"event": "webhook_received", "update_id": body.get("update_id")}))

    # TODO: Route to bot/commands.py and bot/callbacks.py
    # This will be implemented in Phase 2 when we add Telegram integration.
    # For now, acknowledge the update.

    return {"statusCode": 200, "body": json.dumps({"ok": True})}
