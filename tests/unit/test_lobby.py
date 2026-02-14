"""Tests for lobby manager."""

import pytest

from src.db.memory import (
    InMemoryGameRepository,
    InMemoryLobbyRepository,
    InMemoryUserRepository,
)
from src.game.engine import GameEngine
from src.lobby.manager import LobbyManager
from src.utils.constants import STATUS_CLOSED, STATUS_IN_GAME, STATUS_WAITING
from src.utils.crypto import create_rng


@pytest.fixture
def lobby_manager():
    lobby_repo = InMemoryLobbyRepository()
    user_repo = InMemoryUserRepository()
    game_repo = InMemoryGameRepository()
    engine = GameEngine(game_repo, create_rng(42))
    return LobbyManager(lobby_repo, user_repo, engine)


class TestCreateLobby:
    def test_creates_lobby(self, lobby_manager):
        result = lobby_manager.create_lobby("host1", "chat1")
        assert result.success
        assert result.lobby is not None
        assert result.lobby["hostUserId"] == "host1"
        assert len(result.lobby["code"]) == 6
        assert result.lobby["status"] == STATUS_WAITING

    def test_host_auto_joined(self, lobby_manager):
        result = lobby_manager.create_lobby("host1", "chat1")
        assert len(result.lobby["players"]) == 1
        assert result.lobby["players"][0]["userId"] == "host1"


class TestJoinLobby:
    def test_join_by_code(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]

        join_result = lobby_manager.join_lobby("player2", code)
        assert join_result.success
        assert len(join_result.lobby["players"]) == 2

    def test_join_nonexistent_code(self, lobby_manager):
        result = lobby_manager.join_lobby("player2", "ZZZZZZ")
        assert not result.success
        assert "non trovata" in result.error.lower()

    def test_join_full_lobby(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]

        lobby_manager.join_lobby("p2", code)
        lobby_manager.join_lobby("p3", code)
        lobby_manager.join_lobby("p4", code)

        result = lobby_manager.join_lobby("p5", code)
        assert not result.success
        assert "piena" in result.error.lower()

    def test_join_already_in_lobby(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]

        result = lobby_manager.join_lobby("host1", code)
        assert not result.success
        assert "già" in result.error.lower()


class TestReady:
    def test_toggle_ready(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        lobby_id = create_result.lobby["lobbyId"]

        result = lobby_manager.set_ready("host1", lobby_id)
        assert result.success
        assert result.lobby["players"][0]["ready"] is True

        result = lobby_manager.set_ready("host1", lobby_id)
        assert result.success
        assert result.lobby["players"][0]["ready"] is False

    def test_ready_not_in_lobby(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        lobby_id = create_result.lobby["lobbyId"]
        result = lobby_manager.set_ready("stranger", lobby_id)
        assert not result.success


class TestStartGame:
    def test_start_all_ready(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]
        lobby_id = create_result.lobby["lobbyId"]

        lobby_manager.join_lobby("p2", code)
        lobby_manager.set_ready("host1", lobby_id)
        lobby_manager.set_ready("p2", lobby_id)

        result = lobby_manager.start_game("host1", lobby_id)
        assert result.success
        assert result.game_id is not None
        assert result.lobby["status"] == STATUS_IN_GAME

    def test_start_not_all_ready_fails(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]
        lobby_id = create_result.lobby["lobbyId"]

        lobby_manager.join_lobby("p2", code)
        lobby_manager.set_ready("host1", lobby_id)
        # p2 not ready

        result = lobby_manager.start_game("host1", lobby_id)
        assert not result.success
        assert "pronti" in result.error.lower()

    def test_start_not_host_fails(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]
        lobby_id = create_result.lobby["lobbyId"]

        lobby_manager.join_lobby("p2", code)
        lobby_manager.set_ready("host1", lobby_id)
        lobby_manager.set_ready("p2", lobby_id)

        result = lobby_manager.start_game("p2", lobby_id)
        assert not result.success
        assert "host" in result.error.lower()

    def test_start_too_few_players_fails(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        lobby_id = create_result.lobby["lobbyId"]
        lobby_manager.set_ready("host1", lobby_id)

        result = lobby_manager.start_game("host1", lobby_id)
        assert not result.success
        assert "almeno" in result.error.lower()


class TestLeaveLobby:
    def test_player_leaves(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        code = create_result.lobby["code"]
        lobby_id = create_result.lobby["lobbyId"]
        lobby_manager.join_lobby("p2", code)

        result = lobby_manager.leave_lobby("p2", lobby_id)
        assert result.success
        assert len(result.lobby["players"]) == 1

    def test_host_leaves_closes_lobby(self, lobby_manager):
        create_result = lobby_manager.create_lobby("host1", "chat1")
        lobby_id = create_result.lobby["lobbyId"]

        result = lobby_manager.leave_lobby("host1", lobby_id)
        assert result.success
        assert result.lobby["status"] == STATUS_CLOSED

    def test_leave_nonexistent_lobby(self, lobby_manager):
        result = lobby_manager.leave_lobby("p1", "fake-id")
        assert not result.success
