"""Dependency container for bot handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.db.repository import (
        GameRepository,
        LobbyRepository,
        UserRepository,
    )
    from src.game.engine import GameEngine
    from src.lobby.manager import LobbyManager
    from src.utils.telegram import TelegramClient


@dataclass
class Deps:
    """Bundles all dependencies for handler functions."""

    engine: GameEngine
    lobby_manager: LobbyManager
    game_repo: GameRepository
    lobby_repo: LobbyRepository
    user_repo: UserRepository
    telegram: TelegramClient
