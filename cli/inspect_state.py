"""Inspect and validate a saved game state.

Usage:
  python -m cli.inspect_state --file game_snapshot.json
  python -m cli.inspect_state --file game_snapshot.json --player p2 --show hand
  python -m cli.inspect_state --file game_snapshot.json --show table
  python -m cli.inspect_state --file game_snapshot.json --validate
"""

from __future__ import annotations

import argparse
import json
import sys

from src.game.integrity import validate_game_integrity
from src.game.models import GameState


def inspect_state(
    file_path: str,
    player: str | None,
    show: str | None,
    validate: bool,
) -> None:
    with open(file_path) as f:
        data = json.load(f)

    game = GameState.from_dict(data)

    if validate:
        errors = validate_game_integrity(game)
        if errors:
            print("Errori di integrità:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        else:
            print("Stato valido ✓")
        return

    if player and show == "hand":
        p = game.get_player(player)
        if p is None:
            print(f"Giocatore {player} non trovato")
            sys.exit(1)
        print(f"Mano di {player} ({len(p.hand)} carte):")
        for i, card in enumerate(p.hand, 1):
            print(f"  {i:2d}. {card.display()} [{card.compact()}]")
        return

    if show == "table":
        if not game.table_games:
            print("Nessun gioco sul tavolo")
        else:
            print("Giochi sul tavolo:")
            for tg in game.table_games:
                cards_str = " ".join(c.display() for c in tg.cards)
                print(
                    f"  [{tg.game_id[:8]}] {tg.owner}: [{cards_str}] ({tg.game_type})"
                )
        return

    # Default: full dump
    print(f"Game ID: {game.game_id}")
    print(f"Smazzata: {game.smazzata_number}")
    print(f"Status: {game.status}")
    print(f"Turno: {game.current_turn_user_id} ({game.turn_phase})")
    print(f"Tallone: {len(game.deck)} carte")
    print(f"Pozzo: {len(game.discard_pile)} carte")
    if game.discard_pile:
        print(f"  Top: {game.discard_pile[-1].display()}")
    print(f"Punteggi: {game.scores}")
    print("Giocatori:")
    for p in game.players:
        status = (
            "ELIMINATO" if p.is_eliminated else ("aperto" if p.has_opened else "chiuso")
        )
        print(f"  {p.user_id}: {len(p.hand)} carte ({status})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Scala 40 game state")
    parser.add_argument("--file", required=True, help="Path to game state JSON")
    parser.add_argument("--player", help="Player ID to inspect")
    parser.add_argument("--show", choices=["hand", "table"], help="What to show")
    parser.add_argument("--validate", action="store_true", help="Validate integrity")
    args = parser.parse_args()
    inspect_state(args.file, args.player, args.show, args.validate)


if __name__ == "__main__":
    main()
