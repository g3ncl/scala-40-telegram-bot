"""Callback query handlers for Telegram bot."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.bot.messages import (
    build_attach_card_keyboard,
    build_attach_target_keyboard,
    build_card_select_keyboard,
    build_discard_keyboard,
    build_draw_keyboard,
    build_lobby_keyboard,
    build_main_menu_keyboard,
    build_play_keyboard,
    format_hand,
    format_help,
    format_lobby,
    format_table,
)
from src.bot.notifications import (
    notify_round_end,
    notify_table_update,
    notify_turn_start,
)
from src.game.models import Card

if TYPE_CHECKING:
    from src.bot.deps import Deps

logger = logging.getLogger("scala40.callbacks")


def handle_callback(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    """Dispatch callback query by prefix."""
    prefix = data.split(":")[0]

    dispatch = {
        "main": _cb_main,
        "lobby": _cb_lobby,
        "draw": _cb_draw,
        "menu": _cb_menu,
        "card": _cb_card_toggle,
        "conf": _cb_confirm,
        "grp": _cb_group,
        "disc": _cb_discard,
        "att_card": _cb_attach_card,
        "att_tg": _cb_attach_target,
        "cancel": _cb_cancel,
    }

    handler = dispatch.get(prefix)
    if handler is None:
        deps.telegram.answer_callback_query(cq_id, text="Azione non valida")
        return

    handler(user_id, chat_id, message_id, data, cq_id, deps)


# --- Main Menu ---


def _cb_main(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    action = data.split(":")[1]

    if action == "new":
        _ensure_user(user_id, chat_id, deps)
        result = deps.lobby_manager.create_lobby(user_id, chat_id)
        if not result.success:
            deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
            return
        lobby = result.lobby
        assert lobby is not None
        # Save lobby ref
        user = deps.user_repo.get_user(user_id)
        if user:
            user["currentLobbyId"] = lobby["lobbyId"]
            deps.user_repo.save_user(user)

        deps.telegram.answer_callback_query(cq_id, text="Lobby creata!")
        deps.telegram.edit_message(
            chat_id,
            message_id,
            format_lobby(lobby),
            reply_markup=build_lobby_keyboard(lobby, user_id),
        )

    elif action == "help":
        deps.telegram.answer_callback_query(cq_id)
        deps.telegram.edit_message(
            chat_id,
            message_id,
            format_help(),
            reply_markup=build_main_menu_keyboard(),
        )


# --- Lobby ---


def _cb_lobby(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    action = data.split(":")[1]
    
    # Need to find which lobby we are talking about.
    # Usually we rely on user's currentLobbyId, but if they click a button on an old message...
    # For now, rely on user record.
    user = deps.user_repo.get_user(user_id)
    if not user or not user.get("currentLobbyId"):
        deps.telegram.answer_callback_query(cq_id, text="Non sei in una lobby")
        return
    lobby_id = user["currentLobbyId"]

    if action == "ready":
        result = deps.lobby_manager.set_ready(user_id, lobby_id)
        if not result.success:
            deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
            return
        deps.telegram.answer_callback_query(cq_id, text="Stato aggiornato")
        assert result.lobby is not None
        deps.telegram.edit_message(
            chat_id,
            message_id,
            format_lobby(result.lobby),
            reply_markup=build_lobby_keyboard(result.lobby, user_id),
        )

    elif action == "leave":
        result = deps.lobby_manager.leave_lobby(user_id, lobby_id)
        if not result.success:
            deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
            return
        
        user["currentLobbyId"] = None
        deps.user_repo.save_user(user)
        
        deps.telegram.answer_callback_query(cq_id, text="Hai lasciato la lobby")
        # If host left, lobby might be closed. If just player, update message.
        # But we can't easily update the message if we are no longer in the lobby (we don't get the lobby back if closed).
        # However, leave_lobby returns the lobby state.
        
        lobby = result.lobby
        if lobby and lobby.get("status") != "closed":
             # We left, but lobby exists. Update message for others? 
             # Wait, we are editing OUR message. We should probably show main menu.
             deps.telegram.edit_message(
                chat_id,
                message_id,
                "Hai lasciato la lobby.",
                reply_markup=build_main_menu_keyboard(),
             )
        else:
             deps.telegram.edit_message(
                chat_id,
                message_id,
                "Lobby chiusa.",
                reply_markup=build_main_menu_keyboard(),
             )

    elif action == "refresh":
        lobby = deps.lobby_manager.get_lobby(lobby_id)
        if not lobby:
            deps.telegram.answer_callback_query(cq_id, text="Lobby non trovata")
            return
        deps.telegram.answer_callback_query(cq_id, text="Aggiornato")
        deps.telegram.edit_message(
            chat_id,
            message_id,
            format_lobby(lobby),
            reply_markup=build_lobby_keyboard(lobby, user_id),
        )

    elif action == "start":
        result = deps.lobby_manager.start_game(user_id, lobby_id)
        if not result.success:
            deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
            return
        
        deps.telegram.answer_callback_query(cq_id, text="Partita avviata!")
        game_id = result.game_id
        lobby = result.lobby
        assert game_id is not None
        assert lobby is not None

        # Set currentGameId on all players
        for p in lobby["players"]:
            pid = p["userId"]
            pu = deps.user_repo.get_user(pid)
            if pu is None:
                pu = {"userId": pid, "chatId": chat_id}
            pu["currentGameId"] = game_id
            deps.user_repo.save_user(pu)

        game = deps.engine.get_game(game_id)
        assert game is not None
        
        # We can edit the lobby message to show the table, or send a new one.
        # Sending a new one is better for history.
        # But we should probably remove the "Start" button from the lobby message so it's not clicked again.
        deps.telegram.edit_message(
            chat_id,
            message_id,
            f"Partita avviata! (Lobby {lobby.get('code')})",
            reply_markup=None
        )

        # Send table to group chat (if we knew it... but here chat_id is the user's chat or the group chat where button was clicked)
        deps.telegram.send_message(chat_id, format_table(game))

        # DM each player
        for player in game.players:
            pu = deps.user_repo.get_user(player.user_id)
            # If we don't know their chat_id, we can't DM. 
            # But we saved chatId in _ensure_user when they joined/interacted.
            player_chat = pu["chatId"] if pu else chat_id
            deps.telegram.send_message(player_chat, format_hand(player))

        # Send draw keyboard to current player
        current = game.get_player(game.current_turn_user_id)
        has_opened = current.has_opened if current else False
        cu = deps.user_repo.get_user(game.current_turn_user_id)
        current_chat = cu["chatId"] if cu else chat_id
        deps.telegram.send_message(
            current_chat,
            "Il tuo turno! Pesca una carta.",
            reply_markup=build_draw_keyboard(has_opened),
        )


# --- Draw ---


def _cb_draw(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "draw:deck" or "draw:discard"
    source = data.split(":")[1]
    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None

    result = deps.engine.process_draw(game.game_id, user_id, source)
    if not result.success:
        deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
        return

    deps.telegram.answer_callback_query(cq_id)
    deps.telegram.delete_message(chat_id, message_id)

    game = result.game
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None

    # Show hand + play keyboard
    deps.telegram.send_message(chat_id, format_hand(player))
    deps.telegram.send_message(
        chat_id,
        "Scegli un'azione:",
        reply_markup=build_play_keyboard(player.has_opened),
    )


# --- Menu ---


def _cb_menu(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    action = data.split(":")[1]
    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None

    deps.telegram.answer_callback_query(cq_id)

    if action == "discard":
        kb = build_discard_keyboard(player.hand)
        deps.telegram.edit_message(
            chat_id, message_id, "Scegli carta da scartare:", reply_markup=kb
        )
    elif action in ("play", "open"):
        mask = "0" * len(player.hand)
        kb = build_card_select_keyboard(player.hand, mask, action)
        deps.telegram.edit_message(
            chat_id, message_id, "Seleziona le carte:", reply_markup=kb
        )
    elif action == "attach":
        kb = build_attach_card_keyboard(player.hand)
        deps.telegram.edit_message(
            chat_id,
            message_id,
            "Quale carta vuoi attaccare?",
            reply_markup=kb,
        )


# --- Card toggle ---


def _cb_card_toggle(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "card:{idx}:{action}:{mask}"
    parts = data.split(":")
    action = parts[2]
    new_mask = parts[3]

    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None

    deps.telegram.answer_callback_query(cq_id)
    kb = build_card_select_keyboard(player.hand, new_mask, action)
    deps.telegram.edit_message(
        chat_id, message_id, "Seleziona le carte:", reply_markup=kb
    )


# --- Confirm ---


def _cb_confirm(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "conf:{action}:{mask}" or "conf:open:{mask1}+{mask2}..."
    parts = data.split(":")
    action = parts[1]
    mask_str = parts[2]

    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None

    sorted_hand = sorted(player.hand, key=lambda c: (c.suit, c.rank))

    if action == "play":
        selected = _mask_to_cards(sorted_hand, mask_str)
        if not selected:
            deps.telegram.answer_callback_query(
                cq_id, text="Seleziona almeno una carta"
            )
            return
        result = deps.engine.process_play(game.game_id, user_id, selected)
        if not result.success:
            deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
            return
        deps.telegram.answer_callback_query(cq_id, text="Gioco calato!")
        deps.telegram.delete_message(chat_id, message_id)
        game = result.game
        assert game is not None
        player = game.get_player(user_id)
        assert player is not None
        deps.telegram.send_message(chat_id, format_hand(player))
        deps.telegram.send_message(
            chat_id,
            "Scegli un'azione:",
            reply_markup=build_play_keyboard(player.has_opened),
        )

    elif action == "open":
        # mask_str can be "mask1+mask2+..." for multiple groups
        mask_parts = mask_str.split("+")
        groups = [_mask_to_cards(sorted_hand, m) for m in mask_parts]
        groups = [g for g in groups if g]
        if not groups:
            deps.telegram.answer_callback_query(
                cq_id, text="Seleziona almeno un gruppo di carte"
            )
            return
        result = deps.engine.process_open(game.game_id, user_id, groups)
        if not result.success:
            deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
            return
        deps.telegram.answer_callback_query(cq_id, text="Apertura riuscita!")
        deps.telegram.delete_message(chat_id, message_id)
        game = result.game
        assert game is not None
        player = game.get_player(user_id)
        assert player is not None
        deps.telegram.send_message(chat_id, format_hand(player))
        deps.telegram.send_message(
            chat_id,
            "Scegli un'azione:",
            reply_markup=build_play_keyboard(player.has_opened),
        )


# --- Group (for multi-group opening) ---


def _cb_group(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "grp:open:{current_mask}"
    # Save current group mask, start a new selection
    parts = data.split(":")
    parts[1]
    current_mask = parts[2]

    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None

    # New mask for next group selection
    new_mask = "0" * len(player.hand)
    # The confirm button will carry accumulated masks joined with +
    # We modify the action to carry the previous masks

    deps.telegram.answer_callback_query(cq_id, text="Gruppo salvato")

    # Build keyboard with open action, but the confirm callback
    # carries the accumulated masks
    kb = build_card_select_keyboard(player.hand, new_mask, "open")
    # Patch the confirm button to carry accumulated masks
    for row in kb["inline_keyboard"]:
        for btn in row:
            if btn["callback_data"].startswith("conf:open:"):
                # Replace with accumulated + new mask placeholder
                btn["callback_data"] = f"conf:open:{current_mask}+{new_mask}"
    deps.telegram.edit_message(
        chat_id,
        message_id,
        "Seleziona carte per il prossimo gruppo:",
        reply_markup=kb,
    )


# --- Discard ---


def _cb_discard(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "disc:{compact}"
    compact = data.split(":", 1)[1]
    card = Card.from_compact(compact)

    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None

    result = deps.engine.process_discard(game.game_id, user_id, card)
    if not result.success:
        deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
        return

    deps.telegram.answer_callback_query(cq_id)
    deps.telegram.delete_message(chat_id, message_id)

    game = result.game
    assert game is not None

    # Find group chat — use the lobby's chatId or current chat
    group_chat = _get_group_chat(game, deps) or chat_id

    # Check for round end / game end events
    has_closure = any(e.get("event") in ("closure", "game_end") for e in result.events)
    if has_closure:
        notify_round_end(game, group_chat, result.events, deps)
    else:
        notify_table_update(game, group_chat, deps)
        notify_turn_start(game, deps)


# --- Attach ---


def _cb_attach_card(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "att_card:{compact}"
    compact = data.split(":", 1)[1]
    card = Card.from_compact(compact)

    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None

    deps.telegram.answer_callback_query(cq_id)
    kb = build_attach_target_keyboard(card, game.table_games)
    deps.telegram.edit_message(
        chat_id,
        message_id,
        f"Dove attaccare {card.display()}?",
        reply_markup=kb,
    )


def _cb_attach_target(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    # data = "att_tg:{compact}:{tg_prefix}"
    parts = data.split(":")
    compact = parts[1]
    tg_prefix = parts[2]
    card = Card.from_compact(compact)

    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None

    # Find table game by prefix
    target_id = None
    for tg in game.table_games:
        if tg.game_id.startswith(tg_prefix):
            target_id = tg.game_id
            break

    if target_id is None:
        deps.telegram.answer_callback_query(cq_id, text="Gioco non trovato")
        return

    result = deps.engine.process_attach(game.game_id, user_id, card, target_id)
    if not result.success:
        deps.telegram.answer_callback_query(cq_id, text=result.error or "Errore")
        return

    deps.telegram.answer_callback_query(cq_id, text="Carta attaccata!")
    deps.telegram.delete_message(chat_id, message_id)

    game = result.game
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None
    deps.telegram.send_message(chat_id, format_hand(player))
    deps.telegram.send_message(
        chat_id,
        "Scegli un'azione:",
        reply_markup=build_play_keyboard(player.has_opened),
    )


# --- Cancel ---


def _cb_cancel(
    user_id: str,
    chat_id: str,
    message_id: int,
    data: str,
    cq_id: str,
    deps: Deps,
) -> None:
    game, err = _get_game(user_id, deps)
    if err:
        deps.telegram.answer_callback_query(cq_id, text=err)
        return
    assert game is not None
    player = game.get_player(user_id)
    assert player is not None

    deps.telegram.answer_callback_query(cq_id)
    deps.telegram.edit_message(
        chat_id,
        message_id,
        "Scegli un'azione:",
        reply_markup=build_play_keyboard(player.has_opened),
    )


# --- Helpers ---


def _get_game(user_id: str, deps: Deps):
    """Look up user's current game. Returns (game, error_msg)."""
    user = deps.user_repo.get_user(user_id)
    if user is None:
        return None, "Usa /start prima."
    game_id = user.get("currentGameId")
    if not game_id:
        return None, "Non sei in una partita."
    game = deps.engine.get_game(game_id)
    if game is None:
        return None, "Partita non trovata."
    return game, None


def _mask_to_cards(sorted_hand: list[Card], mask: str) -> list[Card]:
    """Convert bitmask to list of selected cards."""
    return [
        card for i, card in enumerate(sorted_hand) if i < len(mask) and mask[i] == "1"
    ]


def _get_group_chat(game, deps: Deps) -> str | None:
    """Get the group chat ID from the lobby."""
    if not game.lobby_id:
        return None
    lobby = deps.lobby_repo.get_lobby(game.lobby_id)
    if lobby is None:
        return None
    return lobby.get("chatId")


def _ensure_user(user_id: str, chat_id: str, deps: Deps) -> None:
    """Create user record if it doesn't exist."""
    user = deps.user_repo.get_user(user_id)
    if user is None:
        deps.user_repo.save_user(
            {
                "userId": user_id,
                "chatId": chat_id,
            }
        )
