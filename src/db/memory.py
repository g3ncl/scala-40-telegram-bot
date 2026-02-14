"""In-memory repository implementations for testing and local CLI."""

from __future__ import annotations

import copy

from src.game.models import GameState


class InMemoryGameRepository:
    def __init__(self) -> None:
        self._games: dict[str, GameState] = {}

    def get_game(self, game_id: str) -> GameState | None:
        game = self._games.get(game_id)
        if game is None:
            return None
        return copy.deepcopy(game)

    def save_game(self, game: GameState) -> None:
        existing = self._games.get(game.game_id)
        if existing is not None and existing.version != game.version:
            raise ValueError(
                f"Version conflict: expected {game.version}, found {existing.version}"
            )
        saved = copy.deepcopy(game)
        saved.version = game.version + 1
        self._games[game.game_id] = saved

    def delete_game(self, game_id: str) -> None:
        self._games.pop(game_id, None)


class InMemoryLobbyRepository:
    def __init__(self) -> None:
        self._lobbies: dict[str, dict] = {}

    def get_lobby(self, lobby_id: str) -> dict | None:
        lobby = self._lobbies.get(lobby_id)
        return copy.deepcopy(lobby) if lobby else None

    def save_lobby(self, lobby: dict) -> None:
        self._lobbies[lobby["lobbyId"]] = copy.deepcopy(lobby)

    def delete_lobby(self, lobby_id: str) -> None:
        self._lobbies.pop(lobby_id, None)

    def get_lobby_by_code(self, code: str) -> dict | None:
        for lobby in self._lobbies.values():
            if lobby.get("code") == code:
                return copy.deepcopy(lobby)
        return None


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[str, dict] = {}

    def get_user(self, user_id: str) -> dict | None:
        user = self._users.get(user_id)
        return copy.deepcopy(user) if user else None

    def save_user(self, user: dict) -> None:
        self._users[user["userId"]] = copy.deepcopy(user)

    def update_user_stats(self, user_id: str, stats_update: dict) -> None:
        user = self._users.get(user_id)
        if user is None:
            return
        if "stats" not in user:
            user["stats"] = {}
        user["stats"].update(stats_update)
