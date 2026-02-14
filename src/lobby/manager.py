"""Lobby management for Scala 40."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from src.db.repository import GameRepository, LobbyRepository, UserRepository
from src.game.engine import GameEngine
from src.utils.constants import (
    DEFAULT_ELIMINATION_SCORE,
    MAX_PLAYERS,
    MIN_PLAYERS,
    STATUS_CLOSED,
    STATUS_IN_GAME,
    STATUS_WAITING,
)
from src.utils.crypto import generate_lobby_code


@dataclass
class LobbyResult:
    success: bool
    lobby: dict | None = None
    game_id: str | None = None
    error: str | None = None


class LobbyManager:
    def __init__(
        self,
        lobby_repo: LobbyRepository,
        user_repo: UserRepository,
        game_engine: GameEngine,
    ) -> None:
        self._lobby_repo = lobby_repo
        self._user_repo = user_repo
        self._engine = game_engine

    def create_lobby(
        self,
        host_user_id: str,
        chat_id: str,
        settings: dict | None = None,
    ) -> LobbyResult:
        """Create a new lobby. Host is auto-joined."""
        code = generate_lobby_code()
        lobby_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        lobby = {
            "lobbyId": lobby_id,
            "code": code,
            "hostUserId": host_user_id,
            "players": [
                {"userId": host_user_id, "ready": False}
            ],
            "status": STATUS_WAITING,
            "settings": settings or {
                "elimination_score": DEFAULT_ELIMINATION_SCORE,
                "variants": [],
            },
            "chatId": chat_id,
            "createdAt": now,
        }
        self._lobby_repo.save_lobby(lobby)
        return LobbyResult(success=True, lobby=lobby)

    def join_lobby(self, user_id: str, code: str) -> LobbyResult:
        """Join a lobby by code."""
        lobby = self._lobby_repo.get_lobby_by_code(code)
        if lobby is None:
            return LobbyResult(success=False, error="Lobby non trovata")

        if lobby["status"] != STATUS_WAITING:
            return LobbyResult(success=False, error="La lobby non accetta giocatori")

        if len(lobby["players"]) >= MAX_PLAYERS:
            return LobbyResult(success=False, error="La lobby è piena (max 4)")

        # Check not already in lobby
        if any(p["userId"] == user_id for p in lobby["players"]):
            return LobbyResult(success=False, error="Sei già in questa lobby")

        lobby["players"].append({"userId": user_id, "ready": False})
        self._lobby_repo.save_lobby(lobby)
        return LobbyResult(success=True, lobby=lobby)

    def leave_lobby(self, user_id: str, lobby_id: str) -> LobbyResult:
        """Leave a lobby. If host leaves, close it."""
        lobby = self._lobby_repo.get_lobby(lobby_id)
        if lobby is None:
            return LobbyResult(success=False, error="Lobby non trovata")

        if not any(p["userId"] == user_id for p in lobby["players"]):
            return LobbyResult(success=False, error="Non sei in questa lobby")

        if lobby["hostUserId"] == user_id:
            lobby["status"] = STATUS_CLOSED
            self._lobby_repo.save_lobby(lobby)
            return LobbyResult(success=True, lobby=lobby)

        lobby["players"] = [
            p for p in lobby["players"] if p["userId"] != user_id
        ]
        self._lobby_repo.save_lobby(lobby)
        return LobbyResult(success=True, lobby=lobby)

    def set_ready(self, user_id: str, lobby_id: str) -> LobbyResult:
        """Toggle ready status."""
        lobby = self._lobby_repo.get_lobby(lobby_id)
        if lobby is None:
            return LobbyResult(success=False, error="Lobby non trovata")

        for player in lobby["players"]:
            if player["userId"] == user_id:
                player["ready"] = not player["ready"]
                self._lobby_repo.save_lobby(lobby)
                return LobbyResult(success=True, lobby=lobby)

        return LobbyResult(success=False, error="Non sei in questa lobby")

    def start_game(self, user_id: str, lobby_id: str) -> LobbyResult:
        """Start a game from the lobby. Only host, all must be ready."""
        lobby = self._lobby_repo.get_lobby(lobby_id)
        if lobby is None:
            return LobbyResult(success=False, error="Lobby non trovata")

        if lobby["hostUserId"] != user_id:
            return LobbyResult(
                success=False, error="Solo l'host può avviare la partita"
            )

        if lobby["status"] != STATUS_WAITING:
            return LobbyResult(success=False, error="La lobby non è in attesa")

        if len(lobby["players"]) < MIN_PLAYERS:
            return LobbyResult(
                success=False, error=f"Servono almeno {MIN_PLAYERS} giocatori"
            )

        if not all(p["ready"] for p in lobby["players"]):
            return LobbyResult(
                success=False, error="Non tutti i giocatori sono pronti"
            )

        # Create game
        player_ids = [p["userId"] for p in lobby["players"]]
        game = self._engine.create_game(
            player_ids=player_ids,
            lobby_id=lobby_id,
            settings=lobby.get("settings"),
        )
        result = self._engine.start_round(game.game_id)

        if not result.success:
            return LobbyResult(success=False, error=result.error)

        # Update lobby status
        lobby["status"] = STATUS_IN_GAME
        self._lobby_repo.save_lobby(lobby)

        return LobbyResult(
            success=True, lobby=lobby, game_id=game.game_id
        )

    def get_lobby(self, lobby_id: str) -> dict | None:
        return self._lobby_repo.get_lobby(lobby_id)

    def get_lobby_by_code(self, code: str) -> dict | None:
        return self._lobby_repo.get_lobby_by_code(code)
