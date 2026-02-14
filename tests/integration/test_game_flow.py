"""Integration tests for complete game flows."""

from src.db.memory import InMemoryGameRepository
from src.game.engine import GameEngine
from src.game.integrity import validate_game_integrity
from src.game.models import Card
from src.game.validator import can_attach, validate_game
from src.utils.constants import (
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


def assert_integrity(game):
    errors = validate_game_integrity(game)
    assert not errors, f"Integrity violations: {errors}"


class TestFullRound:
    def test_two_player_draw_discard_cycle(self):
        """Two players take turns drawing and discarding without opening."""
        repo = InMemoryGameRepository()
        eng = GameEngine(repo, create_rng(42))

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        assert result.success
        game = result.game
        assert_integrity(game)

        # Play 4 turns (2 per player)
        for _ in range(4):
            uid = game.current_turn_user_id
            assert game.turn_phase == PHASE_DRAW

            # Draw
            result = eng.process_draw(game.game_id, uid, "deck")
            assert result.success
            game = result.game

            # Discard (last card in hand)
            player = game.get_player(uid)
            result = eng.process_discard(game.game_id, uid, player.hand[-1])
            assert result.success
            game = result.game
            assert_integrity(game)

        # First round should be complete after 2 full cycles
        assert game.first_round_complete

    def test_player_opens_and_plays(self):
        """Player opens with >= 40 points and plays additional games."""
        repo = InMemoryGameRepository()
        eng = GameEngine(repo, create_rng(42))

        game = eng.create_game(["p1", "p2"])
        result = eng.start_round(game.game_id)
        game = result.game

        uid = game.current_turn_user_id
        player = game.get_player(uid)

        # Use deck-1 cards for the forced hand to avoid conflicts with
        # the dealt deck-0 cards already distributed to hands/deck/discard.
        forced_hand = [
            c("Kh1"), c("Kd1"), c("Kc1"),     # tris K = 30
            c("5h1"), c("5d1"), c("5c1"),      # tris 5 = 15 -> total 45
            c("3h1"), c("4h1"), c("5s1"),
            c("8s1"), c("9s1"), c("Js1"), c("Qs1"),
        ]

        # Collect all cards NOT in current player's hand into a mutable pool,
        # then pick out the forced cards from the pool, put original hand back.
        original_hand = list(player.hand)

        # Build a flat list of all non-current-player cards with their locations
        all_pools = [
            ("deck", game.deck),
            ("discard", game.discard_pile),
        ] + [
            (f"hand_{p.user_id}", p.hand)
            for p in game.players if p.user_id != uid
        ]

        for card in forced_hand:
            # Skip if already in the current player's hand
            if card in player.hand:
                player.hand.remove(card)
                original_hand.remove(card)
                continue
            # Remove from other pools
            for _, pool in all_pools:
                try:
                    pool.remove(card)
                    break
                except ValueError:
                    continue

        # Set the forced hand and put remaining original cards back in the deck
        player.hand = forced_hand
        game.deck.extend(original_hand)
        repo.save_game(game)

        # Draw
        result = eng.process_draw(game.game_id, uid, "deck")
        assert result.success
        game = result.game

        # Open
        result = eng.process_open(
            game.game_id, uid,
            [[c("Kh1"), c("Kd1"), c("Kc1")], [c("5h1"), c("5d1"), c("5c1")]]
        )
        assert result.success
        game = result.game
        assert game.get_player(uid).has_opened
        assert len(game.table_games) == 2

        # Discard
        player = game.get_player(uid)
        result = eng.process_discard(game.game_id, uid, player.hand[-1])
        assert result.success
        game = result.game
        assert_integrity(game)


class TestSimulatedGame:
    def test_simulated_game_completes(self):
        """Run the simulator logic for a single game and verify it completes."""
        from cli.simulate import simulate_game

        rng = create_rng(42)
        result = simulate_game(2, rng, verbose=False)
        # Game should run and either finish with a winner or hit the turn cap
        assert result.get("turns", 0) > 0
        assert result.get("error") is None
        if result["winner"] is not None:
            assert result["smazzate"] > 0

    def test_four_player_game_completes(self):
        """Four-player simulated game."""
        from cli.simulate import simulate_game

        rng = create_rng(123)
        result = simulate_game(4, rng, verbose=False)
        assert result.get("turns", 0) > 0
        if result.get("error") is None:
            assert result["winner"] is not None
