"""Turn notifications — messages sent after state-changing actions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.bot.messages import (
    build_draw_keyboard,
    format_hand,
    format_scores,
    format_table,
)
from src.game.models import GameState
from src.utils.constants import STATUS_FINISHED, STATUS_ROUND_END

if TYPE_CHECKING:
    from src.bot.deps import Deps

logger = logging.getLogger("scala40.notifications")


def notify_turn_start(game: GameState, deps: Deps) -> None:
    """Send draw keyboard to the current player via DM."""
    player = game.get_player(game.current_turn_user_id)
    if player is None:
        return

    user = deps.user_repo.get_user(game.current_turn_user_id)
    if user is None:
        return

    chat_id = user.get("chatId")
    if not chat_id:
        return

    deps.telegram.send_message(chat_id, format_hand(player))
    deps.telegram.send_message(
        chat_id,
        "Il tuo turno! Pesca una carta.",
        reply_markup=build_draw_keyboard(player.has_opened),
    )


def notify_table_update(game: GameState, chat_id: str, deps: Deps) -> None:
    """Send table state to the group chat."""
    deps.telegram.send_message(chat_id, format_table(game))


def notify_round_end(
    game: GameState,
    chat_id: str,
    events: list[dict],
    deps: Deps,
) -> None:
    """Handle round end: show scores, eliminations, start next round."""
    # Show scores
    deps.telegram.send_message(chat_id, format_scores(game))

    # Announce eliminations
    for ev in events:
        if ev.get("event") == "elimination":
            uid = ev["user_id"]
            score = ev.get("total_score", "?")
            deps.telegram.send_message(
                chat_id,
                f"<b>{uid}</b> eliminato! (punteggio: {score})",
            )

    if game.status == STATUS_FINISHED:
        # Announce winner
        winner_ev = next((e for e in events if e.get("event") == "game_end"), None)
        winner = winner_ev["winner"] if winner_ev else "?"
        deps.telegram.send_message(
            chat_id,
            f"<b>Partita finita!</b> Vince <b>{winner}</b>!",
        )
        # Clear currentGameId for all players
        for player in game.players:
            user = deps.user_repo.get_user(player.user_id)
            if user:
                user["currentGameId"] = None
                deps.user_repo.save_user(user)

    elif game.status == STATUS_ROUND_END:
        # Start next round
        result = deps.engine.start_round(game.game_id)
        if not result.success:
            deps.telegram.send_message(
                chat_id,
                f"Errore avvio nuovo round: {result.error}",
            )
            return

        new_game = result.game
        assert new_game is not None

        deps.telegram.send_message(
            chat_id,
            f"<b>Smazzata #{new_game.smazzata_number}</b>",
        )
        deps.telegram.send_message(chat_id, format_table(new_game))

        # DM each active player their hand
        for player in new_game.get_active_players():
            user = deps.user_repo.get_user(player.user_id)
            if user and user.get("chatId"):
                deps.telegram.send_message(user["chatId"], format_hand(player))

        notify_turn_start(new_game, deps)
