"""Telegram Bot API client using httpx."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("scala40.telegram")

BASE_URL = "https://api.telegram.org/bot{token}"


class TelegramClient:
    """Synchronous Telegram Bot API wrapper."""

    def __init__(
        self,
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._base = BASE_URL.format(token=self._token)
        self._client = client or httpx.Client(timeout=10.0)

    def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        payload: dict = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._post("sendMessage", payload)

    def edit_message(
        self,
        chat_id: str | int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        payload: dict = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._post("editMessageText", payload)

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict:
        payload: dict = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        return self._post("answerCallbackQuery", payload)

    def delete_message(
        self, chat_id: str | int, message_id: int
    ) -> dict:
        return self._post(
            "deleteMessage",
            {"chat_id": chat_id, "message_id": message_id},
        )

    def _post(self, method: str, payload: dict) -> dict:
        url = f"{self._base}/{method}"
        response = self._client.post(url, json=payload)
        data: dict = response.json()
        if not data.get("ok"):
            logger.error("Telegram API error on %s: %s", method, data)
        return data
