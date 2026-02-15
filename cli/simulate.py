"""Simulate Scala 40 games with random AI players.

Usage: python -m cli.simulate --games 100 --players 4 [--seed 42] [--verbose]
"""

from __future__ import annotations

import argparse
import random
import time

from src.db.memory import InMemoryGameRepository
from src.game.engine import GameEngine
from src.game.integrity import validate_game_integrity
from src.game.models import Card, GameState
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


def find_opening_combo(hand: list[Card]) -> list[list[Card]] | None:
    """Try to find a valid opening combination from the hand.

    Simple greedy approach: try all 3-card and 4-card subsets.
    """
    from itertools import combinations

    valid_games: list[tuple[list[Card], int]] = []

    # Find all valid 3 and 4-card games
    for size in [3, 4]:
        for combo in combinations(range(len(hand)), size):
            cards = [hand[i] for i in combo]
            result = validate_game(cards)
            if result.valid:
                valid_games.append((cards, result.points))

    # Try to find combinations that sum >= 40
    # Greedy: sort by points desc, pick non-overlapping
    valid_games.sort(key=lambda x: x[1], reverse=True)

    selected: list[list[Card]] = []
    used_indices: set[int] = set()
    total_points = 0

    for cards, points in valid_games:
        indices = set()
        for card in cards:
            for i, h in enumerate(hand):
                if i not in used_indices and i not in indices and h == card:
                    indices.add(i)
                    break
        if len(indices) == len(cards) and not indices & used_indices:
            selected.append(cards)
            used_indices.update(indices)
            total_points += points
            if total_points >= 40:
                return selected

    return None


def ai_turn(engine: GameEngine, game: GameState, rng: random.Random) -> GameState:
    """Execute one AI turn. Returns updated game state."""
    uid = game.current_turn_user_id
    player = game.get_player(uid)
    assert player is not None

    # Draw phase
    if game.turn_phase == PHASE_DRAW:
        source = "deck"
        if player.has_opened and game.discard_pile:
            # 30% chance to pick from discard — but only if we can still
            # find a valid discard afterward (avoids deadlock in >2p games).
            if rng.random() < 0.3:
                top_discard = game.discard_pile[-1]
                num_players = len(game.get_active_players())
                has_valid_discard = False
                for hc in player.hand:
                    if hc == top_discard:
                        continue  # can't discard the card we'd pick
                    if num_players > 2 and player.has_opened:
                        # Check attachable rule
                        attachable = any(
                            can_attach(hc, tg).valid for tg in game.table_games
                        )
                        if attachable:
                            continue
                    has_valid_discard = True
                    break
                if has_valid_discard:
                    source = "discard"
        result = engine.process_draw(game.game_id, uid, source)
        if not result.success:
            # Fallback to deck
            result = engine.process_draw(game.game_id, uid, "deck")
        if not result.success:
            raise RuntimeError(f"Draw failed: {result.error}")
        assert result.game is not None
        game = result.game

    # Play phase
    if game.turn_phase in (PHASE_PLAY, PHASE_DISCARD):
        player = game.get_player(uid)
        assert player is not None

        # Try to open if not opened
        if not player.has_opened:
            opening = find_opening_combo(player.hand)
            if opening:
                result = engine.process_open(game.game_id, uid, opening)
                if result.success:
                    assert result.game is not None
                    game = result.game
                    player = game.get_player(uid)
                    assert player is not None

        # If opened, try to play more games or attach
        # Keep at least 1 card for discard (unless we can close)
        if player.has_opened and game.turn_phase == PHASE_PLAY:
            # Try to play additional games
            from itertools import combinations

            for size in [3, 4]:
                if len(player.hand) <= size:
                    break
                for combo in combinations(range(len(player.hand)), size):
                    cards = [player.hand[i] for i in combo]
                    vr = validate_game(cards)
                    if vr.valid:
                        result = engine.process_play(game.game_id, uid, cards)
                        if result.success:
                            assert result.game is not None
                            game = result.game
                            player = game.get_player(uid)
                            assert player is not None
                            break

            # Try to attach cards (keep at least 1 for discard)
            for tg in list(game.table_games):
                if len(player.hand) <= 1:
                    break
                for card in list(player.hand):
                    if len(player.hand) <= 1:
                        break
                    ar = can_attach(card, tg)
                    if ar.valid:
                        result = engine.process_attach(
                            game.game_id, uid, card, tg.game_id
                        )
                        if result.success:
                            assert result.game is not None
                            game = result.game
                            player = game.get_player(uid)
                            assert player is not None
                            break

    # Discard phase
    if game.turn_phase in (PHASE_PLAY, PHASE_DISCARD):
        player = game.get_player(uid)
        assert player is not None
        if not player.hand:
            # Edge case: player somehow has 0 cards without closing
            # This shouldn't happen with the guard above
            return game

        # Try each card until a valid discard is found
        hand_shuffled = list(player.hand)
        rng.shuffle(hand_shuffled)

        for card in hand_shuffled:
            result = engine.process_discard(game.game_id, uid, card)
            if result.success:
                assert result.game is not None
                return result.game

        # If no valid discard found (e.g., drawn from discard and all cards
        # attach or are the same card), try harder: the drawn_from_discard
        # constraint only prevents the exact same card object
        # Just discard the first card we can
        for card in player.hand:
            result = engine.process_discard(game.game_id, uid, card)
            if result.success:
                assert result.game is not None
                return result.game

        # True deadlock - skip turn by forcing discard
        # This is a degenerate case
        return game

    return game


def simulate_game(num_players: int, rng: random.Random, verbose: bool = False) -> dict:
    """Simulate one complete game. Returns stats dict."""
    repo = InMemoryGameRepository()
    engine = GameEngine(repo, rng)

    player_ids = [f"p{i + 1}" for i in range(num_players)]
    game = engine.create_game(player_ids, lobby_id="sim")
    result = engine.start_round(game.game_id)
    assert result.game is not None
    game = result.game

    max_turns = 5000
    turn_count = 0
    smazzate = 0

    while game.status != STATUS_FINISHED and turn_count < max_turns:
        if game.status == STATUS_ROUND_END:
            smazzate += 1
            result = engine.start_round(game.game_id)
            if not result.success:
                return {"error": result.error, "turns": turn_count}
            assert result.game is not None
            game = result.game

        if game.status != STATUS_PLAYING:
            break

        # Integrity check
        errors = validate_game_integrity(game)
        if errors:
            return {
                "error": f"Integrity: {errors}",
                "turns": turn_count,
            }

        try:
            game = ai_turn(engine, game, rng)
        except Exception as e:
            return {"error": str(e), "turns": turn_count}

        turn_count += 1

        if verbose and turn_count % 100 == 0:
            print(f"  Turn {turn_count}, smazzata {game.smazzata_number}")

    winner = None
    active = game.get_active_players()
    if len(active) == 1:
        winner = active[0].user_id

    return {
        "winner": winner,
        "turns": turn_count,
        "smazzate": game.smazzata_number,
        "scores": dict(game.scores),
        "error": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scala 40 Simulator")
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--players", type=int, default=4, choices=[2, 3, 4])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    base_seed = args.seed if args.seed is not None else int(time.time())
    n, p = args.games, args.players
    print(f"Simulating {n} games with {p} players (base seed: {base_seed})")

    errors = 0
    wins: dict[str, int] = {}
    total_turns = 0
    total_smazzate = 0

    for i in range(args.games):
        rng = create_rng(base_seed + i)
        result = simulate_game(args.players, rng, verbose=args.verbose)

        if result.get("error"):
            errors += 1
            if args.verbose:
                print(f"  Game {i + 1}: ERROR - {result['error']}")
        else:
            winner = result.get("winner", "none")
            wins[winner] = wins.get(winner, 0) + 1
            total_turns += result["turns"]
            total_smazzate += result["smazzate"]

            if args.verbose:
                print(
                    f"  Game {i + 1}: winner={winner}, "
                    f"turns={result['turns']}, smazzate={result['smazzate']}"
                )

        if (i + 1) % 100 == 0 and not args.verbose:
            print(f"  {i + 1}/{args.games} completati...")

    completed = args.games - errors
    print("\nRisultati:")
    print(f"  Partite completate: {completed}/{args.games}")
    print(f"  Errori: {errors}")
    if completed > 0:
        print(f"  Turni medi: {total_turns / completed:.1f}")
        print(f"  Smazzate medie: {total_smazzate / completed:.1f}")
        print(f"  Vittorie: {wins}")


if __name__ == "__main__":
    main()
