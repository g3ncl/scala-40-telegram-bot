"""Deck operations for Scala 40: creation, shuffle, deal, draw."""

from __future__ import annotations

import random

from src.game.models import Card
from src.utils.constants import (
    CARDS_PER_PLAYER,
    JOKER_RANK,
    JOKER_SUIT,
    RANKS,
    SUITS,
)


def create_deck() -> list[Card]:
    """Create a full 108-card deck (2x52 suited cards + 4 jokers)."""
    cards: list[Card] = []
    for deck_num in range(2):
        for suit in SUITS:
            for rank in RANKS:
                cards.append(Card(suit=suit, rank=rank, deck=deck_num))
        # 2 jokers per deck
        cards.append(Card(suit=JOKER_SUIT, rank=JOKER_RANK, deck=deck_num))
        cards.append(Card(suit=JOKER_SUIT, rank=JOKER_RANK, deck=deck_num))
    return cards


def shuffle_cards(cards: list[Card], rng: random.Random) -> list[Card]:
    """Fisher-Yates shuffle using provided RNG. Returns a new list."""
    shuffled = list(cards)
    for i in range(len(shuffled) - 1, 0, -1):
        j = rng.randint(0, i)
        shuffled[i], shuffled[j] = shuffled[j], shuffled[i]
    return shuffled


def deal(
    deck: list[Card], num_players: int, cards_each: int = CARDS_PER_PLAYER
) -> tuple[list[list[Card]], list[Card], Card]:
    """Deal cards from a shuffled deck.

    Returns:
        (hands, remaining_deck, first_discard)
        hands: list of hands, one per player
        remaining_deck: cards left in the tallone
        first_discard: first card placed on discard pile
    """
    remaining = list(deck)
    hands: list[list[Card]] = [[] for _ in range(num_players)]
    # Deal one at a time, round-robin
    for _ in range(cards_each):
        for p in range(num_players):
            hands[p].append(remaining.pop(0))
    first_discard = remaining.pop(0)
    return hands, remaining, first_discard


def draw_from_deck(deck: list[Card]) -> tuple[Card, list[Card]]:
    """Draw the top card from the deck.

    Returns (drawn_card, remaining_deck).
    Raises ValueError if deck is empty.
    """
    if not deck:
        raise ValueError("Deck is empty")
    remaining = list(deck)
    card = remaining.pop(0)
    return card, remaining


def draw_from_discard(discard_pile: list[Card]) -> tuple[Card, list[Card]]:
    """Pick up the top card from the discard pile (last element).

    Returns (picked_card, remaining_pile).
    Raises ValueError if pile is empty.
    """
    if not discard_pile:
        raise ValueError("Discard pile is empty")
    remaining = list(discard_pile)
    card = remaining.pop()  # top = last element
    return card, remaining


def reshuffle_discard(
    discard_pile: list[Card], rng: random.Random
) -> tuple[list[Card], Card]:
    """When deck runs out, reshuffle discard pile into new deck.

    Keeps the last discarded card as the new discard pile top.
    Returns (new_deck, last_discard).
    """
    if len(discard_pile) < 2:
        raise ValueError("Not enough cards to reshuffle")
    last_discard = discard_pile[-1]
    to_shuffle = discard_pile[:-1]
    new_deck = shuffle_cards(to_shuffle, rng)
    return new_deck, last_discard
