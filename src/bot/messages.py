"""Message formatting and keyboard builders for Telegram."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.game.models import Card, GameState, PlayerState, TableGame
from src.game.validator import can_attach
from src.utils.constants import PHASE_DISCARD, PHASE_DRAW, PHASE_PLAY

if TYPE_CHECKING:
    from src.bot.deps import Deps

# --- Helpers ---


def _get_display_name(user_id: str, deps: Deps | None = None) -> str:
    """Get display name: @username > First Last > user_id."""
    if deps is None:
        return user_id

    user = deps.user_repo.get_user(user_id)
    if not user:
        return user_id

    if user.get("username"):
        return f"@{user['username']}"

    first = user.get("first_name", "")
    last = user.get("last_name", "")
    full = f"{first} {last}".strip()
    if full:
        return full

    return user_id


# --- Text formatters ---


def format_welcome() -> str:
    return (
        "<b>Scala 40 Bot</b>\n\n"
        "Gioca a Scala 40 su Telegram!\n\n"
        "<b>Comandi:</b>\n"
        "/newlobby - Crea una lobby\n"
        "/join &lt;CODICE&gt; - Entra in una lobby\n"
        "/ready - Segna pronto\n"
        "/startgame - Avvia la partita (host)\n"
        "/hand - Mostra le tue carte\n"
        "/table - Mostra il tavolo\n"
        "/scores - Mostra i punteggi\n"
        "/help - Regole e comandi"
    )


def format_help() -> str:
    return (
        "<b>Regole Scala 40</b>\n\n"
        "Si gioca con 2 mazzi francesi (108 carte).\n"
        "Ogni giocatore riceve 13 carte.\n\n"
        "<b>Turno:</b> Pesca - Gioca - Scarta\n\n"
        "<b>Apertura:</b> Cala giochi per almeno 40 punti.\n"
        "<b>Sequenza:</b> 3+ carte consecutive stesso seme.\n"
        "<b>Combinazione:</b> 3-4 carte stesso valore, semi diversi.\n"
        "<b>Chiusura:</b> Scarta l'ultima carta (dopo il primo giro).\n\n"
        "<b>Punteggi:</b> A=11, Figure=10, Jolly=25, "
        "altre=valore.\n"
        "Eliminazione a 101 punti. Ultimo in gioco vince."
    )


def format_hand(player: PlayerState) -> str:
    if not player.hand:
        return "<b>La tua mano</b>: (vuota)"
    sorted_cards = sorted(player.hand, key=lambda c: (c.suit, c.rank))
    lines = [f"<b>La tua mano</b> ({len(sorted_cards)} carte):"]
    for i, card in enumerate(sorted_cards, 1):
        lines.append(f"  {i}. {card.display()}")
    return "\n".join(lines)


def format_table(game: GameState, deps: Deps | None = None) -> str:
    phase_names = {
        PHASE_DRAW: "Pesca",
        PHASE_PLAY: "Gioco",
        PHASE_DISCARD: "Scarto",
    }
    phase = phase_names.get(game.turn_phase, game.turn_phase)

    current_name = _get_display_name(game.current_turn_user_id, deps)
    lines = [
        f"<b>SCALA 40</b> — Smazzata #{game.smazzata_number}\n",
        f"Turno di: <b>{current_name}</b> (fase: {phase})",
    ]

    if game.discard_pile:
        lines.append(f"Pozzo: {game.discard_pile[-1].display()}")
    else:
        lines.append("Pozzo: (vuoto)")
    lines.append(f"Tallone: {len(game.deck)} carte\n")

    if game.table_games:
        lines.append("<b>Giochi sul tavolo:</b>")
        for tg in game.table_games:
            cards_str = " ".join(c.display() for c in tg.cards)
            owner_name = _get_display_name(tg.owner, deps)
            lines.append(f"  {owner_name}: [{cards_str}]")
        lines.append("")

    lines.append("<b>Carte in mano:</b>")
    for p in game.players:
        p_name = _get_display_name(p.user_id, deps)
        if p.is_eliminated:
            lines.append(f"  {p_name}: ELIMINATO")
            continue
        marker = " &lt;&lt;" if p.user_id == game.current_turn_user_id else ""
        opened = "" if p.has_opened else " (chiuso)"
        lines.append(f"  {p_name}: {len(p.hand)} carte{opened}{marker}")

    lines.append("")
    score_parts = []
    for uid, s in game.scores.items():
        u_name = _get_display_name(uid, deps)
        score_parts.append(f"{u_name}: {s}")
    lines.append(f"Punteggi: {' | '.join(score_parts)}")
    return "\n".join(lines)


def format_lobby(lobby: dict, deps: Deps | None = None) -> str:
    code = lobby.get("code", "???")
    lines = [f"<b>Lobby #{code}</b>\n"]
    lines.append("Giocatori:")
    for p in lobby.get("players", []):
        check = "+" if p.get("ready") else "-"
        uid = p.get("userId", "?")
        u_name = _get_display_name(uid, deps)
        status = "pronto" if p.get("ready") else "non pronto"
        lines.append(f"  {check} {u_name} ({status})")
    return "\n".join(lines)


def format_scores(game: GameState, deps: Deps | None = None) -> str:
    lines = ["<b>Punteggi:</b>"]
    sorted_scores = sorted(game.scores.items(), key=lambda x: x[1])
    for uid, score in sorted_scores:
        player = game.get_player(uid)
        u_name = _get_display_name(uid, deps)
        status = ""
        if player and player.is_eliminated:
            status = " (eliminato)"
        lines.append(f"  {u_name}: {score}{status}")
    return "\n".join(lines)


# --- Keyboard builders ---


def build_main_menu_keyboard() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "🆕 Crea Partita", "callback_data": "main:new"},
                {"text": "❓ Aiuto", "callback_data": "main:help"},
            ],
            # Join is complex via buttons without a conversation handler,
            # but we can add a button that explains how to join.
            # {"text": "🔑 Entra in partita", "callback_data": "main:join_info"},
        ]
    }


def build_lobby_keyboard(lobby: dict, user_id: str) -> dict:
    host_id = lobby.get("hostUserId")
    players = lobby.get("players", [])
    is_host = user_id == host_id

    me = next((p for p in players if p["userId"] == user_id), None)
    is_ready = me.get("ready", False) if me else False

    ready_text = "❌ Non pronto" if is_ready else "✅ Pronto"
    ready_cb = "lobby:ready"

    rows = [
        [{"text": ready_text, "callback_data": ready_cb}],
    ]

    if is_host:
        # Start button enabled only if everyone ready and min players
        all_ready = all(p.get("ready") for p in players)
        count = len(players)
        if count >= 2 and all_ready:
            rows.append([{"text": "🚀 Avvia Partita", "callback_data": "lobby:start"}])

    rows.append([{"text": "🚪 Esci", "callback_data": "lobby:leave"}])
    rows.append([{"text": "🔄 Aggiorna", "callback_data": "lobby:refresh"}])

    return {"inline_keyboard": rows}


def build_draw_keyboard(has_opened: bool = False) -> dict:
    buttons = [{"text": "Pesca dal mazzo", "callback_data": "draw:deck"}]
    if has_opened:
        buttons.append({"text": "Prendi dal pozzo", "callback_data": "draw:discard"})
    return {"inline_keyboard": [buttons]}


def build_play_keyboard(has_opened: bool = True) -> dict:
    rows = []
    if not has_opened:
        rows.append(
            [
                {"text": "Apri", "callback_data": "menu:open"},
                {"text": "Scarta", "callback_data": "menu:discard"},
            ]
        )
    else:
        rows.append(
            [
                {"text": "Cala gioco", "callback_data": "menu:play"},
                {"text": "Attacca", "callback_data": "menu:attach"},
            ]
        )
        rows.append(
            [
                {"text": "Scarta", "callback_data": "menu:discard"},
            ]
        )
    return {"inline_keyboard": rows}


def _sort_hand(hand: list[Card]) -> list[Card]:
    return sorted(hand, key=lambda c: (c.suit, c.rank))


def build_card_select_keyboard(cards: list[Card], mask: str, action: str) -> dict:
    """Card grid with checkmarks. Each button toggles a bit."""
    sorted_cards = _sort_hand(cards)
    rows: list[list[dict]] = []
    row: list[dict] = []
    for i, card in enumerate(sorted_cards):
        selected = mask[i] == "1" if i < len(mask) else False
        label = f"{'[x] ' if selected else ''}{card.display()}"
        new_mask = list(mask.ljust(len(sorted_cards), "0"))
        new_mask[i] = "0" if selected else "1"
        cb = f"card:{i}:{action}:{''.join(new_mask)}"
        row.append({"text": label, "callback_data": cb})
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    # Confirm + Cancel buttons
    confirm_row = [
        {"text": "Conferma", "callback_data": f"conf:{action}:{mask}"},
    ]
    if action == "open":
        confirm_row.append(
            {"text": "Gruppo +", "callback_data": f"grp:{action}:{mask}"},
        )
    confirm_row.append(
        {"text": "Annulla", "callback_data": "cancel"},
    )
    rows.append(confirm_row)
    return {"inline_keyboard": rows}


def build_discard_keyboard(cards: list[Card]) -> dict:
    """One button per card for discard selection."""
    sorted_cards = _sort_hand(cards)
    rows: list[list[dict]] = []
    row: list[dict] = []
    for card in sorted_cards:
        cb = f"disc:{card.compact()}"
        row.append({"text": card.display(), "callback_data": cb})
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "Annulla", "callback_data": "cancel"}])
    return {"inline_keyboard": rows}


def build_attach_card_keyboard(cards: list[Card]) -> dict:
    """Select which card to attach."""
    sorted_cards = _sort_hand(cards)
    rows: list[list[dict]] = []
    row: list[dict] = []
    for card in sorted_cards:
        cb = f"att_card:{card.compact()}"
        row.append({"text": card.display(), "callback_data": cb})
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([{"text": "Annulla", "callback_data": "cancel"}])
    return {"inline_keyboard": rows}


def build_attach_target_keyboard(
    card: Card, table_games: list[TableGame], deps: Deps | None = None
) -> dict:
    """Show valid table games to attach to."""
    rows: list[list[dict]] = []
    for tg in table_games:
        if not can_attach(card, tg).valid:
            continue
        cards_str = " ".join(c.display() for c in tg.cards[:5])
        if len(tg.cards) > 5:
            cards_str += "..."
        owner_name = _get_display_name(tg.owner, deps)
        label = f"{owner_name}: {cards_str}"
        cb = f"att_tg:{card.compact()}:{tg.game_id[:6]}"
        rows.append([{"text": label, "callback_data": cb}])
    rows.append([{"text": "Annulla", "callback_data": "cancel"}])
    return {"inline_keyboard": rows}
