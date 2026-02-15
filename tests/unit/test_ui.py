"""Tests for UI components (Keyboards and Callbacks)."""

from src.bot.callbacks import handle_callback
from src.bot.deps import Deps
from src.bot.messages import build_lobby_keyboard, build_main_menu_keyboard
from src.db.memory import (
    InMemoryGameRepository,
    InMemoryLobbyRepository,
    InMemoryUserRepository,
)
from src.game.engine import GameEngine
from src.lobby.manager import LobbyManager

from tests.conftest import MockTelegramClient


def _make_deps() -> tuple[Deps, MockTelegramClient]:
    game_repo = InMemoryGameRepository()
    lobby_repo = InMemoryLobbyRepository()
    user_repo = InMemoryUserRepository()
    engine = GameEngine(game_repo)
    lobby_mgr = LobbyManager(lobby_repo, user_repo, engine)
    tg = MockTelegramClient()
    deps = Deps(
        engine=engine,
        lobby_manager=lobby_mgr,
        game_repo=game_repo,
        lobby_repo=lobby_repo,
        user_repo=user_repo,
        telegram=tg,
    )
    return deps, tg


class TestKeyboards:
    def test_main_menu_structure(self):
        kb = build_main_menu_keyboard()
        assert "inline_keyboard" in kb
        rows = kb["inline_keyboard"]
        assert len(rows) >= 1
        btn_texts = [btn["text"] for row in rows for btn in row]
        assert any("Crea" in t for t in btn_texts)
        assert any("Aiuto" in t for t in btn_texts)
        btn_data = [btn["callback_data"] for row in rows for btn in row]
        assert "main:new" in btn_data
        assert "main:help" in btn_data

    def test_lobby_keyboard_host_not_ready(self):
        lobby = {
            "lobbyId": "l1",
            "hostUserId": "h1",
            "players": [{"userId": "h1", "ready": False}],
        }
        kb = build_lobby_keyboard(lobby, "h1")
        rows = kb["inline_keyboard"]
        btn_texts = [btn["text"] for row in rows for btn in row]
        # Should have Ready, Leave, Refresh. No Start (not ready, not enough players)
        assert any("Pronto" in t for t in btn_texts)
        assert any("Esci" in t for t in btn_texts)
        assert not any("Avvia" in t for t in btn_texts)

    def test_lobby_keyboard_host_ready_enough_players(self):
        lobby = {
            "lobbyId": "l1",
            "hostUserId": "h1",
            "players": [
                {"userId": "h1", "ready": True},
                {"userId": "p2", "ready": True},
            ],
        }
        kb = build_lobby_keyboard(lobby, "h1")
        rows = kb["inline_keyboard"]
        btn_texts = [btn["text"] for row in rows for btn in row]
        # Should have Start
        assert any("Avvia" in t for t in btn_texts)

    def test_lobby_keyboard_guest(self):
        lobby = {
            "lobbyId": "l1",
            "hostUserId": "h1",
            "players": [
                {"userId": "h1", "ready": True},
                {"userId": "p2", "ready": True},
            ],
        }
        kb = build_lobby_keyboard(lobby, "p2")
        rows = kb["inline_keyboard"]
        btn_texts = [btn["text"] for row in rows for btn in row]
        # Guest cannot start
        assert not any("Avvia" in t for t in btn_texts)


class TestMainCallbacks:
    def test_main_new(self):
        deps, tg = _make_deps()
        handle_callback("u1", "c1", 123, "main:new", "cq1", deps)

        # Should create lobby and edit message
        user = deps.user_repo.get_user("u1")
        assert user["currentLobbyId"] is not None

        assert tg.last_call("edit_message") is not None
        edit = tg.last_call("edit_message")
        assert "Lobby" in edit["text"]
        assert edit["reply_markup"] is not None

    def test_main_help(self):
        deps, tg = _make_deps()
        handle_callback("u1", "c1", 123, "main:help", "cq1", deps)
        edit = tg.last_call("edit_message")
        assert "Regole" in edit["text"]


class TestLobbyCallbacks:
    def test_lobby_ready(self):
        deps, tg = _make_deps()
        # Setup user in lobby
        res = deps.lobby_manager.create_lobby("u1", "c1")
        deps.user_repo.save_user(
            {"userId": "u1", "currentLobbyId": res.lobby["lobbyId"]}
        )

        handle_callback("u1", "c1", 123, "lobby:ready", "cq1", deps)

        lobby = deps.lobby_manager.get_lobby(res.lobby["lobbyId"])
        assert lobby["players"][0]["ready"] is True

        edit = tg.last_call("edit_message")
        assert "pronto" in edit["text"] or "Pronto" in str(edit["reply_markup"])

    def test_lobby_leave_host(self):
        deps, tg = _make_deps()
        res = deps.lobby_manager.create_lobby("u1", "c1")
        deps.user_repo.save_user(
            {"userId": "u1", "currentLobbyId": res.lobby["lobbyId"]}
        )

        handle_callback("u1", "c1", 123, "lobby:leave", "cq1", deps)

        user = deps.user_repo.get_user("u1")
        assert user["currentLobbyId"] is None

        edit = tg.last_call("edit_message")
        assert "Lobby chiusa" in edit["text"]

    def test_lobby_leave_guest(self):
        deps, tg = _make_deps()
        res = deps.lobby_manager.create_lobby("u1", "c1")
        lobby_id = res.lobby["lobbyId"]

        deps.lobby_manager.join_lobby("u2", res.lobby["code"])
        deps.user_repo.save_user({"userId": "u2", "currentLobbyId": lobby_id})

        handle_callback("u2", "c2", 456, "lobby:leave", "cq2", deps)

        user = deps.user_repo.get_user("u2")
        assert user["currentLobbyId"] is None

        edit = tg.last_call("edit_message")
        assert "lasciato" in edit["text"]

    def test_lobby_start(self):
        deps, tg = _make_deps()
        # Setup: 2 players, both ready
        res = deps.lobby_manager.create_lobby("u1", "c1")
        lobby_id = res.lobby["lobbyId"]
        deps.user_repo.save_user(
            {"userId": "u1", "currentLobbyId": lobby_id, "chatId": "c1"}
        )

        deps.lobby_manager.join_lobby("u2", res.lobby["code"])
        deps.user_repo.save_user(
            {"userId": "u2", "currentLobbyId": lobby_id, "chatId": "c2"}
        )

        deps.lobby_manager.set_ready("u1", lobby_id)
        deps.lobby_manager.set_ready("u2", lobby_id)

        handle_callback("u1", "c1", 123, "lobby:start", "cq1", deps)

        # Should have started game
        user = deps.user_repo.get_user("u1")
        assert user.get("currentGameId") is not None

        # Should have sent table and hands
        sends = tg.get_calls("send_message")
        assert any("Smazzata" in s["text"] for s in sends)
        assert any("mano" in s["text"].lower() for s in sends)
