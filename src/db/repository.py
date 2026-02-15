"""Repository protocol interfaces for Scala 40 persistence."""

from __future__ import annotations

from typing import Protocol

from src.game.models import GameState


class GameRepository(Protocol):
    def get_game(self, game_id: str) -> GameState | None:
        ...

    def save_game(self, game: GameState) -> None:
        ...

    def delete_game(self, game_id: str) -> None:
        ...


class LobbyRepository(Protocol):
    def get_lobby(self, lobby_id: str) -> dict | None:
        ...

    def save_lobby(self, lobby: dict) -> None:
        ...

    def delete_lobby(self, lobby_id: str) -> None:
        ...

    def get_lobby_by_code(self, code: str) -> dict | None:
        ...


class UserRepository(Protocol):
    def get_user(self, user_id: str) -> dict | None:
        ...

    def save_user(self, user: dict) -> None:
        ...

    def update_user_stats(self, user_id: str, stats_update: dict) -> None:
        ...
