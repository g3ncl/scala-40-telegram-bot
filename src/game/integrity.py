"""State integrity checker for Scala 40 game state."""

from __future__ import annotations

from collections import Counter

from src.game.models import Card, GameState
from src.game.validator import validate_game
from src.utils.constants import (
    PHASE_DISCARD,
    PHASE_DRAW,
    PHASE_PLAY,
    STATUS_PLAYING,
    TOTAL_CARDS,
)


def validate_game_integrity(game: GameState) -> list[str]:
    """Validate all game state invariants. Returns list of errors (empty = OK).

    Checks:
    1. Total cards = 108 (hands + deck + discard + table)
    2. No illegal card duplicates
    3. All table games are valid sequences/combinations
    4. Current turn player exists and is active
    5. Turn phase is valid
    6. Unopened players have no table games
    7. Scores are non-negative
    """
    errors: list[str] = []

    if game.status != STATUS_PLAYING:
        # Limited checks for non-playing states
        return errors

    # 1. Collect all cards and check total
    all_cards: list[Card] = []
    for player in game.players:
        if not player.is_eliminated:
            all_cards.extend(player.hand)
    all_cards.extend(game.deck)
    all_cards.extend(game.discard_pile)
    for tg in game.table_games:
        all_cards.extend(tg.cards)

    if len(all_cards) != TOTAL_CARDS:
        errors.append(f"Totale carte = {len(all_cards)}, atteso {TOTAL_CARDS}")

    # 2. Check card duplicates
    # Each non-joker card (suit, rank, deck) should appear exactly once.
    # Jokers: 2 per deck (deck 0 and deck 1), so 4 total.
    # Jokers from the same deck are identical in our model.
    non_joker_counts = Counter(
        (c.suit, c.rank, c.deck) for c in all_cards if not c.is_joker
    )
    for key, count in non_joker_counts.items():
        if count > 1:
            errors.append(
                f"Carta duplicata illegale: "
                f"suit={key[0]} rank={key[1]} deck={key[2]} (x{count})"
            )

    joker_count = sum(1 for c in all_cards if c.is_joker)
    if joker_count != 4:
        errors.append(f"Jolly totali = {joker_count}, attesi 4")

    # 3. Validate table games
    for tg in game.table_games:
        result = validate_game(tg.cards)
        if not result.valid:
            errors.append(f"Gioco sul tavolo {tg.game_id} non valido: {result.error}")

    # 4. Current turn player
    active_ids = {p.user_id for p in game.get_active_players()}
    if game.current_turn_user_id not in active_ids:
        errors.append(f"Giocatore di turno {game.current_turn_user_id} non è attivo")

    # 5. Turn phase
    if game.turn_phase not in (PHASE_DRAW, PHASE_PLAY, PHASE_DISCARD):
        errors.append(f"Fase turno non valida: {game.turn_phase}")

    # 6. Unopened players should not have table games
    for tg in game.table_games:
        owner = game.get_player(tg.owner)
        if owner and not owner.has_opened and not owner.is_eliminated:
            errors.append(f"Giocatore {tg.owner} ha giochi sul tavolo ma non ha aperto")

    # 7. Non-negative scores
    for uid, score in game.scores.items():
        if score < 0:
            errors.append(f"Punteggio negativo per {uid}: {score}")

    return errors
