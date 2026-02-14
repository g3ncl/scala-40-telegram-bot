"""Tests for scoring module."""

from src.game.models import Card, GameState, PlayerState
from src.game.scoring import (
    apply_round_scores,
    calculate_hand_score,
    check_eliminations,
    check_winner,
)


def c(code: str) -> Card:
    return Card.from_compact(code)


JOKER = Card(suit="j", rank=0, deck=0)


class TestCalculateHandScore:
    def test_numeric_cards(self):
        hand = [c("3h"), c("5d"), c("8c")]
        assert calculate_hand_score(hand) == 16

    def test_face_cards(self):
        hand = [c("Jh"), c("Qd"), c("Ks")]
        assert calculate_hand_score(hand) == 30

    def test_ace_counts_11(self):
        hand = [c("Ah")]
        assert calculate_hand_score(hand) == 11

    def test_joker_25(self):
        hand = [JOKER]
        assert calculate_hand_score(hand) == 25

    def test_empty_hand(self):
        assert calculate_hand_score([]) == 0

    def test_mixed_hand(self):
        hand = [c("Ah"), c("Kd"), JOKER, c("5c")]
        assert calculate_hand_score(hand) == 11 + 10 + 25 + 5


def _make_game(scores: dict[str, int] | None = None, threshold: int = 101) -> GameState:
    players = [
        PlayerState(user_id="p1", hand=[c("8h"), c("Kd")]),
        PlayerState(user_id="p2", hand=[c("Ah"), JOKER]),
        PlayerState(user_id="p3", hand=[]),
    ]
    return GameState(
        game_id="g1",
        lobby_id="l1",
        players=players,
        deck=[],
        discard_pile=[],
        table_games=[],
        current_turn_user_id="p1",
        turn_phase="draw",
        round_number=1,
        dealer_user_id="p3",
        first_round_complete=True,
        smazzata_number=1,
        scores=scores or {"p1": 0, "p2": 0, "p3": 0},
        status="playing",
        settings={"elimination_score": threshold},
        updated_at="2025-01-01T00:00:00Z",
    )


class TestApplyRoundScores:
    def test_closer_gets_zero(self):
        game = _make_game()
        apply_round_scores(game, closer_user_id="p3")
        assert game.scores["p3"] == 0

    def test_others_get_hand_score(self):
        game = _make_game()
        apply_round_scores(game, closer_user_id="p3")
        assert game.scores["p1"] == 18  # 8 + 10
        assert game.scores["p2"] == 36  # 11 + 25

    def test_scores_accumulate(self):
        game = _make_game(scores={"p1": 20, "p2": 30, "p3": 0})
        apply_round_scores(game, closer_user_id="p3")
        assert game.scores["p1"] == 38  # 20 + 18
        assert game.scores["p2"] == 66  # 30 + 36


class TestCheckEliminations:
    def test_no_elimination(self):
        game = _make_game(scores={"p1": 50, "p2": 80, "p3": 0})
        eliminated = check_eliminations(game)
        assert eliminated == []

    def test_one_eliminated(self):
        game = _make_game(scores={"p1": 101, "p2": 80, "p3": 0})
        eliminated = check_eliminations(game)
        assert eliminated == ["p1"]
        assert game.get_player("p1").is_eliminated

    def test_multiple_eliminated(self):
        game = _make_game(scores={"p1": 150, "p2": 200, "p3": 0})
        eliminated = check_eliminations(game)
        assert set(eliminated) == {"p1", "p2"}

    def test_custom_threshold(self):
        game = _make_game(scores={"p1": 150, "p2": 80, "p3": 0}, threshold=201)
        eliminated = check_eliminations(game)
        assert eliminated == []  # 150 < 201


class TestCheckWinner:
    def test_no_winner_yet(self):
        game = _make_game()
        assert check_winner(game) is None

    def test_winner_last_standing(self):
        game = _make_game()
        game.players[0].is_eliminated = True
        game.players[1].is_eliminated = True
        winner = check_winner(game)
        assert winner == "p3"
