"""Interactive CLI for Scala 40.

Usage: python -m cli.play --players 2 [--seed 42]
"""

from __future__ import annotations

import argparse

from src.db.memory import InMemoryGameRepository
from src.game.engine import GameEngine
from src.game.integrity import validate_game_integrity
from src.game.models import Card, GameState
from src.utils.constants import (
    PHASE_DISCARD,
    PHASE_DRAW,
    PHASE_PLAY,
    STATUS_FINISHED,
    STATUS_PLAYING,
    STATUS_ROUND_END,
)
from src.utils.crypto import create_rng


def parse_card(s: str) -> Card:
    """Parse compact card notation."""
    return Card.from_compact(s.strip())


def display_hand(hand: list[Card]) -> str:
    """Format hand for terminal display."""
    if not hand:
        return "  (vuota)"
    lines = []
    for i, card in enumerate(sorted(hand, key=lambda c: (c.suit, c.rank)), 1):
        lines.append(f"  {i:2d}. {card.display()} [{card.compact()}]")
    return "\n".join(lines)


def display_table(game: GameState) -> str:
    """Format table state for terminal display."""
    lines = [
        "",
        f"{'=' * 50}",
        f"  SCALA 40 — Smazzata #{game.smazzata_number}",
        f"{'=' * 50}",
        "",
        f"  Turno di: {game.current_turn_user_id} (fase: {game.turn_phase})",
    ]

    if game.discard_pile:
        top = game.discard_pile[-1].display()
        lines.append(f"  Pozzo: {top}")
    else:
        lines.append("  Pozzo: (vuoto)")

    lines.append(f"  Tallone: {len(game.deck)} carte")
    lines.append("")

    if game.table_games:
        lines.append("  Giochi sul tavolo:")
        for tg in game.table_games:
            cards_str = " ".join(c.display() for c in tg.cards)
            lines.append(
                f"    [{tg.game_id[:6]}] {tg.owner}: [{cards_str}] ({tg.game_type})"
            )
        lines.append("")

    lines.append("  Carte in mano:")
    for player in game.players:
        if player.is_eliminated:
            lines.append(f"    {player.user_id}: ELIMINATO")
        else:
            status = ""
            if player.user_id == game.current_turn_user_id:
                status = " ← turno"
            if not player.has_opened:
                status += " (non ha aperto)"
            lines.append(f"    {player.user_id}: {len(player.hand)} carte{status}")

    lines.append("")
    scores = " | ".join(f"{uid}: {score}" for uid, score in game.scores.items())
    lines.append(f"  Punteggi: {scores}")
    lines.append("")

    return "\n".join(lines)


def display_actions(game: GameState, user_id: str) -> str:
    """Show available actions."""
    player = game.get_player(user_id)
    assert player is not None
    lines = ["  Azioni disponibili:"]

    if game.turn_phase == PHASE_DRAW:
        lines.append("    draw       - Pesca dal tallone")
        if player.has_opened and game.discard_pile:
            top = game.discard_pile[-1].display()
            lines.append(f"    pickup     - Prendi dal pozzo ({top})")
    elif game.turn_phase in (PHASE_PLAY, PHASE_DISCARD):
        if not player.has_opened and game.turn_phase == PHASE_DISCARD:
            lines.append(
                "    open <carte> | <carte> - Apri (es: open Kh Kd Kc | 5h 5d 5c)"
            )
        if player.has_opened:
            lines.append("    play <carte>   - Cala un gioco (es: play 3h 4h 5h)")
            lines.append(
                "    attach <carta> <id> - Attacca a gioco (es: attach 6h abc123)"
            )
        lines.append("    discard <carta> - Scarta (es: discard 8h)")

    lines.append("    hand       - Mostra la mano")
    lines.append("    table      - Mostra il tavolo")
    lines.append("    quit       - Esci")
    lines.append("")

    return "\n".join(lines)


def play_game(num_players: int, seed: int | None = None) -> None:
    rng = create_rng(seed)
    repo = InMemoryGameRepository()
    engine = GameEngine(repo, rng)

    player_ids = [f"player{i + 1}" for i in range(num_players)]
    game = engine.create_game(player_ids, lobby_id="local")
    result = engine.start_round(game.game_id)
    if not result.success:
        print(f"Errore avvio: {result.error}")
        return
    assert result.game is not None
    game = result.game

    print("\n  Benvenuti a Scala 40!")
    print(f"  Giocatori: {', '.join(player_ids)}")
    if seed is not None:
        print(f"  Seed: {seed}")

    while game.status == STATUS_PLAYING:
        # Display state
        print(display_table(game))

        current = game.current_turn_user_id
        player = game.get_player(current)
        assert player is not None
        print(f"  --- Mano di {current} ---")
        print(display_hand(player.hand))
        print()
        print(display_actions(game, current))

        # Get input
        try:
            action_str = input(f"  {current}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Partita interrotta.")
            return

        if not action_str:
            continue

        parts = action_str.split()
        cmd = parts[0].lower()

        if cmd == "quit":
            print("  Partita abbandonata.")
            return
        elif cmd == "hand":
            print(display_hand(player.hand))
            continue
        elif cmd == "table":
            print(display_table(game))
            continue
        elif cmd == "draw":
            result = engine.process_draw(game.game_id, current, "deck")
        elif cmd == "pickup":
            result = engine.process_draw(game.game_id, current, "discard")
        elif cmd == "open":
            # Parse: open Kh Kd Kc | 5h 5d 5c
            try:
                rest = " ".join(parts[1:])
                game_strs = rest.split("|")
                games = []
                for gs in game_strs:
                    cards = [parse_card(c) for c in gs.split()]
                    if cards:
                        games.append(cards)
                result = engine.process_open(game.game_id, current, games)
            except Exception as e:
                print(f"  Errore parsing: {e}")
                continue
        elif cmd == "play":
            try:
                cards = [parse_card(p) for p in parts[1:]]
                result = engine.process_play(game.game_id, current, cards)
            except Exception as e:
                print(f"  Errore parsing: {e}")
                continue
        elif cmd == "attach":
            if len(parts) < 3:
                print("  Uso: attach <carta> <game_id>")
                continue
            try:
                card = parse_card(parts[1])
                tg_id = parts[2]
                # Find matching table game ID
                matching = [
                    tg for tg in game.table_games if tg.game_id.startswith(tg_id)
                ]
                if not matching:
                    print(f"  Gioco '{tg_id}' non trovato")
                    continue
                result = engine.process_attach(
                    game.game_id, current, card, matching[0].game_id
                )
            except Exception as e:
                print(f"  Errore: {e}")
                continue
        elif cmd == "discard":
            if len(parts) < 2:
                print("  Uso: discard <carta>")
                continue
            try:
                card = parse_card(parts[1])
                result = engine.process_discard(game.game_id, current, card)
            except Exception as e:
                print(f"  Errore parsing: {e}")
                continue
        else:
            print(f"  Comando sconosciuto: {cmd}")
            continue

        if result.success:
            assert result.game is not None
            game = result.game
            for event in result.events:
                ev_type = event.get("event", "")
                if ev_type == "closure":
                    print(f"\n  *** {event['user_id']} ha chiuso! ***")
                    print(f"  Punteggi: {event['scores']}")
                elif ev_type == "elimination":
                    uid = event["user_id"]
                    sc = event["total_score"]
                    print(f"  *** {uid} è eliminato! (score: {sc})")
                elif ev_type == "game_end":
                    print(f"\n  *** {event['winner']} ha vinto la partita! ***")
                    print(f"  Punteggi finali: {event['final_scores']}")
        else:
            print(f"  ✗ {result.error}")
            continue

        # Integrity check
        if game.status == STATUS_PLAYING:
            errors = validate_game_integrity(game)
            if errors:
                print(f"\n  ⚠ ERRORE INTEGRITÀ: {errors}")
                return

        # Handle round end
        if game.status == STATUS_ROUND_END:
            print("\n  Fine della smazzata. Inizio nuova smazzata...")
            result = engine.start_round(game.game_id)
            if result.success:
                assert result.game is not None
                game = result.game
            else:
                print(f"  Errore: {result.error}")
                return

    if game.status == STATUS_FINISHED:
        print("\n  Partita terminata!")
        for uid, score in sorted(game.scores.items(), key=lambda x: x[1]):
            player = game.get_player(uid)
            assert player is not None
            eliminated = player.is_eliminated
            status = " (ELIMINATO)" if eliminated else ""
            print(f"    {uid}: {score} punti{status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scala 40 CLI")
    parser.add_argument("--players", type=int, default=2, choices=[2, 3, 4])
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    play_game(args.players, args.seed)


if __name__ == "__main__":
    main()
