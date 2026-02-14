"""Tests for game validator."""

from src.game.models import Card, TableGame
from src.game.validator import (
    can_attach,
    can_substitute_joker,
    card_points,
    is_valid_combination,
    is_valid_discard,
    is_valid_opening,
    is_valid_sequence,
    validate_game,
)
from src.utils.constants import GAME_TYPE_COMBINATION, GAME_TYPE_SEQUENCE


def c(code: str) -> Card:
    """Shorthand to create a card from compact notation."""
    return Card.from_compact(code)


JOKER = Card(suit="j", rank=0, deck=0)
JOKER2 = Card(suit="j", rank=0, deck=1)


class TestCardPoints:
    def test_numeric(self):
        assert card_points(c("5h")) == 5

    def test_face(self):
        assert card_points(c("Jh")) == 10
        assert card_points(c("Qd")) == 10
        assert card_points(c("Ks")) == 10

    def test_ace_high(self):
        assert card_points(c("Ah")) == 11

    def test_ace_low(self):
        assert card_points(c("Ah"), low_ace=True) == 1

    def test_joker(self):
        assert card_points(JOKER) == 25


class TestIsValidSequence:
    def test_basic_sequence(self):
        result = is_valid_sequence([c("3h"), c("4h"), c("5h")])
        assert result.valid
        assert result.points == 12  # 3+4+5

    def test_long_sequence(self):
        result = is_valid_sequence([c(f"{r}h") for r in ["3", "4", "5", "6", "7", "8"]])
        assert result.valid
        assert result.points == 3 + 4 + 5 + 6 + 7 + 8

    def test_with_joker_in_middle(self):
        result = is_valid_sequence([c("3h"), JOKER, c("5h")])
        assert result.valid
        assert result.points == 3 + 4 + 5  # joker = 4h

    def test_ace_low(self):
        result = is_valid_sequence([c("Ah"), c("2h"), c("3h")])
        assert result.valid
        assert result.points == 1 + 2 + 3  # Ace = 1

    def test_ace_high(self):
        result = is_valid_sequence([c("Qh"), c("Kh"), c("Ah")])
        assert result.valid
        assert result.points == 10 + 10 + 11  # Ace = 11

    def test_no_wrap_kah2(self):
        result = is_valid_sequence([c("Kh"), c("Ah"), c("2h")])
        assert not result.valid

    def test_different_suits_invalid(self):
        result = is_valid_sequence([c("3h"), c("4d"), c("5h")])
        assert not result.valid

    def test_too_short(self):
        result = is_valid_sequence([c("3h"), c("4h")])
        assert not result.valid

    def test_two_jokers_invalid(self):
        result = is_valid_sequence([c("3h"), JOKER, JOKER2])
        assert not result.valid

    def test_gap_too_large_no_joker(self):
        result = is_valid_sequence([c("3h"), c("6h"), c("7h")])
        assert not result.valid

    def test_joker_at_start(self):
        # Joker before 2h -> Joker=Ah (low)
        result = is_valid_sequence([JOKER, c("2h"), c("3h")])
        assert result.valid

    def test_joker_at_end(self):
        result = is_valid_sequence([c("Qh"), c("Kh"), JOKER])
        assert result.valid

    def test_duplicate_ranks_invalid(self):
        # Same rank in a sequence is invalid
        result = is_valid_sequence([c("3h"), c("3h1"), c("4h")])
        assert not result.valid

    def test_face_card_sequence(self):
        result = is_valid_sequence([c("Jh"), c("Qh"), c("Kh")])
        assert result.valid
        assert result.points == 30  # 10+10+10


class TestIsValidCombination:
    def test_tris(self):
        result = is_valid_combination([c("8h"), c("8d"), c("8c")])
        assert result.valid
        assert result.points == 24  # 8*3

    def test_poker(self):
        result = is_valid_combination([c("8h"), c("8d"), c("8c"), c("8s")])
        assert result.valid
        assert result.points == 32  # 8*4

    def test_with_joker(self):
        result = is_valid_combination([c("8h"), c("8d"), JOKER])
        assert result.valid
        assert result.points == 24  # 8+8+8 (joker=8)

    def test_same_suit_invalid(self):
        # Two hearts (from different decks)
        result = is_valid_combination([c("8h"), c("8h1"), c("8d")])
        assert not result.valid

    def test_different_ranks_invalid(self):
        result = is_valid_combination([c("8h"), c("9d"), c("8c")])
        assert not result.valid

    def test_five_cards_invalid(self):
        result = is_valid_combination([c("8h"), c("8d"), c("8c"), c("8s"), JOKER])
        assert not result.valid

    def test_two_cards_invalid(self):
        result = is_valid_combination([c("8h"), c("8d")])
        assert not result.valid

    def test_two_jokers_invalid(self):
        result = is_valid_combination([JOKER, JOKER2, c("8h")])
        assert not result.valid

    def test_ace_tris(self):
        result = is_valid_combination([c("Ah"), c("Ad"), c("Ac")])
        assert result.valid
        assert result.points == 33  # 11*3

    def test_face_tris(self):
        result = is_valid_combination([c("Kh"), c("Kd"), c("Kc")])
        assert result.valid
        assert result.points == 30  # 10*3


class TestValidateGame:
    def test_sequence_detected(self):
        result = validate_game([c("3h"), c("4h"), c("5h")])
        assert result.valid

    def test_combination_detected(self):
        result = validate_game([c("8h"), c("8d"), c("8c")])
        assert result.valid

    def test_invalid(self):
        result = validate_game([c("3h"), c("8d"), c("Kc")])
        assert not result.valid


class TestIsValidOpening:
    def test_exactly_40_points(self):
        # Tris of Ks (10*3=30) + A,2,3 of hearts (1+2+3=6)... not enough
        # Tris of Ks (30) + tris of 5s (15) = 45 >= 40
        games = [
            [c("Kh"), c("Kd"), c("Kc")],  # 30
            [c("5h"), c("5d"), c("5c")],  # 15
        ]
        result = is_valid_opening(games)
        assert result.valid
        assert result.points == 45

    def test_over_40_points(self):
        games = [
            [c("Jh"), c("Qh"), c("Kh")],  # 30 (sequence)
            [c("Ah"), c("Ad"), c("Ac")],  # 33 (tris, Ace=11)
        ]
        result = is_valid_opening(games)
        assert result.valid
        assert result.points == 63

    def test_under_40_points(self):
        games = [
            [c("3h"), c("4h"), c("5h")],  # 12
            [c("2d"), c("2c"), c("2s")],  # 6
        ]
        result = is_valid_opening(games)
        assert not result.valid
        assert "insufficiente" in result.error.lower()

    def test_invalid_game_in_opening(self):
        games = [
            [c("3h"), c("8d"), c("Kc")],  # invalid
        ]
        result = is_valid_opening(games)
        assert not result.valid

    def test_opening_with_joker_value(self):
        # Sequence: Joker-Kh-Ah = J(=Qh=10)+K(10)+A(11) = 31
        # Plus tris of 5s = 15
        # Total = 46 >= 40? Wait, let me recount.
        # Joker, Kh, Ah -> sequence Qh,Kh,Ah -> 10+10+11=31
        # Sequence ranks: [12(Q via joker), 13, 14(A-high)]
        # points: 10+10+11=31. Plus tris of 5s=15 -> 46 >= 40 ✓
        games = [
            [JOKER, c("Kh"), c("Ah")],
            [c("5d"), c("5c"), c("5s")],
        ]
        result = is_valid_opening(games)
        assert result.valid
        assert result.points >= 40

    def test_empty_opening(self):
        result = is_valid_opening([])
        assert not result.valid


class TestCanAttach:
    def test_extend_sequence_end(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_attach(c("6h"), tg)
        assert result.valid

    def test_extend_sequence_start(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_attach(c("2h"), tg)
        assert result.valid

    def test_wrong_suit_sequence(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_attach(c("6d"), tg)
        assert not result.valid

    def test_wrong_rank_sequence(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_attach(c("8h"), tg)
        assert not result.valid

    def test_add_to_combination(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), c("8d"), c("8c")],
            game_type=GAME_TYPE_COMBINATION,
        )
        result = can_attach(c("8s"), tg)
        assert result.valid

    def test_combination_full(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), c("8d"), c("8c"), c("8s")],
            game_type=GAME_TYPE_COMBINATION,
        )
        result = can_attach(JOKER, tg)
        assert not result.valid

    def test_combination_same_suit_invalid(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), c("8d"), c("8c")],
            game_type=GAME_TYPE_COMBINATION,
        )
        result = can_attach(c("8h1"), tg)  # same suit (hearts) from deck 1
        assert not result.valid

    def test_ace_extends_sequence_at_end(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("Qh"), c("Kh")],  # Wait, this is only 2 cards
            game_type=GAME_TYPE_SEQUENCE,
        )
        # Let's use a valid 3-card sequence
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("Jh"), c("Qh"), c("Kh")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_attach(c("Ah"), tg)
        assert result.valid


class TestCanSubstituteJoker:
    def test_substitute_in_combination(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), JOKER, c("8c")],
            game_type=GAME_TYPE_COMBINATION,
        )
        # Joker represents an 8 of a missing suit (d or s)
        result = can_substitute_joker(c("8d"), tg)
        assert result.valid

    def test_substitute_wrong_rank(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), JOKER, c("8c")],
            game_type=GAME_TYPE_COMBINATION,
        )
        result = can_substitute_joker(c("9d"), tg)
        assert not result.valid

    def test_substitute_in_sequence(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), JOKER, c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_substitute_joker(c("4h"), tg)
        assert result.valid

    def test_substitute_wrong_card_in_sequence(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), JOKER, c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = can_substitute_joker(c("6h"), tg)
        assert not result.valid

    def test_no_joker_to_substitute(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), c("8d"), c("8c")],
            game_type=GAME_TYPE_COMBINATION,
        )
        result = can_substitute_joker(c("8s"), tg)
        assert not result.valid

    def test_cannot_substitute_joker_with_joker(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("8h"), JOKER, c("8c")],
            game_type=GAME_TYPE_COMBINATION,
        )
        result = can_substitute_joker(JOKER2, tg)
        assert not result.valid


class TestIsValidDiscard:
    def test_normal_discard(self):
        result = is_valid_discard(
            card=c("8h"),
            drawn_from_discard=None,
            table_games=[],
            player_has_opened=True,
            num_players=4,
            cards_in_hand_after=5,
        )
        assert result.valid

    def test_cannot_discard_picked_card(self):
        picked = c("8h")
        result = is_valid_discard(
            card=c("8h"),
            drawn_from_discard=picked,
            table_games=[],
            player_has_opened=True,
            num_players=4,
            cards_in_hand_after=5,
        )
        assert not result.valid

    def test_can_discard_different_card(self):
        result = is_valid_discard(
            card=c("9h"),
            drawn_from_discard=c("8h"),
            table_games=[],
            player_has_opened=True,
            num_players=4,
            cards_in_hand_after=5,
        )
        assert result.valid

    def test_cannot_discard_attachable_multiplayer(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = is_valid_discard(
            card=c("6h"),  # extends the sequence
            drawn_from_discard=None,
            table_games=[tg],
            player_has_opened=True,
            num_players=3,
            cards_in_hand_after=5,
        )
        assert not result.valid

    def test_can_discard_attachable_when_closing(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = is_valid_discard(
            card=c("6h"),
            drawn_from_discard=None,
            table_games=[tg],
            player_has_opened=True,
            num_players=3,
            cards_in_hand_after=0,  # closing
        )
        assert result.valid

    def test_attachable_allowed_in_2_player(self):
        tg = TableGame(
            game_id="t1",
            owner="p1",
            cards=[c("3h"), c("4h"), c("5h")],
            game_type=GAME_TYPE_SEQUENCE,
        )
        result = is_valid_discard(
            card=c("6h"),
            drawn_from_discard=None,
            table_games=[tg],
            player_has_opened=True,
            num_players=2,
            cards_in_hand_after=5,
        )
        assert result.valid
