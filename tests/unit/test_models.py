"""Tests for game data models."""

from src.game.models import Card, GameState, PlayerState, TableGame
from src.utils.constants import JOKER_SUIT, JOKER_RANK


class TestCard:
    def test_is_joker(self):
        joker = Card(suit="j", rank=0, deck=0)
        assert joker.is_joker
        regular = Card(suit="h", rank=8, deck=0)
        assert not regular.is_joker

    def test_points_numeric(self):
        card = Card(suit="h", rank=8, deck=0)
        assert card.points() == 8

    def test_points_ace_high(self):
        ace = Card(suit="h", rank=1, deck=0)
        assert ace.points() == 11

    def test_points_ace_low(self):
        ace = Card(suit="h", rank=1, deck=0)
        assert ace.points(low_ace=True) == 1

    def test_points_face_cards(self):
        assert Card(suit="h", rank=11, deck=0).points() == 10  # Jack
        assert Card(suit="h", rank=12, deck=0).points() == 10  # Queen
        assert Card(suit="h", rank=13, deck=0).points() == 10  # King

    def test_points_joker(self):
        joker = Card(suit="j", rank=0, deck=0)
        assert joker.points() == 25

    def test_compact_numeric(self):
        card = Card(suit="h", rank=8, deck=0)
        assert card.compact() == "8h0"

    def test_compact_face(self):
        assert Card(suit="s", rank=13, deck=0).compact() == "Ks0"
        assert Card(suit="d", rank=12, deck=1).compact() == "Qd1"
        assert Card(suit="c", rank=11, deck=0).compact() == "Jc0"

    def test_compact_ace(self):
        assert Card(suit="d", rank=1, deck=0).compact() == "Ad0"

    def test_compact_ten(self):
        assert Card(suit="c", rank=10, deck=0).compact() == "10c0"

    def test_compact_joker(self):
        assert Card(suit="j", rank=0, deck=0).compact() == "J0"
        assert Card(suit="j", rank=0, deck=1).compact() == "J1"

    def test_from_compact_numeric(self):
        card = Card.from_compact("8h0")
        assert card == Card(suit="h", rank=8, deck=0)

    def test_from_compact_default_deck(self):
        card = Card.from_compact("8h")
        assert card == Card(suit="h", rank=8, deck=0)

    def test_from_compact_face(self):
        assert Card.from_compact("Ks1") == Card(suit="s", rank=13, deck=1)

    def test_from_compact_ten(self):
        assert Card.from_compact("10c0") == Card(suit="c", rank=10, deck=0)

    def test_from_compact_joker(self):
        assert Card.from_compact("J0") == Card(suit="j", rank=0, deck=0)
        assert Card.from_compact("J1") == Card(suit="j", rank=0, deck=1)

    def test_compact_roundtrip(self):
        cards = [
            Card(suit="h", rank=1, deck=0),
            Card(suit="s", rank=13, deck=1),
            Card(suit="c", rank=10, deck=0),
            Card(suit="j", rank=0, deck=0),
            Card(suit="d", rank=5, deck=1),
        ]
        for card in cards:
            assert Card.from_compact(card.compact()) == card

    def test_display_numeric(self):
        card = Card(suit="h", rank=8, deck=0)
        assert card.display() == "8♥"

    def test_display_joker(self):
        card = Card(suit="j", rank=0, deck=0)
        assert card.display() == "🃏"

    def test_display_face(self):
        assert Card(suit="s", rank=13, deck=0).display() == "K♠"

    def test_to_dict_from_dict_roundtrip(self):
        card = Card(suit="h", rank=8, deck=1)
        assert Card.from_dict(card.to_dict()) == card

    def test_to_dict_from_dict_joker(self):
        card = Card(suit="j", rank=0, deck=0)
        assert Card.from_dict(card.to_dict()) == card

    def test_frozen_hashable(self):
        card1 = Card(suit="h", rank=8, deck=0)
        card2 = Card(suit="h", rank=8, deck=0)
        assert card1 == card2
        assert hash(card1) == hash(card2)
        assert len({card1, card2}) == 1

    def test_different_deck_not_equal(self):
        card1 = Card(suit="h", rank=8, deck=0)
        card2 = Card(suit="h", rank=8, deck=1)
        assert card1 != card2


class TestPlayerState:
    def test_to_dict_from_dict_roundtrip(self):
        player = PlayerState(
            user_id="p1",
            hand=[Card(suit="h", rank=8, deck=0), Card(suit="j", rank=0, deck=1)],
            has_opened=True,
            is_eliminated=False,
            score=42,
        )
        restored = PlayerState.from_dict(player.to_dict())
        assert restored.user_id == player.user_id
        assert restored.hand == player.hand
        assert restored.has_opened == player.has_opened
        assert restored.score == player.score


class TestTableGame:
    def test_to_dict_from_dict_roundtrip(self):
        tg = TableGame(
            game_id="abc123",
            owner="p1",
            cards=[Card(suit="h", rank=3, deck=0), Card(suit="h", rank=4, deck=0), Card(suit="h", rank=5, deck=0)],
            game_type="sequence",
        )
        restored = TableGame.from_dict(tg.to_dict())
        assert restored.game_id == tg.game_id
        assert restored.cards == tg.cards
        assert restored.game_type == tg.game_type


class TestGameState:
    def _make_game(self) -> GameState:
        return GameState(
            game_id="game-1",
            lobby_id="lobby-1",
            players=[
                PlayerState(user_id="p1", hand=[Card(suit="h", rank=8, deck=0)]),
                PlayerState(user_id="p2", hand=[Card(suit="s", rank=13, deck=1)]),
            ],
            deck=[Card(suit="d", rank=5, deck=0)],
            discard_pile=[Card(suit="c", rank=3, deck=0)],
            table_games=[],
            current_turn_user_id="p1",
            turn_phase="draw",
            round_number=1,
            dealer_user_id="p2",
            first_round_complete=False,
            smazzata_number=1,
            scores={"p1": 0, "p2": 10},
            status="playing",
            settings={"elimination_score": 101},
            updated_at="2025-01-01T00:00:00Z",
            version=1,
        )

    def test_get_player(self):
        game = self._make_game()
        assert game.get_player("p1") is not None
        assert game.get_player("p1").user_id == "p1"
        assert game.get_player("nonexistent") is None

    def test_get_active_players(self):
        game = self._make_game()
        assert len(game.get_active_players()) == 2
        game.players[1].is_eliminated = True
        assert len(game.get_active_players()) == 1

    def test_to_dict_from_dict_roundtrip(self):
        game = self._make_game()
        restored = GameState.from_dict(game.to_dict())
        assert restored.game_id == game.game_id
        assert restored.players[0].user_id == "p1"
        assert restored.deck == game.deck
        assert restored.scores == game.scores
        assert restored.version == game.version

    def test_to_dict_from_dict_with_drawn_from_discard(self):
        game = self._make_game()
        game.drawn_from_discard = Card(suit="h", rank=5, deck=0)
        restored = GameState.from_dict(game.to_dict())
        assert restored.drawn_from_discard == Card(suit="h", rank=5, deck=0)
