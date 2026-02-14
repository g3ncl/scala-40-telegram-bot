"""Tests for deck operations."""

import random
from collections import Counter

import pytest

from src.game.deck import (
    create_deck,
    deal,
    draw_from_deck,
    draw_from_discard,
    reshuffle_discard,
    shuffle_cards,
)
from src.game.models import Card
from src.utils.constants import JOKER_SUIT, TOTAL_CARDS
from src.utils.crypto import create_rng


class TestCreateDeck:
    def test_total_cards(self):
        deck = create_deck()
        assert len(deck) == TOTAL_CARDS  # 108

    def test_four_jokers(self):
        deck = create_deck()
        jokers = [c for c in deck if c.is_joker]
        assert len(jokers) == 4

    def test_suited_cards_per_suit(self):
        deck = create_deck()
        for suit in ["h", "d", "c", "s"]:
            suited = [c for c in deck if c.suit == suit]
            assert len(suited) == 26  # 13 per deck * 2 decks

    def test_ranks_per_suit_per_deck(self):
        deck = create_deck()
        for suit in ["h", "d", "c", "s"]:
            for deck_num in range(2):
                cards = [c for c in deck if c.suit == suit and c.deck == deck_num]
                ranks = sorted(c.rank for c in cards)
                assert ranks == list(range(1, 14))


class TestShuffle:
    def test_preserves_cards(self):
        rng = create_rng(42)
        deck = create_deck()
        shuffled = shuffle_cards(deck, rng)
        assert len(shuffled) == len(deck)
        assert Counter(id(c) for c in deck) != Counter(id(c) for c in shuffled) or deck != shuffled
        # Same cards (as multiset)
        assert sorted(deck, key=lambda c: (c.suit, c.rank, c.deck)) == sorted(
            shuffled, key=lambda c: (c.suit, c.rank, c.deck)
        )

    def test_deterministic_with_seed(self):
        deck = create_deck()
        s1 = shuffle_cards(deck, create_rng(42))
        s2 = shuffle_cards(deck, create_rng(42))
        assert s1 == s2

    def test_different_seeds_different_order(self):
        deck = create_deck()
        s1 = shuffle_cards(deck, create_rng(42))
        s2 = shuffle_cards(deck, create_rng(99))
        assert s1 != s2


class TestDeal:
    def test_hand_sizes_4_players(self):
        rng = create_rng(42)
        deck = shuffle_cards(create_deck(), rng)
        hands, remaining, first_discard = deal(deck, 4)
        for hand in hands:
            assert len(hand) == 13
        assert len(remaining) == 108 - 52 - 1  # 55
        assert first_discard is not None

    def test_hand_sizes_2_players(self):
        rng = create_rng(42)
        deck = shuffle_cards(create_deck(), rng)
        hands, remaining, first_discard = deal(deck, 2)
        for hand in hands:
            assert len(hand) == 13
        assert len(remaining) == 108 - 26 - 1  # 81

    def test_all_cards_accounted_for(self):
        rng = create_rng(42)
        deck = shuffle_cards(create_deck(), rng)
        hands, remaining, first_discard = deal(deck, 3)
        all_cards = []
        for hand in hands:
            all_cards.extend(hand)
        all_cards.extend(remaining)
        all_cards.append(first_discard)
        assert len(all_cards) == TOTAL_CARDS


class TestDraw:
    def test_draw_from_deck(self):
        deck = [Card(suit="h", rank=i, deck=0) for i in range(1, 6)]
        card, remaining = draw_from_deck(deck)
        assert card == Card(suit="h", rank=1, deck=0)
        assert len(remaining) == 4

    def test_draw_from_empty_deck_raises(self):
        with pytest.raises(ValueError, match="empty"):
            draw_from_deck([])

    def test_draw_from_discard(self):
        pile = [Card(suit="h", rank=i, deck=0) for i in range(1, 4)]
        card, remaining = draw_from_discard(pile)
        assert card == Card(suit="h", rank=3, deck=0)  # last = top
        assert len(remaining) == 2

    def test_draw_from_empty_discard_raises(self):
        with pytest.raises(ValueError, match="empty"):
            draw_from_discard([])


class TestReshuffle:
    def test_reshuffle_creates_new_deck(self):
        rng = create_rng(42)
        pile = [Card(suit="h", rank=i, deck=0) for i in range(1, 10)]
        new_deck, last = reshuffle_discard(pile, rng)
        assert last == Card(suit="h", rank=9, deck=0)  # last card kept
        assert len(new_deck) == 8  # pile minus last card
        assert last not in new_deck

    def test_reshuffle_too_few_cards_raises(self):
        rng = create_rng(42)
        with pytest.raises(ValueError, match="Not enough"):
            reshuffle_discard([Card(suit="h", rank=1, deck=0)], rng)
