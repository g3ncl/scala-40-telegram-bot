"""Validation logic for Scala 40 games.

Validates sequences (scale), combinations (tris/poker), openings,
attachments, joker substitutions, and discards.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.game.models import Card, TableGame
from src.utils.constants import (
    ACE,
    ACE_POINTS_HIGH,
    ACE_POINTS_LOW,
    FACE_POINTS,
    GAME_TYPE_COMBINATION,
    GAME_TYPE_SEQUENCE,
    JOKER_POINTS,
    KING,
    OPENING_THRESHOLD,
)


@dataclass
class ValidationResult:
    valid: bool
    points: int = 0
    error: str | None = None


def card_points(card: Card, low_ace: bool = False) -> int:
    """Point value of a single card."""
    if card.is_joker:
        return JOKER_POINTS
    if card.rank == ACE:
        return ACE_POINTS_LOW if low_ace else ACE_POINTS_HIGH
    if card.rank >= 11:
        return FACE_POINTS
    return card.rank


def _sequence_points(ranks_in_order: list[int], suit: str) -> int:
    """Calculate points for a sequence given the ranks in order (joker gaps filled)."""
    total = 0
    for rank in ranks_in_order:
        if rank == ACE:
            # Ace is low (1) if at position before 2, high (11) if after K
            total += ACE_POINTS_LOW
        elif rank == 14:
            # Ace-high (after K)
            total += ACE_POINTS_HIGH
        elif rank >= 11:
            total += FACE_POINTS
        else:
            total += rank
    return total


def is_valid_sequence(cards: list[Card]) -> ValidationResult:
    """Validate a sequence (scala).

    Rules:
    - Min 3 cards, same suit, consecutive ranks
    - Max 1 joker per sequence
    - Ace can be low (A-2-3) or high (Q-K-A), but NOT wrap (K-A-2)
    - Max 14 cards (A through K-A with joker)
    """
    if len(cards) < 3:
        return ValidationResult(False, error="La sequenza richiede almeno 3 carte")

    if len(cards) > 14:
        return ValidationResult(False, error="La sequenza non può avere più di 14 carte")

    jokers = [c for c in cards if c.is_joker]
    regulars = [c for c in cards if not c.is_joker]

    if len(jokers) > 1:
        return ValidationResult(False, error="Massimo 1 jolly per sequenza")

    if not regulars:
        return ValidationResult(False, error="La sequenza non può essere composta solo da jolly")

    # All regular cards must be same suit
    suit = regulars[0].suit
    if not all(c.suit == suit for c in regulars):
        return ValidationResult(False, error="Tutte le carte devono essere dello stesso seme")

    ranks = sorted(c.rank for c in regulars)

    # Check for duplicate ranks (not allowed in a sequence)
    if len(ranks) != len(set(ranks)):
        return ValidationResult(False, error="Ranghi duplicati nella sequenza")

    num_jokers = len(jokers)

    # Try Ace-low (A=1) and Ace-high (A=14)
    rank_sets_to_try = [ranks]
    if ACE in ranks:
        # Also try with Ace as 14
        ace_high_ranks = sorted([14 if r == ACE else r for r in ranks])
        rank_sets_to_try.append(ace_high_ranks)

    for try_ranks in rank_sets_to_try:
        # Check if cards form consecutive sequence with joker filling gaps
        gaps = 0
        valid = True
        for i in range(1, len(try_ranks)):
            diff = try_ranks[i] - try_ranks[i - 1]
            if diff == 1:
                continue
            elif diff == 2 and gaps < num_jokers:
                gaps += 1
            else:
                valid = False
                break

        if not valid:
            continue

        if gaps > num_jokers:
            continue

        # Build the full sequence of ranks (including joker positions)
        full_ranks = []
        jokers_placed = 0
        for i, r in enumerate(try_ranks):
            if i > 0:
                diff = r - try_ranks[i - 1]
                if diff == 2:
                    # Joker fills the gap
                    full_ranks.append(try_ranks[i - 1] + 1)
                    jokers_placed += 1
            full_ranks.append(r)

        # If joker not yet placed (e.g., at start or end), place at either end
        if num_jokers > 0 and jokers_placed == 0:
            # Try extending at start or end
            start_rank = try_ranks[0] - 1
            end_rank = try_ranks[-1] + 1
            if start_rank >= 1 or (start_rank == 0 and ACE not in try_ranks):
                # Prefer end extension if valid
                if end_rank <= 14:
                    full_ranks.append(end_rank)
                elif start_rank >= 1:
                    full_ranks.insert(0, start_rank)
                else:
                    continue  # Can't place joker
            elif end_rank <= 14:
                full_ranks.append(end_rank)
            else:
                continue  # Can't place joker

        points = _sequence_points(full_ranks, suit)
        return ValidationResult(True, points=points)

    return ValidationResult(False, error="Le carte non formano una sequenza valida")


def is_valid_combination(cards: list[Card]) -> ValidationResult:
    """Validate a combination (tris/poker).

    Rules:
    - 3 or 4 cards, same rank, different suits
    - Max 1 joker
    - No all-joker combinations
    - No two cards of the same suit
    """
    if len(cards) < 3 or len(cards) > 4:
        return ValidationResult(
            False, error="La combinazione richiede 3 o 4 carte"
        )

    jokers = [c for c in cards if c.is_joker]
    regulars = [c for c in cards if not c.is_joker]

    if len(jokers) > 1:
        return ValidationResult(False, error="Massimo 1 jolly per combinazione")

    if not regulars:
        return ValidationResult(
            False, error="La combinazione non può essere composta solo da jolly"
        )

    if len(regulars) < 2:
        return ValidationResult(
            False, error="Servono almeno 2 carte regolari nella combinazione"
        )

    # All same rank
    rank = regulars[0].rank
    if not all(c.rank == rank for c in regulars):
        return ValidationResult(
            False, error="Tutte le carte devono avere lo stesso valore"
        )

    # All different suits
    suits = [c.suit for c in regulars]
    if len(suits) != len(set(suits)):
        return ValidationResult(
            False, error="Tutte le carte devono avere semi diversi"
        )

    # Calculate points
    points = sum(card_points(c) for c in regulars)
    if jokers:
        # Joker takes the value of the rank it represents
        points += card_points(regulars[0])

    return ValidationResult(True, points=points)


def validate_game(cards: list[Card]) -> ValidationResult:
    """Try to validate cards as a sequence first, then as a combination."""
    seq_result = is_valid_sequence(cards)
    if seq_result.valid:
        return seq_result
    comb_result = is_valid_combination(cards)
    if comb_result.valid:
        return comb_result
    return ValidationResult(
        False,
        error=f"Gioco non valido. Sequenza: {seq_result.error}. Combinazione: {comb_result.error}",
    )


def detect_game_type(cards: list[Card]) -> str | None:
    """Detect whether cards form a sequence or combination. Returns type or None."""
    if is_valid_sequence(cards).valid:
        return GAME_TYPE_SEQUENCE
    if is_valid_combination(cards).valid:
        return GAME_TYPE_COMBINATION
    return None


def is_valid_opening(games: list[list[Card]]) -> ValidationResult:
    """Validate an opening: all games valid, total points >= 40.

    The joker within opening games takes the value of the card it replaces.
    """
    if not games:
        return ValidationResult(False, error="Nessun gioco da calare")

    total_points = 0
    for game_cards in games:
        result = validate_game(game_cards)
        if not result.valid:
            return ValidationResult(
                False, error=f"Gioco non valido nell'apertura: {result.error}"
            )
        total_points += result.points

    if total_points < OPENING_THRESHOLD:
        return ValidationResult(
            False,
            error=f"Apertura insufficiente: {total_points} punti (minimo {OPENING_THRESHOLD})",
        )

    return ValidationResult(True, points=total_points)


def can_attach(card: Card, table_game: TableGame) -> ValidationResult:
    """Check if a card can be attached to an existing table game.

    For sequences: card extends at the beginning or end.
    For combinations: card has same rank, different suit, total <= 4.
    """
    if table_game.game_type == GAME_TYPE_SEQUENCE:
        return _can_attach_to_sequence(card, table_game)
    elif table_game.game_type == GAME_TYPE_COMBINATION:
        return _can_attach_to_combination(card, table_game)
    return ValidationResult(False, error="Tipo di gioco sconosciuto")


def _can_attach_to_sequence(card: Card, table_game: TableGame) -> ValidationResult:
    """Check if a card can extend a sequence."""
    if card.is_joker:
        # Joker can extend at either end if max 1 joker total
        existing_jokers = sum(1 for c in table_game.cards if c.is_joker)
        if existing_jokers >= 1:
            return ValidationResult(False, error="La sequenza ha già un jolly")
        # Can extend
        return ValidationResult(True, points=card.points())

    existing_regulars = [c for c in table_game.cards if not c.is_joker]
    if not existing_regulars:
        return ValidationResult(False, error="Sequenza senza carte regolari")

    suit = existing_regulars[0].suit
    if card.suit != suit:
        return ValidationResult(False, error="Seme diverso dalla sequenza")

    # Determine the rank range of the sequence
    # We need to figure out the actual ranks including joker positions
    seq_ranks = _get_sequence_ranks(table_game.cards)
    if seq_ranks is None:
        return ValidationResult(False, error="Sequenza non valida sul tavolo")

    min_rank = min(seq_ranks)
    max_rank = max(seq_ranks)

    # Can extend at start or end
    card_rank = card.rank
    # Handle Ace: can be 1 (before 2) or 14 (after K)
    if card_rank == ACE:
        if min_rank == 2:
            return ValidationResult(True, points=ACE_POINTS_LOW)
        if max_rank == KING:
            return ValidationResult(True, points=ACE_POINTS_HIGH)
        # Ace as 14 if sequence already has ace-high
        if max_rank == 14:
            return ValidationResult(False, error="Sequenza già completa con Asso alto")
        return ValidationResult(False, error="L'Asso non si attacca a questa sequenza")

    if card_rank == min_rank - 1 and card_rank >= 1:
        return ValidationResult(True, points=card_points(card))
    if card_rank == max_rank + 1 and card_rank <= KING:
        return ValidationResult(True, points=card_points(card))

    # Check if Ace-high extends: if max is K (13), Ace (rank 1) goes as 14
    # Already handled above in the ACE branch

    return ValidationResult(False, error="La carta non estende la sequenza")


def _get_sequence_ranks(cards: list[Card]) -> list[int] | None:
    """Get the rank positions in a sequence, resolving joker placement.

    Returns list of ranks (using 14 for ace-high) or None if invalid.
    """
    jokers = [c for c in cards if c.is_joker]
    regulars = [c for c in cards if not c.is_joker]

    if not regulars:
        return None

    ranks = sorted(c.rank for c in regulars)

    # Try ace-low and ace-high
    for ace_val in ([1] if ACE not in ranks else [1, 14]):
        try_ranks = sorted([ace_val if r == ACE else r for r in ranks])

        # Build full sequence filling joker gaps
        full = [try_ranks[0]]
        jokers_used = 0
        for i in range(1, len(try_ranks)):
            diff = try_ranks[i] - try_ranks[i - 1]
            if diff == 1:
                full.append(try_ranks[i])
            elif diff == 2 and jokers_used < len(jokers):
                full.append(try_ranks[i - 1] + 1)
                full.append(try_ranks[i])
                jokers_used += 1
            else:
                break
        else:
            # Place remaining jokers at ends
            remaining_jokers = len(jokers) - jokers_used
            for _ in range(remaining_jokers):
                if full[-1] + 1 <= 14:
                    full.append(full[-1] + 1)
                elif full[0] - 1 >= 1:
                    full.insert(0, full[0] - 1)
            return full

    return None


def _can_attach_to_combination(
    card: Card, table_game: TableGame
) -> ValidationResult:
    """Check if a card can be added to a combination."""
    if len(table_game.cards) >= 4:
        return ValidationResult(False, error="La combinazione ha già 4 carte")

    regulars = [c for c in table_game.cards if not c.is_joker]
    if not regulars:
        return ValidationResult(False, error="Combinazione senza carte regolari")

    if card.is_joker:
        existing_jokers = sum(1 for c in table_game.cards if c.is_joker)
        if existing_jokers >= 1:
            return ValidationResult(False, error="La combinazione ha già un jolly")
        return ValidationResult(True, points=card_points(regulars[0]))

    rank = regulars[0].rank
    if card.rank != rank:
        return ValidationResult(
            False, error="La carta deve avere lo stesso valore"
        )

    # Check suit not already present
    existing_suits = {c.suit for c in regulars}
    if card.suit in existing_suits:
        return ValidationResult(False, error="Seme già presente nella combinazione")

    return ValidationResult(True, points=card_points(card))


def can_substitute_joker(
    card: Card, table_game: TableGame
) -> ValidationResult:
    """Check if a card can replace a joker in a table game.

    The card must be the exact card the joker is substituting.
    """
    joker_indices = [i for i, c in enumerate(table_game.cards) if c.is_joker]
    if not joker_indices:
        return ValidationResult(False, error="Nessun jolly in questo gioco")

    if card.is_joker:
        return ValidationResult(False, error="Non puoi sostituire un jolly con un jolly")

    if table_game.game_type == GAME_TYPE_COMBINATION:
        regulars = [c for c in table_game.cards if not c.is_joker]
        rank = regulars[0].rank
        if card.rank != rank:
            return ValidationResult(
                False, error="La carta deve avere lo stesso valore della combinazione"
            )
        existing_suits = {c.suit for c in regulars}
        if card.suit in existing_suits:
            return ValidationResult(False, error="Seme già presente nella combinazione")
        return ValidationResult(True)

    elif table_game.game_type == GAME_TYPE_SEQUENCE:
        regulars = [c for c in table_game.cards if not c.is_joker]
        suit = regulars[0].suit
        if card.suit != suit:
            return ValidationResult(False, error="Seme diverso dalla sequenza")

        seq_ranks = _get_sequence_ranks(table_game.cards)
        if seq_ranks is None:
            return ValidationResult(False, error="Sequenza non valida")

        # Find the joker's position rank
        joker_idx = joker_indices[0]
        # The joker fills a specific rank in the sequence
        # We need to determine what rank the joker represents
        sorted_with_pos = []
        joker_rank_in_seq = None
        rank_idx = 0
        for i, c in enumerate(table_game.cards):
            if c.is_joker:
                joker_rank_in_seq = seq_ranks[i] if i < len(seq_ranks) else None
            sorted_with_pos.append((i, c))

        # Simpler approach: the joker represents the missing rank
        regular_ranks = set()
        for c in regulars:
            r = c.rank
            regular_ranks.add(r)

        missing_ranks = set(seq_ranks) - regular_ranks
        # Handle ace-high (rank 14 means ace)
        for mr in missing_ranks:
            check_rank = ACE if mr == 14 else mr
            if card.rank == check_rank and card.suit == suit:
                return ValidationResult(True)

        return ValidationResult(
            False, error="La carta non corrisponde alla posizione del jolly"
        )

    return ValidationResult(False, error="Tipo di gioco sconosciuto")


def is_valid_discard(
    card: Card,
    drawn_from_discard: Card | None,
    table_games: list[TableGame],
    player_has_opened: bool,
    num_players: int,
    cards_in_hand_after: int,
) -> ValidationResult:
    """Validate a discard action.

    Rules:
    1. Cannot discard the same card just picked from the discard pile.
    2. In games with >2 players, cannot discard a card that could attach
       to a table game (unless closing with this discard).
    """
    # Rule 1: Cannot discard card picked from discard
    if drawn_from_discard is not None and card == drawn_from_discard:
        return ValidationResult(
            False,
            error="Non puoi scartare la stessa carta appena raccolta dal pozzo",
        )

    is_closing = cards_in_hand_after == 0

    # Rule 2: Cannot discard attachable card in >2 player games (unless closing)
    if num_players > 2 and player_has_opened and not is_closing:
        for tg in table_games:
            result = can_attach(card, tg)
            if result.valid:
                return ValidationResult(
                    False,
                    error="Non puoi scartare una carta che si attacca a un gioco sul tavolo",
                )

    return ValidationResult(True)
