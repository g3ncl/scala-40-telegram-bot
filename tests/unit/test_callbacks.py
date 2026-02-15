"""Tests for bot callback handlers."""

from src.bot.callbacks import handle_callback
from src.bot.commands import handle_command
from src.bot.deps import Deps
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


def _setup_game(deps: Deps) -> str:
    """Set up a 2-player game, return game_id."""
    handle_command("/start", "", "u1", "chat1", deps)
    handle_command("/start", "", "u2", "chat2", deps)
    handle_command("/newlobby", "", "u1", "chat1", deps)
    user = deps.user_repo.get_user("u1")
    assert user is not None
    assert user.get("currentLobbyId") is not None
    lobby = deps.lobby_repo.get_lobby(user["currentLobbyId"])
    assert lobby is not None
    handle_command("/join", lobby["code"], "u2", "chat2", deps)
    handle_command("/ready", "", "u1", "chat1", deps)
    handle_command("/ready", "", "u2", "chat2", deps)
    handle_command("/startgame", "", "u1", "chat1", deps)
    user = deps.user_repo.get_user("u1")
    assert user is not None
    res = user.get("currentGameId")
    assert isinstance(res, str)
    return res


class TestDrawCallback:
    def test_draw_from_deck(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        tg.calls.clear()

        handle_callback(current, "chat1", 100, "draw:deck", "cq1", deps)

        # Should ack + delete + send hand + send play keyboard
        assert len(tg.get_calls("answer_callback_query")) == 1
        assert len(tg.get_calls("delete_message")) == 1
        sends = tg.get_calls("send_message")
        assert any("mano" in s["text"].lower() for s in sends)
        assert any(s.get("reply_markup") for s in sends)

    def test_draw_wrong_turn(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        # Find who is NOT the current player
        other = [
            p.user_id for p in game.players if p.user_id != game.current_turn_user_id
        ][0]
        tg.calls.clear()

        handle_callback(other, "chat2", 100, "draw:deck", "cq1", deps)
        ack = tg.last_call("answer_callback_query")
        assert ack["text"] is not None  # error message


class TestMenuCallback:
    def test_menu_discard(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id

        # Draw first
        deps.engine.process_draw(game_id, current, "deck")
        tg.calls.clear()

        handle_callback(current, "chat1", 100, "menu:discard", "cq1", deps)
        edit = tg.last_call("edit_message")
        assert edit is not None
        assert edit["reply_markup"] is not None


class TestCardToggleCallback:
    def test_toggle_updates_keyboard(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        player = game.get_player(current)
        mask = "0" * len(player.hand)

        # Toggle first card
        new_mask = "1" + mask[1:]
        tg.calls.clear()
        handle_callback(
            current,
            "chat1",
            100,
            f"card:0:play:{new_mask}",
            "cq1",
            deps,
        )
        edit = tg.last_call("edit_message")
        assert edit is not None
        assert edit["reply_markup"] is not None


class TestDiscardCallback:
    def test_discard_advances_turn(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        player = game.get_player(current)

        # Draw first
        deps.engine.process_draw(game_id, current, "deck")
        game = deps.engine.get_game(game_id)
        player = game.get_player(current)
        card = player.hand[0]
        tg.calls.clear()

        handle_callback(
            current,
            "chat1",
            100,
            f"disc:{card.compact()}",
            "cq1",
            deps,
        )

        # Should ack + delete original message
        assert len(tg.get_calls("answer_callback_query")) == 1
        assert len(tg.get_calls("delete_message")) == 1
        # Should send table update + next player's turn
        sends = tg.get_calls("send_message")
        assert len(sends) > 0


class TestAttachCallbacks:
    def test_attach_card_shows_targets(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        player = game.get_player(current)
        card = player.hand[0]
        tg.calls.clear()

        handle_callback(
            current,
            "chat1",
            100,
            f"att_card:{card.compact()}",
            "cq1",
            deps,
        )
        edit = tg.last_call("edit_message")
        assert edit is not None
        assert "attaccare" in edit["text"].lower()


class TestCancelCallback:
    def test_cancel_returns_to_menu(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        tg.calls.clear()

        handle_callback(current, "chat1", 100, "cancel", "cq1", deps)
        edit = tg.last_call("edit_message")
        assert edit is not None
        assert edit["reply_markup"] is not None


class TestInvalidCallback:
    def test_unknown_prefix(self):
        deps, tg = _make_deps()
        game_id = _setup_game(deps)
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        tg.calls.clear()

        handle_callback(current, "chat1", 100, "xyz:foo", "cq1", deps)
        ack = tg.last_call("answer_callback_query")
        assert ack["text"] == "Azione non valida"
