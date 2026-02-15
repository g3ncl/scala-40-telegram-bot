"""Tests for bot command handlers."""

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


class TestStartCommand:
    def test_creates_user_and_sends_welcome(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        assert tg.last_call("send_message") is not None
        assert "/newlobby" in tg.last_call("send_message")["text"]
        assert deps.user_repo.get_user("u1") is not None

    def test_idempotent(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/start", "", "u1", "chat1", deps)
        assert len(tg.get_calls("send_message")) == 2


class TestHelpCommand:
    def test_sends_rules(self):
        deps, tg = _make_deps()
        handle_command("/help", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "Regole" in text


class TestNewLobbyCommand:
    def test_creates_lobby(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        calls = tg.get_calls("send_message")
        lobby_msg = calls[-1]["text"]
        assert "Lobby" in lobby_msg
        user = deps.user_repo.get_user("u1")
        assert user is not None
        assert user.get("currentLobbyId") is not None


class TestJoinCommand:
    def test_join_with_code(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        # Get lobby code
        user = deps.user_repo.get_user("u1")
        lobby = deps.lobby_repo.get_lobby(user["currentLobbyId"])
        code = lobby["code"]

        handle_command("/start", "", "u2", "chat2", deps)
        handle_command("/join", code, "u2", "chat2", deps)
        lobby = deps.lobby_repo.get_lobby(user["currentLobbyId"])
        player_ids = [p["userId"] for p in lobby["players"]]
        assert "u2" in player_ids

    def test_join_no_code(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/join", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "CODICE" in text

    def test_join_bad_code(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/join", "XXXXXX", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "Errore" in text


class TestLeaveCommand:
    def test_leave_lobby(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        user = deps.user_repo.get_user("u1")
        lobby_id = user["currentLobbyId"]

        handle_command("/start", "", "u2", "chat2", deps)
        lobby = deps.lobby_repo.get_lobby(lobby_id)
        handle_command("/join", lobby["code"], "u2", "chat2", deps)

        handle_command("/leave", "", "u2", "chat2", deps)
        text = tg.last_call("send_message")["text"]
        assert "lasciato" in text

    def test_leave_no_lobby(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/leave", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "Non sei" in text


class TestReadyCommand:
    def test_toggle_ready(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        handle_command("/ready", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "pronto" in text


class TestLobbyCommand:
    def test_shows_lobby(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        handle_command("/lobby", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "Lobby" in text


class TestStartGameCommand:
    def test_starts_game(self):
        deps, tg = _make_deps()
        # Create lobby with 2 players
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        user = deps.user_repo.get_user("u1")
        lobby = deps.lobby_repo.get_lobby(user["currentLobbyId"])
        code = lobby["code"]

        handle_command("/start", "", "u2", "chat2", deps)
        handle_command("/join", code, "u2", "chat2", deps)
        handle_command("/ready", "", "u1", "chat1", deps)
        handle_command("/ready", "", "u2", "chat2", deps)
        handle_command("/startgame", "", "u1", "chat1", deps)

        # Should have sent table + hands + draw keyboard
        sends = tg.get_calls("send_message")
        texts = [s["text"] for s in sends]
        has_table = any("Smazzata" in t for t in texts)
        has_hand = any("mano" in t.lower() for t in texts)
        has_draw = any(s.get("reply_markup") for s in sends)
        assert has_table
        assert has_hand
        assert has_draw

    def test_not_host_cannot_start(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/newlobby", "", "u1", "chat1", deps)
        user = deps.user_repo.get_user("u1")
        lobby = deps.lobby_repo.get_lobby(user["currentLobbyId"])

        handle_command("/start", "", "u2", "chat2", deps)
        handle_command("/join", lobby["code"], "u2", "chat2", deps)
        handle_command("/ready", "", "u1", "chat1", deps)
        handle_command("/ready", "", "u2", "chat2", deps)

        handle_command("/startgame", "", "u2", "chat2", deps)
        text = tg.last_call("send_message")["text"]
        assert "host" in text.lower() or "Errore" in text


class TestHandCommand:
    def test_shows_hand(self):
        deps, tg = _make_deps()
        _setup_game(deps)
        handle_command("/hand", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "mano" in text.lower()

    def test_no_game(self):
        deps, tg = _make_deps()
        handle_command("/start", "", "u1", "chat1", deps)
        handle_command("/hand", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "partita" in text.lower()


class TestTableCommand:
    def test_shows_table(self):
        deps, tg = _make_deps()
        _setup_game(deps)
        handle_command("/table", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "Smazzata" in text


class TestScoresCommand:
    def test_shows_scores(self):
        deps, tg = _make_deps()
        _setup_game(deps)
        handle_command("/scores", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "Punteggi" in text


class TestUnknownCommand:
    def test_unknown(self):
        deps, tg = _make_deps()
        handle_command("/foobar", "", "u1", "chat1", deps)
        text = tg.last_call("send_message")["text"]
        assert "sconosciuto" in text.lower()


def _setup_game(deps: Deps) -> str:
    """Set up a 2-player game and return game_id."""
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
