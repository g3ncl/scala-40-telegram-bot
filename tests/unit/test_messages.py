"""Tests for bot message formatting and keyboard builders."""

from src.bot.messages import (
    _get_display_name,
    build_attach_target_keyboard,
    build_card_select_keyboard,
    build_discard_keyboard,
    build_draw_keyboard,
    build_play_keyboard,
    format_hand,
    format_lobby,
    format_scores,
    format_table,
    format_welcome,
)
from src.game.models import Card, GameState, PlayerState, TableGame
from src.utils.constants import (
    GAME_TYPE_SEQUENCE,
    PHASE_DRAW,
    STATUS_PLAYING,
)


def c(code: str) -> Card:
    return Card.from_compact(code)


def _make_game() -> GameState:
    return GameState(
        game_id="g1",
        lobby_id="l1",
        players=[
            PlayerState(user_id="p1", hand=[c("3h"), c("5d"), c("Ks")]),
            PlayerState(user_id="p2", hand=[c("8c"), c("9c")]),
        ],
        deck=[c("2h")] * 10,
        discard_pile=[c("Jh")],
        table_games=[],
        current_turn_user_id="p1",
        turn_phase=PHASE_DRAW,
        round_number=1,
        dealer_user_id="p2",
        first_round_complete=False,
        smazzata_number=1,
        scores={"p1": 0, "p2": 15},
        status=STATUS_PLAYING,
        settings={"elimination_score": 101},
        updated_at="",
    )


class TestGetDisplayName:
    def test_fallback_to_id_no_deps(self):
        assert _get_display_name("u1") == "u1"

    def test_fallback_to_id_no_user(self, deps_with_user):
        deps, _ = deps_with_user
        assert _get_display_name("u2", deps) == "u2"

    def test_username_priority(self, deps_with_user):
        deps, _ = deps_with_user
        assert _get_display_name("u1", deps) == "@user1"

    def test_fullname_priority(self, deps_with_user):
        deps, _ = deps_with_user
        deps.user_repo.save_user(
            {"userId": "u1", "first_name": "Mario", "last_name": "Rossi"}
        )
        assert _get_display_name("u1", deps) == "Mario Rossi"

    def test_firstname_only(self, deps_with_user):
        deps, _ = deps_with_user
        deps.user_repo.save_user({"userId": "u1", "first_name": "Mario"})
        assert _get_display_name("u1", deps) == "Mario"


class TestFormatWelcome:
    def test_contains_commands(self):
        text = format_welcome()
        assert "/newlobby" in text
        assert "/join" in text
        assert "/hand" in text


class TestFormatHand:
    def test_shows_cards(self):
        player = PlayerState(user_id="p1", hand=[c("Ks"), c("3h"), c("5d")])
        text = format_hand(player)
        assert "3 carte" in text
        assert "K" in text

    def test_empty_hand(self):
        player = PlayerState(user_id="p1", hand=[])
        text = format_hand(player)
        assert "vuota" in text


class TestFormatTable:
    def test_shows_turn_and_discard(self):
        game = _make_game()
        text = format_table(game)
        assert "p1" in text
        assert "Pesca" in text
        assert "Smazzata #1" in text

    def test_shows_hand_counts(self):
        game = _make_game()
        text = format_table(game)
        assert "3 carte" in text
        assert "2 carte" in text

    def test_shows_scores(self):
        game = _make_game()
        text = format_table(game)
        assert "p1: 0" in text
        assert "p2: 15" in text


class TestFormatLobby:
    def test_shows_players(self):
        lobby = {
            "code": "ABC123",
            "players": [
                {"userId": "host", "ready": True},
                {"userId": "guest", "ready": False},
            ],
        }
        text = format_lobby(lobby)
        assert "ABC123" in text
        assert "host" in text
        assert "pronto" in text
        assert "non pronto" in text


class TestFormatScores:
    def test_sorted_by_score(self):
        game = _make_game()
        text = format_scores(game)
        # p1: 0 should come before p2: 15
        assert text.index("p1") < text.index("p2")


class TestBuildDrawKeyboard:
    def test_deck_only_when_not_opened(self):
        kb = build_draw_keyboard(has_opened=False)
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 1
        assert buttons[0]["callback_data"] == "draw:deck"

    def test_both_when_opened(self):
        kb = build_draw_keyboard(has_opened=True)
        buttons = kb["inline_keyboard"][0]
        assert len(buttons) == 2
        assert buttons[1]["callback_data"] == "draw:discard"


class TestBuildPlayKeyboard:
    def test_opened_has_play_attach_discard(self):
        kb = build_play_keyboard(has_opened=True)
        all_cb = [btn["callback_data"] for row in kb["inline_keyboard"] for btn in row]
        assert "menu:play" in all_cb
        assert "menu:attach" in all_cb
        assert "menu:discard" in all_cb

    def test_not_opened_has_open_discard(self):
        kb = build_play_keyboard(has_opened=False)
        all_cb = [btn["callback_data"] for row in kb["inline_keyboard"] for btn in row]
        assert "menu:open" in all_cb
        assert "menu:discard" in all_cb


class TestBuildCardSelectKeyboard:
    def test_buttons_match_cards(self):
        cards = [c("3h"), c("5d"), c("Ks")]
        mask = "000"
        kb = build_card_select_keyboard(cards, mask, "play")
        # Cards row + confirm row
        card_buttons = kb["inline_keyboard"][0]
        assert len(card_buttons) == 3

    def test_selected_card_has_marker(self):
        cards = [c("3h"), c("5d")]
        mask = "10"
        kb = build_card_select_keyboard(cards, mask, "play")
        card_buttons = kb["inline_keyboard"][0]
        # First card (3h, sorted) should have [x]
        assert "[x]" in card_buttons[0]["text"]
        assert "[x]" not in card_buttons[1]["text"]

    def test_callback_data_under_64_bytes(self):
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        cards = [c(f"{r}h") for r in ranks]  # 13 cards
        mask = "0" * 13
        kb = build_card_select_keyboard(cards, mask, "play")
        for row in kb["inline_keyboard"]:
            for btn in row:
                assert len(btn["callback_data"]) <= 64

    def test_confirm_button_present(self):
        cards = [c("3h")]
        mask = "0"
        kb = build_card_select_keyboard(cards, mask, "play")
        last_row = kb["inline_keyboard"][-1]
        labels = [btn["text"] for btn in last_row]
        assert "Conferma" in labels

    def test_open_has_group_button(self):
        cards = [c("3h")]
        mask = "0"
        kb = build_card_select_keyboard(cards, mask, "open")
        last_row = kb["inline_keyboard"][-1]
        labels = [btn["text"] for btn in last_row]
        assert "Gruppo +" in labels


class TestBuildDiscardKeyboard:
    def test_one_button_per_card(self):
        cards = [c("3h"), c("5d")]
        kb = build_discard_keyboard(cards)
        # Card row + cancel row
        card_row = kb["inline_keyboard"][0]
        assert len(card_row) == 2
        assert card_row[0]["callback_data"].startswith("disc:")


class TestBuildAttachTargetKeyboard:
    def test_shows_valid_targets(self):
        tg = TableGame(
            game_id="tg-abcdef-123",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        kb = build_attach_target_keyboard(c("6h"), [tg])
        # One target row + cancel row
        assert len(kb["inline_keyboard"]) == 2
        assert "att_tg:6h0:tg-abc" in kb["inline_keyboard"][0][0]["callback_data"]

    def test_filters_invalid_targets(self):
        tg = TableGame(
            game_id="tg-abcdef-123",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        kb = build_attach_target_keyboard(c("9d"), [tg])
        # Only cancel row (9d can't attach to 3-4-5 of hearts)
        assert len(kb["inline_keyboard"]) == 1
