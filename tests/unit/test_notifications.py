"""Tests for turn notifications."""

from src.bot.deps import Deps
from src.bot.notifications import (
    notify_round_end,
    notify_table_update,
    notify_turn_start,
)
from src.db.memory import (
    InMemoryGameRepository,
    InMemoryLobbyRepository,
    InMemoryUserRepository,
)
from src.game.engine import GameEngine
from src.game.models import GameState
from src.lobby.manager import LobbyManager
from src.utils.constants import (
    STATUS_FINISHED,
    STATUS_ROUND_END,
)

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


def _make_game(deps: Deps) -> GameState:
    """Create a game via engine for notification tests."""
    # Register users
    deps.user_repo.save_user({"userId": "p1", "chatId": "chat_p1"})
    deps.user_repo.save_user({"userId": "p2", "chatId": "chat_p2"})

    game = deps.engine.create_game(["p1", "p2"], lobby_id="lob1")
    result = deps.engine.start_round(game.game_id)
    assert result.success
    assert result.game is not None
    return result.game


class TestNotifyTurnStart:
    def test_sends_hand_and_draw_kb(self):
        deps, tg = _make_deps()
        game = _make_game(deps)

        notify_turn_start(game, deps)

        sends = tg.get_calls("send_message")
        # Should send hand + draw keyboard to current player's chat
        current = game.current_turn_user_id
        user = deps.user_repo.get_user(current)
        player_sends = [s for s in sends if s["chat_id"] == user["chatId"]]
        assert len(player_sends) == 2
        assert "mano" in player_sends[0]["text"].lower()
        assert player_sends[1]["reply_markup"] is not None

    def test_no_user_no_crash(self):
        deps, tg = _make_deps()
        game = _make_game(deps)
        # Remove the user record
        deps.user_repo._users.pop(game.current_turn_user_id, None)
        # Should not crash
        notify_turn_start(game, deps)
        assert len(tg.get_calls("send_message")) == 0


class TestNotifyTableUpdate:
    def test_sends_table(self):
        deps, tg = _make_deps()
        game = _make_game(deps)

        notify_table_update(game, "group_chat", deps)

        msg = tg.last_call("send_message")
        assert msg["chat_id"] == "group_chat"
        assert "Smazzata" in msg["text"]


class TestNotifyRoundEnd:
    def test_finished_announces_winner(self):
        deps, tg = _make_deps()
        game = _make_game(deps)
        game.status = STATUS_FINISHED
        # Save game with new status
        deps.game_repo.save_game(game)

        events = [
            {"event": "closure", "user_id": "p1"},
            {"event": "game_end", "winner": "p1"},
        ]
        notify_round_end(game, "group_chat", events, deps)

        sends = tg.get_calls("send_message")
        texts = [s["text"] for s in sends]
        assert any("Vince" in t for t in texts)
        assert any("p1" in t for t in texts)

    def test_elimination_announced(self):
        deps, tg = _make_deps()
        game = _make_game(deps)
        game.status = STATUS_FINISHED
        deps.game_repo.save_game(game)

        events = [
            {"event": "closure", "user_id": "p1"},
            {
                "event": "elimination",
                "user_id": "p2",
                "total_score": 105,
            },
            {"event": "game_end", "winner": "p1"},
        ]
        notify_round_end(game, "group_chat", events, deps)

        sends = tg.get_calls("send_message")
        texts = [s["text"] for s in sends]
        assert any("eliminato" in t for t in texts)

    def test_round_end_starts_new_round(self):
        deps, tg = _make_deps()
        game = _make_game(deps)
        game.status = STATUS_ROUND_END
        deps.game_repo.save_game(game)

        events = [{"event": "closure", "user_id": "p1"}]
        notify_round_end(game, "group_chat", events, deps)

        sends = tg.get_calls("send_message")
        texts = [s["text"] for s in sends]
        # Should announce new smazzata + send hands + turn start
        assert any("Smazzata" in t for t in texts)
