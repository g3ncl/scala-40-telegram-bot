"""Tests for state integrity checker."""

from src.db.memory import InMemoryGameRepository
from src.game.engine import GameEngine
from src.game.integrity import validate_game_integrity
from src.game.models import Card, TableGame
from src.utils.constants import GAME_TYPE_SEQUENCE
from src.utils.crypto import create_rng


def c(code: str) -> Card:
    return Card.from_compact(code)


def _make_started_game():
    repo = InMemoryGameRepository()
    rng = create_rng(42)
    eng = GameEngine(repo, rng)
    game = eng.create_game(["p1", "p2"])
    result = eng.start_round(game.game_id)
    return result.game


class TestValidateGameIntegrity:
    def test_valid_game_passes(self):
        game = _make_started_game()
        errors = validate_game_integrity(game)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_missing_card_detected(self):
        game = _make_started_game()
        # Remove a card from the deck
        game.deck.pop()
        errors = validate_game_integrity(game)
        assert any("Totale carte" in e for e in errors)

    def test_extra_card_detected(self):
        game = _make_started_game()
        # Add a duplicate card
        game.deck.append(c("8h"))
        errors = validate_game_integrity(game)
        assert len(errors) > 0

    def test_invalid_table_game_detected(self):
        game = _make_started_game()
        # Add an invalid table game
        game.table_games.append(
            TableGame(
                game_id="bad",
                owner="p1",
                cards=[c("3h"), c("8d"), c("Kc")],  # invalid
                game_type=GAME_TYPE_SEQUENCE,
            )
        )
        # Also need to add these cards somewhere to not fail total count
        # Actually, just check that the invalid game is detected
        errors = validate_game_integrity(game)
        assert any("non valido" in e for e in errors)

    def test_invalid_turn_phase_detected(self):
        game = _make_started_game()
        game.turn_phase = "invalid_phase"
        errors = validate_game_integrity(game)
        assert any("Fase turno" in e for e in errors)

    def test_invalid_current_player_detected(self):
        game = _make_started_game()
        game.current_turn_user_id = "nonexistent"
        errors = validate_game_integrity(game)
        assert any("non è attivo" in e for e in errors)

    def test_after_draw_still_valid(self):
        """Integrity should hold after a draw action."""
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)
        game = eng.create_game(["p1", "p2"])
        eng.start_round(game.game_id)
        game = eng.get_game(game.game_id)

        uid = game.current_turn_user_id
        eng.process_draw(game.game_id, uid, "deck")
        game = eng.get_game(game.game_id)
        errors = validate_game_integrity(game)
        assert errors == [], f"Unexpected errors after draw: {errors}"

    def test_after_discard_still_valid(self):
        """Integrity should hold after a full draw+discard cycle."""
        repo = InMemoryGameRepository()
        rng = create_rng(42)
        eng = GameEngine(repo, rng)
        game = eng.create_game(["p1", "p2"])
        eng.start_round(game.game_id)
        game = eng.get_game(game.game_id)

        uid = game.current_turn_user_id
        eng.process_draw(game.game_id, uid, "deck")
        game = eng.get_game(game.game_id)
        player = game.get_player(uid)
        eng.process_discard(game.game_id, uid, player.hand[-1])
        game = eng.get_game(game.game_id)
        errors = validate_game_integrity(game)
        assert errors == [], f"Unexpected errors after discard: {errors}"
