"""Score calculation and elimination logic for Scala 40."""

from __future__ import annotations

from src.game.models import Card, GameState


def calculate_hand_score(hand: list[Card]) -> int:
    """Sum point values of cards remaining in hand.

    Ace always counts as 11 when in hand (penalty scoring).
    Joker = 25, Face cards = 10, others = face value.
    """
    return sum(card.points(low_ace=False) for card in hand)


def apply_round_scores(game: GameState, closer_user_id: str) -> None:
    """Apply scores after a round ends.

    The closer gets 0 points. Everyone else gets the sum of cards in hand.
    Scores are accumulated into game.scores.
    """
    for player in game.players:
        if player.is_eliminated:
            continue
        if player.user_id == closer_user_id:
            round_score = 0
        else:
            round_score = calculate_hand_score(player.hand)
        player.score = round_score
        game.scores[player.user_id] = game.scores.get(player.user_id, 0) + round_score


def check_eliminations(game: GameState) -> list[str]:
    """Check which players have reached the elimination threshold.

    Returns list of newly eliminated user_ids.
    """
    threshold = game.settings.get("elimination_score", 101)
    newly_eliminated = []
    for player in game.players:
        if player.is_eliminated:
            continue
        if game.scores.get(player.user_id, 0) >= threshold:
            player.is_eliminated = True
            newly_eliminated.append(player.user_id)
    return newly_eliminated


def check_winner(game: GameState) -> str | None:
    """If only one non-eliminated player remains, return their user_id."""
    active = game.get_active_players()
    if len(active) == 1:
        return active[0].user_id
    return None
