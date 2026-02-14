"""Full integration test: Telegram updates through the handler pipeline."""

from __future__ import annotations

import json

from src.bot.deps import Deps
from src.db.memory import (
    InMemoryGameRepository,
    InMemoryLobbyRepository,
    InMemoryUserRepository,
)
from src.game.engine import GameEngine
from src.handler import _init_deps, lambda_handler
from src.lobby.manager import LobbyManager

from tests.conftest import MockTelegramClient


def _make_event(body: dict) -> dict:
    """Build a fake API Gateway event."""
    return {"headers": {}, "body": json.dumps(body)}


def _command_update(user_id: int, chat_id: int, text: str, update_id: int = 1) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": user_id, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


def _callback_update(
    user_id: int,
    chat_id: int,
    message_id: int,
    data: str,
    cq_id: str = "cq1",
    update_id: int = 1,
) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": cq_id,
            "from": {"id": user_id},
            "message": {
                "message_id": message_id,
                "chat": {"id": chat_id, "type": "private"},
            },
            "data": data,
        },
    }


def _setup_deps() -> tuple[Deps, MockTelegramClient]:
    """Init deps with in-memory repos + mock telegram."""
    game_repo = InMemoryGameRepository()
    lobby_repo = InMemoryLobbyRepository()
    user_repo = InMemoryUserRepository()
    engine = GameEngine(game_repo)
    lobby_mgr = LobbyManager(lobby_repo, user_repo, engine)
    tg = MockTelegramClient()
    deps = _init_deps(
        overrides={
            "engine": engine,
            "lobby_manager": lobby_mgr,
            "game_repo": game_repo,
            "lobby_repo": lobby_repo,
            "user_repo": user_repo,
            "telegram": tg,
        }
    )
    return deps, tg


class TestHandlerBasics:
    def test_returns_200_on_valid_update(self):
        _setup_deps()
        event = _make_event({"update_id": 1})
        resp = lambda_handler(event)
        assert resp["statusCode"] == 200

    def test_returns_400_on_bad_json(self):
        _setup_deps()
        resp = lambda_handler({"headers": {}, "body": "not json"})
        assert resp["statusCode"] == 400

    def test_webhook_secret_check(self):
        import os

        _setup_deps()
        os.environ["WEBHOOK_SECRET"] = "secret123"
        try:
            resp = lambda_handler(
                {
                    "headers": {"x-telegram-bot-api-secret-token": "wrong"},
                    "body": "{}",
                }
            )
            assert resp["statusCode"] == 403

            resp = lambda_handler(
                {
                    "headers": {"x-telegram-bot-api-secret-token": "secret123"},
                    "body": "{}",
                }
            )
            assert resp["statusCode"] == 200
        finally:
            os.environ.pop("WEBHOOK_SECRET", None)


class TestFullGameFlow:
    def test_lobby_to_draw_to_discard(self):
        deps, tg = _setup_deps()

        # /start for both players
        resp = lambda_handler(_make_event(_command_update(1, 100, "/start", 1)))
        assert resp["statusCode"] == 200

        resp = lambda_handler(_make_event(_command_update(2, 200, "/start", 2)))
        assert resp["statusCode"] == 200

        # /newlobby
        lambda_handler(_make_event(_command_update(1, 100, "/newlobby", 3)))
        user1 = deps.user_repo.get_user("1")
        assert user1 is not None
        lobby = deps.lobby_repo.get_lobby(user1["currentLobbyId"])
        assert lobby is not None
        code = lobby["code"]

        # /join
        lambda_handler(_make_event(_command_update(2, 200, f"/join {code}", 4)))

        # /ready x2
        lambda_handler(_make_event(_command_update(1, 100, "/ready", 5)))
        lambda_handler(_make_event(_command_update(2, 200, "/ready", 6)))

        # /startgame
        tg.calls.clear()
        lambda_handler(_make_event(_command_update(1, 100, "/startgame", 7)))

        # Verify table + hands were sent
        sends = tg.get_calls("send_message")
        assert any("Smazzata" in s["text"] for s in sends)
        assert any("mano" in s["text"].lower() for s in sends)

        # Get game state
        user1 = deps.user_repo.get_user("1")
        game_id = user1["currentGameId"]
        game = deps.engine.get_game(game_id)
        current = game.current_turn_user_id
        current_int = int(current)
        current_chat = 100 if current == "1" else 200

        # Draw from deck
        tg.calls.clear()
        lambda_handler(
            _make_event(_callback_update(current_int, current_chat, 50, "draw:deck"))
        )
        sends = tg.get_calls("send_message")
        assert any("mano" in s["text"].lower() for s in sends)

        # Game should be in play/discard phase now
        game = deps.engine.get_game(game_id)
        assert game.current_turn_user_id == current
        player = game.get_player(current)
        assert len(player.hand) == 14  # 13 + 1 drawn

        # Discard first card
        card = player.hand[0]
        tg.calls.clear()
        lambda_handler(
            _make_event(
                _callback_update(
                    current_int,
                    current_chat,
                    51,
                    f"disc:{card.compact()}",
                )
            )
        )

        # Turn should have advanced to the other player
        game = deps.engine.get_game(game_id)
        assert game.current_turn_user_id != current

    def test_hand_table_scores_commands(self):
        deps, tg = _setup_deps()

        # Set up game
        lambda_handler(_make_event(_command_update(1, 100, "/start")))
        lambda_handler(_make_event(_command_update(2, 200, "/start")))
        lambda_handler(_make_event(_command_update(1, 100, "/newlobby")))
        user1 = deps.user_repo.get_user("1")
        lobby = deps.lobby_repo.get_lobby(user1["currentLobbyId"])
        lambda_handler(_make_event(_command_update(2, 200, f"/join {lobby['code']}")))
        lambda_handler(_make_event(_command_update(1, 100, "/ready")))
        lambda_handler(_make_event(_command_update(2, 200, "/ready")))
        lambda_handler(_make_event(_command_update(1, 100, "/startgame")))

        # /hand
        tg.calls.clear()
        lambda_handler(_make_event(_command_update(1, 100, "/hand")))
        text = tg.last_call("send_message")["text"]
        assert "mano" in text.lower()

        # /table
        tg.calls.clear()
        lambda_handler(_make_event(_command_update(1, 100, "/table")))
        text = tg.last_call("send_message")["text"]
        assert "Smazzata" in text

        # /scores
        tg.calls.clear()
        lambda_handler(_make_event(_command_update(1, 100, "/scores")))
        text = tg.last_call("send_message")["text"]
        assert "Punteggi" in text


class TestRouterEdgeCases:
    def test_non_command_message_ignored(self):
        _setup_deps()
        resp = lambda_handler(
            _make_event(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 1,
                        "from": {"id": 1},
                        "chat": {"id": 1, "type": "private"},
                        "text": "hello",
                    },
                }
            )
        )
        assert resp["statusCode"] == 200

    def test_empty_update_ignored(self):
        _setup_deps()
        resp = lambda_handler(_make_event({"update_id": 1}))
        assert resp["statusCode"] == 200
