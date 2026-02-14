"""Shared test fixtures for Scala 40."""

from __future__ import annotations

import pytest

from src.db.memory import (
    InMemoryGameRepository,
    InMemoryLobbyRepository,
    InMemoryUserRepository,
)


class MockTelegramClient:
    """Records all Telegram API calls for test assertions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def send_message(
        self,
        chat_id: str | int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        self.calls.append((
            "send_message",
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": reply_markup,
            },
        ))
        return {"ok": True, "result": {"message_id": len(self.calls)}}

    def edit_message(
        self,
        chat_id: str | int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "HTML",
    ) -> dict:
        self.calls.append((
            "edit_message",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            },
        ))
        return {"ok": True, "result": {"message_id": message_id}}

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict:
        self.calls.append((
            "answer_callback_query",
            {
                "callback_query_id": callback_query_id,
                "text": text,
                "show_alert": show_alert,
            },
        ))
        return {"ok": True}

    def delete_message(
        self, chat_id: str | int, message_id: int
    ) -> dict:
        self.calls.append((
            "delete_message",
            {"chat_id": chat_id, "message_id": message_id},
        ))
        return {"ok": True}

    def get_calls(self, method: str) -> list[dict]:
        """Get all calls for a specific method."""
        return [kwargs for m, kwargs in self.calls if m == method]

    def last_call(self, method: str) -> dict | None:
        """Get the last call for a specific method."""
        calls = self.get_calls(method)
        return calls[-1] if calls else None


@pytest.fixture
def game_repo():
    return InMemoryGameRepository()


@pytest.fixture
def lobby_repo():
    return InMemoryLobbyRepository()


@pytest.fixture
def user_repo():
    return InMemoryUserRepository()


@pytest.fixture
def mock_telegram():
    return MockTelegramClient()
