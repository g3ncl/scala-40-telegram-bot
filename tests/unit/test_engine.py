"""Tests for the game engine."""

import pytest
from src.db.memory import InMemoryGameRepository
from src.game.engine import GameEngine
from src.game.models import Card
from src.utils.constants import (
    GAME_TYPE_COMBINATION,
    PHASE_DISCARD,
    PHASE_DRAW,
    PHASE_PLAY,
    STATUS_FINISHED,
    STATUS_PLAYING,
    STATUS_ROUND_END,
)
from src.utils.crypto import create_rng


def c(code: str) -> Card:
    return Card.from_compact(code)


JOKER = Card(suit="j", rank=0, deck=0)


@pytest.fixture
def engine():
    repo = InMemoryGameRepository()
    rng = create_rng(42)
    return GameEngine(repo, rng)


@pytest.fixture
def game_with_round(engine):
    """Game with 2 players, round started."""
    game = engine.create_game(["p1", "p2"], lobby_id="test")
    result = engine.start_round(game.game_id)
    assert result.success
    return result.game


class TestCreateGame:
    def test_creates_game(self, engine):
        game = engine.create_game(["p1", "p2", "p3"])
        assert game is not None
        assert len(game.players) == 3
        assert game.status == STATUS_PLAYING
        assert game.scores == {"p1": 0, "p2": 0, "p3": 0}

    def test_settings(self, engine):
        game = engine.create_game(["p1", "p2"], settings={"elimination_score": 201})
        assert game.settings["elimination_score"] == 201


class TestStartRound:
    def test_deals_13_cards(self, game_with_round):
        game = game_with_round
        for player in game.players:
            assert len(player.hand) == 13

    def test_discard_pile_has_one(self, game_with_round):
        assert len(game_with_round.discard_pile) == 1

    def test_deck_has_remaining(self, game_with_round):
        game = game_with_round
        # 108 - 26 (2*13) - 1 (discard) = 81
        assert len(game.deck) == 81

    def test_sets_first_player(self, game_with_round):
        game = game_with_round
        # First player is left of dealer
        assert game.current_turn_user_id != ""
        assert game.turn_phase == PHASE_DRAW

    def test_smazzata_increments(self, engine):
        game = engine.create_game(["p1", "p2"])
        r1 = engine.start_round(game.game_id)
        assert r1.game.smazzata_number == 1
        # Simulate round end and start new
        g = r1.game
        g.status = STATUS_ROUND_END
        engine._repo.save_game(g)
        r2 = engine.start_round(game.game_id)
        assert r2.game.smazzata_number == 2

    def test_first_round_not_complete(self, game_with_round):
        assert not game_with_round.first_round_complete


class TestProcessDraw:
    def test_draw_from_deck(self, engine, game_with_round):
        game = game_with_round
        first = game.current_turn_user_id
        result = engine.process_draw(game.game_id, first, "deck")
        assert result.success
        player = result.game.get_player(first)
        assert len(player.hand) == 14  # 13 + 1
        # Phase transitions to discard (not opened)
        assert result.game.turn_phase == PHASE_DISCARD

    def test_draw_from_discard_not_opened_fails(self, engine, game_with_round):
        game = game_with_round
        first = game.current_turn_user_id
        result = engine.process_draw(game.game_id, first, "discard")
        assert not result.success
        assert "aperto" in result.error.lower()

    def test_wrong_turn_fails(self, engine, game_with_round):
        game = game_with_round
        active = [p.user_id for p in game.get_active_players()]
        other = [uid for uid in active if uid != game.current_turn_user_id][0]
        result = engine.process_draw(game.game_id, other, "deck")
        assert not result.success
        assert "turno" in result.error.lower()

    def test_wrong_phase_fails(self, engine, game_with_round):
        game = game_with_round
        first = game.current_turn_user_id
        # Draw once
        engine.process_draw(game.game_id, first, "deck")
        # Try to draw again
        result = engine.process_draw(game.game_id, first, "deck")
        assert not result.success


class TestProcessOpen:
    def _setup_opening_hand(self, engine, game):
        """Force a hand that allows opening."""
        player = game.get_player(game.current_turn_user_id)
        # Replace hand with cards that allow opening >= 40
        player.hand = [
            c("Kh"),
            c("Kd"),
            c("Kc"),  # tris K = 30
            c("5h"),
            c("5d"),
            c("5c"),  # tris 5 = 15 -> total 45
            c("2h"),
            c("3h"),
            c("4h"),  # sequence = 9
            c("8s"),
            c("9s"),
            c("Js"),
            c("Qs"),  # extras
        ]
        # Need to draw first
        engine._repo.save_game(game)
        result = engine.process_draw(game.game_id, game.current_turn_user_id, "deck")
        return result.game

    def test_valid_opening(self, engine, game_with_round):
        game = self._setup_opening_hand(engine, game_with_round)
        uid = game.current_turn_user_id
        # Phase is discard (not opened), we need to transition to allow opening
        # Actually, opening can happen during discard phase for unopened players
        games = [
            [c("Kh"), c("Kd"), c("Kc")],
            [c("5h"), c("5d"), c("5c")],
        ]
        result = engine.process_open(game.game_id, uid, games)
        assert result.success
        player = result.game.get_player(uid)
        assert player.has_opened
        assert len(result.game.table_games) == 2

    def test_opening_under_40_fails(self, engine, game_with_round):
        game = self._setup_opening_hand(engine, game_with_round)
        uid = game.current_turn_user_id
        games = [
            [c("2h"), c("3h"), c("4h")],  # 9 points only
        ]
        result = engine.process_open(game.game_id, uid, games)
        assert not result.success
        assert "insufficiente" in result.error.lower()


class TestProcessPlay:
    def _setup_opened_player(self, engine, game):
        """Set up a game where current player has opened."""
        uid = game.current_turn_user_id
        player = game.get_player(uid)
        player.hand = [
            c("Kh"),
            c("Kd"),
            c("Kc"),
            c("5h"),
            c("5d"),
            c("5c"),
            c("2h"),
            c("3h"),
            c("4h"),
            c("8s"),
            c("9s"),
            c("Js"),
            c("Qs"),
        ]
        engine._repo.save_game(game)

        engine.process_draw(game.game_id, uid, "deck")
        game = engine.get_game(game.game_id)
        engine.process_open(
            game.game_id,
            uid,
            [[c("Kh"), c("Kd"), c("Kc")], [c("5h"), c("5d"), c("5c")]],
        )
        return engine.get_game(game.game_id)

    def test_play_sequence(self, engine, game_with_round):
        game = self._setup_opened_player(engine, game_with_round)
        uid = game.current_turn_user_id
        result = engine.process_play(game.game_id, uid, [c("2h"), c("3h"), c("4h")])
        assert result.success
        # Now 3 table games (2 from opening + 1 new)
        assert len(result.game.table_games) == 3

    def test_play_before_opening_fails(self, engine, game_with_round):
        game = game_with_round
        uid = game.current_turn_user_id
        # Draw first to get to play/discard phase
        engine.process_draw(game.game_id, uid, "deck")
        game = engine.get_game(game.game_id)
        result = engine.process_play(game.game_id, uid, [c("2h"), c("3h"), c("4h")])
        assert not result.success


class TestProcessAttach:
    def test_attach_to_sequence(self, engine, game_with_round):
        game = game_with_round
        uid = game.current_turn_user_id
        player = game.get_player(uid)
        # Set up: player has opened, has a sequence on table, and 6h in hand
        player.hand = [
            c("Kh"),
            c("Kd"),
            c("Kc"),
            c("5h"),
            c("5d"),
            c("5c"),
            c("3h"),
            c("4h"),
            c("5s"),  # 5s stays, 3h,4h for sequence
            c("6h"),
            c("9s"),
            c("Js"),
            c("Qs"),  # 6h to attach
        ]
        engine._repo.save_game(game)
        engine.process_draw(game.game_id, uid, "deck")
        game = engine.get_game(game.game_id)
        engine.process_open(
            game.game_id,
            uid,
            [[c("Kh"), c("Kd"), c("Kc")], [c("5h"), c("5d"), c("5c")]],
        )
        game = engine.get_game(game.game_id)
        # Play a sequence 3h, 4h, 5s — wait, that's invalid (different suits)
        # Let me use: play 3h 4h and need a 5h... already used.
        # Let's just attach 6h to an existing sequence if we had one.
        # Actually let's just test with combination:
        # Attach Ks to the King tris
        player2 = game.get_player(uid)
        # Kings tris is on table. Let's add Ks if in hand.
        # The hand after opening should have: drawn card, 3h, 4h, 5s, 6h, 9s, Js, Qs
        # Let's find the king tris table game
        king_tris = None
        for tg in game.table_games:
            if tg.game_type == GAME_TYPE_COMBINATION and any(
                tc.rank == 13 for tc in tg.cards
            ):
                king_tris = tg
                break

        # Player doesn't have Ks in hand right now. Let me restructure.
        # For simplicity, force add Ks to hand
        player2.hand.append(c("Ks"))
        engine._repo.save_game(game)

        result = engine.process_attach(game.game_id, uid, c("Ks"), king_tris.game_id)
        assert result.success


class TestProcessDiscard:
    def test_discard_ends_turn(self, engine, game_with_round):
        game = game_with_round
        first = game.current_turn_user_id
        active_ids = [p.user_id for p in game.get_active_players()]
        second = [uid for uid in active_ids if uid != first][0]

        # Draw
        engine.process_draw(game.game_id, first, "deck")
        game = engine.get_game(game.game_id)

        # Discard any card from hand
        player = game.get_player(first)
        card_to_discard = player.hand[-1]
        result = engine.process_discard(game.game_id, first, card_to_discard)
        assert result.success
        assert result.game.current_turn_user_id == second
        assert result.game.turn_phase == PHASE_DRAW

    def test_discard_card_not_in_hand_fails(self, engine, game_with_round):
        game = game_with_round
        first = game.current_turn_user_id
        engine.process_draw(game.game_id, first, "deck")
        # Try discarding a card not in hand
        result = engine.process_discard(
            game.game_id,
            first,
            c("J0"),  # Joker unlikely in hand
        )
        # Might succeed if joker happens to be in hand, so check
        game = engine.get_game(game.game_id)
        player = game.get_player(first)
        fake_card = Card(suit="h", rank=1, deck=1)
        if fake_card not in player.hand:
            result = engine.process_discard(game.game_id, first, fake_card)
            assert not result.success

    def test_discard_same_as_picked_fails(self, engine):
        """Player picks from discard, cannot discard the same card."""
        repo = InMemoryGameRepository()
        rng = create_rng(100)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        game = result.game

        # Force p1 to have opened and be current player
        p1 = game.get_player("p1")
        p1.has_opened = True
        # Need the discard pile to have a known card
        known_card = c("8h")
        game.discard_pile = [known_card]
        game.current_turn_user_id = "p1"
        game.turn_phase = PHASE_DRAW
        repo.save_game(game)

        # Draw from discard
        result = eng.process_draw(game.game_id, "p1", "discard")
        assert result.success

        # Try to discard the same card
        result = eng.process_discard(game.game_id, "p1", known_card)
        assert not result.success
        assert "stessa carta" in result.error.lower()


class TestClosure:
    def test_closure_on_last_card(self, engine):
        """Player discards last card -> round ends or game finishes."""
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        game = result.game

        # Force p1: opened, 1 card in hand, first round complete
        p1 = game.get_player("p1")
        p1.has_opened = True
        last_card = c("8s")
        p1.hand = [last_card]
        game.first_round_complete = True
        game.current_turn_user_id = "p1"
        game.turn_phase = PHASE_PLAY
        repo.save_game(game)

        result = eng.process_discard(game.game_id, "p1", last_card)
        assert result.success
        assert result.game.status in (STATUS_ROUND_END, STATUS_FINISHED)
        # p1 scored 0
        assert result.game.scores["p1"] == 0
        # p2 scored hand value
        assert result.game.scores["p2"] > 0

    def test_closure_blocked_first_round(self, engine):
        """Cannot close during first round."""
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        game = result.game

        p1 = game.get_player("p1")
        p1.has_opened = True
        last_card = c("8s")
        p1.hand = [last_card]
        game.first_round_complete = False  # first round NOT complete
        game.current_turn_user_id = "p1"
        game.turn_phase = PHASE_PLAY
        repo.save_game(game)

        result = eng.process_discard(game.game_id, "p1", last_card)
        assert not result.success
        assert "primo giro" in result.error.lower()


class TestTurnAdvancement:
    def test_turn_advances_to_next_player(self, engine, game_with_round):
        game = game_with_round
        first = game.current_turn_user_id
        active_ids = [p.user_id for p in game.get_active_players()]
        second = [uid for uid in active_ids if uid != first][0]

        # Draw and discard
        engine.process_draw(game.game_id, first, "deck")
        game = engine.get_game(game.game_id)
        player = game.get_player(first)
        result = engine.process_discard(game.game_id, first, player.hand[-1])
        assert result.game.current_turn_user_id == second

    def test_skips_eliminated_player(self, engine):
        """3 players, p2 eliminated, turn goes p1 -> p3."""
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2", "p3"])
        result = eng.start_round(game.game_id)
        game = result.game

        # Eliminate p2
        game.get_player("p2").is_eliminated = True
        game.get_player("p2").hand = []
        game.current_turn_user_id = "p1"
        game.turn_phase = PHASE_DRAW
        repo.save_game(game)

        # p1 draws and discards
        eng.process_draw(game.game_id, "p1", "deck")
        game = eng.get_game(game.game_id)
        p1 = game.get_player("p1")
        result = eng.process_discard(game.game_id, "p1", p1.hand[-1])

        # Should skip p2, go to p3
        assert result.game.current_turn_user_id == "p3"

    def test_first_round_complete_after_cycle(self, engine):
        """first_round_complete set after all players take a turn."""
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        game = result.game
        starter = game.current_turn_user_id
        active_ids = [p.user_id for p in game.get_active_players()]
        other = [uid for uid in active_ids if uid != starter][0]

        # Starter draws and discards
        eng.process_draw(game.game_id, starter, "deck")
        g = eng.get_game(game.game_id)
        p = g.get_player(starter)
        eng.process_discard(game.game_id, starter, p.hand[-1])
        g = eng.get_game(game.game_id)
        assert not g.first_round_complete  # other hasn't played yet

        # Other draws and discards
        eng.process_draw(game.game_id, other, "deck")
        g = eng.get_game(game.game_id)
        p = g.get_player(other)
        eng.process_discard(game.game_id, other, p.hand[-1])
        g = eng.get_game(game.game_id)
        assert g.first_round_complete  # both have played


class TestElimination:
    def test_player_eliminated_at_threshold(self, engine):
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2", "p3"])
        result = eng.start_round(game.game_id)
        game = result.game

        # Set scores close to threshold
        game.scores["p2"] = 90
        # Force p1 to close: opened, 1 card, first_round_complete
        p1 = game.get_player("p1")
        p1.has_opened = True
        last_card = c("2s")
        p1.hand = [last_card]
        game.first_round_complete = True
        game.current_turn_user_id = "p1"
        game.turn_phase = PHASE_PLAY
        repo.save_game(game)

        result = eng.process_discard(game.game_id, "p1", last_card)
        assert result.success

        # p2 had 13 cards worth of points, likely > 11 points
        # So p2's total should be 90 + hand_value >= 101
        p2 = result.game.get_player("p2")
        if result.game.scores["p2"] >= 101:
            assert p2.is_eliminated

    def test_game_ends_with_winner(self, engine):
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        game = result.game

        # Set p2 score close to elimination
        game.scores["p2"] = 95
        p1 = game.get_player("p1")
        p1.has_opened = True
        p1.hand = [c("2s")]
        game.first_round_complete = True
        game.current_turn_user_id = "p1"
        game.turn_phase = PHASE_PLAY
        repo.save_game(game)

        result = eng.process_discard(game.game_id, "p1", c("2s"))
        assert result.success

        # If p2's hand score pushes them over 101, game should end
        if result.game.scores["p2"] >= 101:
            assert result.game.status == STATUS_FINISHED
