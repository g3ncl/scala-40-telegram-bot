"""Command handlers for Telegram bot."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.bot.messages import (
    build_draw_keyboard,
    build_lobby_keyboard,
    build_main_menu_keyboard,
    format_hand,
    format_help,
    format_lobby,
    format_scores,
    format_table,
    format_welcome,
)

if TYPE_CHECKING:
    from src.bot.deps import Deps

logger = logging.getLogger("scala40.commands")


def handle_command(
    command: str,
    args: str,
    user_id: str,
    chat_id: str,
    deps: Deps,
    user_info: dict | None = None,
) -> None:
    """Dispatch a slash command."""
    handlers = {
        "/start": _cmd_start,
        "/help": _cmd_help,
        "/newlobby": _cmd_newlobby,
        "/join": _cmd_join,
        "/leave": _cmd_leave,
        "/ready": _cmd_ready,
        "/lobby": _cmd_lobby,
        "/startgame": _cmd_startgame,
        "/hand": _cmd_hand,
        "/table": _cmd_table,
        "/scores": _cmd_scores,
    }
    handler = handlers.get(command)
    if handler is None:
        deps.telegram.send_message(chat_id, "Comando sconosciuto. Usa /help.")
        return
    handler(args, user_id, chat_id, deps, user_info)


def _get_user_game(user_id: str, deps: Deps):
    """Look up the user's current game. Returns (game, error_msg)."""
    user = deps.user_repo.get_user(user_id)
    if user is None:
        return None, "Usa /start prima di giocare."
    game_id = user.get("currentGameId")
    if not game_id:
        return None, "Non sei in una partita."
    game = deps.engine.get_game(game_id)
    if game is None:
        return None, "Partita non trovata."
    return game, None


def _cmd_start(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    _ensure_user(user_id, chat_id, deps, user_info)
    deps.telegram.send_message(
        chat_id, format_welcome(), reply_markup=build_main_menu_keyboard()
    )


def _cmd_help(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    deps.telegram.send_message(
        chat_id, format_help(), reply_markup=build_main_menu_keyboard()
    )


def _cmd_newlobby(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    _ensure_user(user_id, chat_id, deps, user_info)
    result = deps.lobby_manager.create_lobby(user_id, chat_id)
    if not result.success:
        deps.telegram.send_message(chat_id, f"Errore: {result.error}")
        return
    lobby = result.lobby
    assert lobby is not None
    # Save lobby ref on user
    user = deps.user_repo.get_user(user_id)
    if user:
        user["currentLobbyId"] = lobby["lobbyId"]
        deps.user_repo.save_user(user)
    deps.telegram.send_message(
        chat_id,
        format_lobby(lobby, deps),
        reply_markup=build_lobby_keyboard(lobby, user_id),
    )


def _cmd_join(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    _ensure_user(user_id, chat_id, deps, user_info)
    code = args.strip().upper()
    if not code:
        deps.telegram.send_message(chat_id, "Uso: /join CODICE")
        return
    result = deps.lobby_manager.join_lobby(user_id, code)
    if not result.success:
        deps.telegram.send_message(chat_id, f"Errore: {result.error}")
        return
    lobby = result.lobby
    assert lobby is not None
    # Save lobby ref
    user = deps.user_repo.get_user(user_id)
    if user:
        user["currentLobbyId"] = lobby["lobbyId"]
        deps.user_repo.save_user(user)
    deps.telegram.send_message(
        chat_id,
        format_lobby(lobby, deps),
        reply_markup=build_lobby_keyboard(lobby, user_id),
    )


def _cmd_leave(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    user = deps.user_repo.get_user(user_id)
    if user is None or not user.get("currentLobbyId"):
        deps.telegram.send_message(chat_id, "Non sei in una lobby.")
        return
    result = deps.lobby_manager.leave_lobby(user_id, user["currentLobbyId"])
    if not result.success:
        deps.telegram.send_message(chat_id, f"Errore: {result.error}")
        return
    user["currentLobbyId"] = None
    deps.user_repo.save_user(user)
    deps.telegram.send_message(
        chat_id, "Hai lasciato la lobby.", reply_markup=build_main_menu_keyboard()
    )


def _cmd_ready(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    user = deps.user_repo.get_user(user_id)
    if user is None or not user.get("currentLobbyId"):
        deps.telegram.send_message(chat_id, "Non sei in una lobby.")
        return
    result = deps.lobby_manager.set_ready(user_id, user["currentLobbyId"])
    if not result.success:
        deps.telegram.send_message(chat_id, f"Errore: {result.error}")
        return
    lobby = result.lobby
    assert lobby is not None
    deps.telegram.send_message(
        chat_id,
        format_lobby(lobby, deps),
        reply_markup=build_lobby_keyboard(lobby, user_id),
    )


def _cmd_lobby(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    user = deps.user_repo.get_user(user_id)
    if user is None or not user.get("currentLobbyId"):
        deps.telegram.send_message(chat_id, "Non sei in una lobby.")
        return
    lobby = deps.lobby_manager.get_lobby(user["currentLobbyId"])
    if lobby is None:
        deps.telegram.send_message(chat_id, "Lobby non trovata.")
        return
    deps.telegram.send_message(
        chat_id,
        format_lobby(lobby, deps),
        reply_markup=build_lobby_keyboard(lobby, user_id),
    )


def _cmd_startgame(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    user = deps.user_repo.get_user(user_id)
    if user is None or not user.get("currentLobbyId"):
        deps.telegram.send_message(chat_id, "Non sei in una lobby.")
        return
    result = deps.lobby_manager.start_game(user_id, user["currentLobbyId"])
    if not result.success:
        deps.telegram.send_message(chat_id, f"Errore: {result.error}")
        return

    game_id = result.game_id
    assert game_id is not None
    lobby = result.lobby
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

    # Send table to group chat
    deps.telegram.send_message(chat_id, format_table(game, deps))

    # DM each player their hand
    for player in game.players:
        pu = deps.user_repo.get_user(player.user_id)
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


def _cmd_hand(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    game, err = _get_user_game(user_id, deps)
    if err:
        deps.telegram.send_message(chat_id, err)
        return
    assert game is not None
    player = game.get_player(user_id)
    if player is None:
        deps.telegram.send_message(chat_id, "Non sei in questa partita.")
        return
    deps.telegram.send_message(chat_id, format_hand(player))


def _cmd_table(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    game, err = _get_user_game(user_id, deps)
    if err:
        deps.telegram.send_message(chat_id, err)
        return
    assert game is not None
    deps.telegram.send_message(chat_id, format_table(game, deps))


def _cmd_scores(
    args: str, user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    game, err = _get_user_game(user_id, deps)
    if err:
        deps.telegram.send_message(chat_id, err)
        return
    assert game is not None
    deps.telegram.send_message(chat_id, format_scores(game, deps))


def _ensure_user(
    user_id: str, chat_id: str, deps: Deps, user_info: dict | None = None
) -> None:
    """Create or update user record with Telegram info."""
    user = deps.user_repo.get_user(user_id)
    if user is None:
        user = {"userId": user_id, "chatId": chat_id}

    if user_info:
        user["username"] = user_info.get("username")
        user["first_name"] = user_info.get("first_name")
        user["last_name"] = user_info.get("last_name")

    deps.user_repo.save_user(user)
