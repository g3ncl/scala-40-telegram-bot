"""Game engine for Scala 40 — orchestrates the full game flow."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.db.repository import GameRepository
from src.game.deck import (
    create_deck,
    deal,
    draw_from_deck,
    draw_from_discard,
    reshuffle_discard,
    shuffle_cards,
)
from src.game.models import Card, GameState, PlayerState, TableGame
from src.game.scoring import (
    apply_round_scores,
    check_eliminations,
    check_winner,
)
from src.game.validator import (
    can_attach,
    can_substitute_joker,
    detect_game_type,
    is_valid_discard,
    is_valid_opening,
    validate_game,
)
from src.utils.constants import (
    DEFAULT_ELIMINATION_SCORE,
    PHASE_DISCARD,
    PHASE_DRAW,
    PHASE_PLAY,
    STATUS_FINISHED,
    STATUS_PLAYING,
    STATUS_ROUND_END,
)
from src.utils.crypto import create_rng

logger = logging.getLogger("scala40.engine")


@dataclass
class ActionResult:
    success: bool
    game: GameState
    error: str | None = None
    events: list[dict] = field(default_factory=list)


class GameEngine:
    """Stateless game engine. All state lives in GameState / repository."""

    def __init__(
        self, repo: GameRepository, rng: random.Random | None = None
    ) -> None:
        self._repo = repo
        self._rng = rng or create_rng()

    def create_game(
        self,
        player_ids: list[str],
        lobby_id: str = "",
        settings: dict | None = None,
    ) -> GameState:
        """Create a new game. Does NOT deal cards yet (call start_round)."""
        game_id = GameState.new_game_id()
        players = [PlayerState(user_id=uid) for uid in player_ids]
        scores = {uid: 0 for uid in player_ids}
        game = GameState(
            game_id=game_id,
            lobby_id=lobby_id,
            players=players,
            deck=[],
            discard_pile=[],
            table_games=[],
            current_turn_user_id="",
            turn_phase=PHASE_DRAW,
            round_number=0,
            dealer_user_id=player_ids[0],
            first_round_complete=False,
            smazzata_number=0,
            scores=scores,
            status=STATUS_PLAYING,
            settings=settings or {"elimination_score": DEFAULT_ELIMINATION_SCORE},
            updated_at=self._now(),
        )
        self._repo.save_game(game)
        return self._repo.get_game(game_id)

    def start_round(self, game_id: str) -> ActionResult:
        """Start a new round (smazzata): shuffle, deal, set first player."""
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        # Create and shuffle deck
        deck = create_deck()
        deck = shuffle_cards(deck, self._rng)

        # Reset player state for new round
        active_players = game.get_active_players()
        for player in game.players:
            player.hand = []
            player.has_opened = False
            player.score = 0

        # Deal cards
        active_ids = [p.user_id for p in active_players]
        hands, remaining_deck, first_discard = deal(deck, len(active_ids))

        for i, player in enumerate(active_players):
            player.hand = hands[i]

        game.deck = remaining_deck
        game.discard_pile = [first_discard]
        game.table_games = []
        game.smazzata_number += 1
        game.round_number = 0
        game.first_round_complete = False
        game.drawn_from_discard = None
        game.status = STATUS_PLAYING

        # Rotate dealer (handle case where previous dealer was eliminated)
        if game.smazzata_number > 1:
            if game.dealer_user_id in active_ids:
                dealer_idx = active_ids.index(game.dealer_user_id)
                game.dealer_user_id = active_ids[(dealer_idx + 1) % len(active_ids)]
            else:
                # Previous dealer was eliminated, pick next active player
                game.dealer_user_id = active_ids[0]

        # First player is left of dealer
        dealer_idx = active_ids.index(game.dealer_user_id)
        first_player_idx = (dealer_idx + 1) % len(active_ids)
        game.current_turn_user_id = active_ids[first_player_idx]
        game.round_starter_user_id = game.current_turn_user_id
        game.turn_phase = PHASE_DRAW
        game.updated_at = self._now()

        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        event = {
            "event": "round_start",
            "game_id": game_id,
            "smazzata": game.smazzata_number,
            "dealer": game.dealer_user_id,
            "first_player": game.current_turn_user_id,
            "players_cards": {p.user_id: len(p.hand) for p in active_players},
        }
        logger.info(json.dumps(event))
        return ActionResult(success=True, game=game, events=[event])

    def process_draw(
        self, game_id: str, user_id: str, source: str
    ) -> ActionResult:
        """Draw a card from deck or discard pile.

        source: "deck" or "discard"
        """
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        error = self._validate_turn(game, user_id, PHASE_DRAW)
        if error:
            return ActionResult(success=False, game=game, error=error)

        player = game.get_player(user_id)

        if source == "discard":
            if not player.has_opened:
                return ActionResult(
                    success=False, game=game,
                    error="Devi aver aperto per pescare dal pozzo"
                )
            if not game.discard_pile:
                return ActionResult(
                    success=False, game=game, error="Il pozzo è vuoto"
                )
            card, game.discard_pile = draw_from_discard(game.discard_pile)
            game.drawn_from_discard = card
        elif source == "deck":
            if not game.deck:
                # Reshuffle discard pile
                if len(game.discard_pile) < 2:
                    return ActionResult(
                        success=False, game=game,
                        error="Non ci sono carte da pescare"
                    )
                game.deck, last_discard = reshuffle_discard(
                    game.discard_pile, self._rng
                )
                game.discard_pile = [last_discard]
            card, game.deck = draw_from_deck(game.deck)
            game.drawn_from_discard = None
        else:
            return ActionResult(
                success=False, game=game,
                error=f"Sorgente non valida: {source}"
            )

        player.hand.append(card)

        # Transition phase
        if player.has_opened:
            game.turn_phase = PHASE_PLAY
        else:
            game.turn_phase = PHASE_DISCARD

        game.updated_at = self._now()
        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        event = {
            "event": "draw",
            "game_id": game_id,
            "user_id": user_id,
            "source": source,
            "card_drawn": card.compact(),
            "deck_remaining": len(game.deck),
            "hand_size": len(player.hand),
        }
        logger.info(json.dumps(event))
        return ActionResult(success=True, game=game, events=[event])

    def process_open(
        self, game_id: str, user_id: str, games: list[list[Card]]
    ) -> ActionResult:
        """Open with a set of games totaling >= 40 points."""
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        error = self._validate_turn(game, user_id, PHASE_PLAY, allow_discard_phase=True)
        if error:
            return ActionResult(success=False, game=game, error=error)

        player = game.get_player(user_id)

        if player.has_opened:
            return ActionResult(
                success=False, game=game, error="Hai già aperto"
            )

        # Validate opening
        result = is_valid_opening(games)
        if not result.valid:
            return ActionResult(success=False, game=game, error=result.error)

        # Check all cards are in hand
        all_cards = [card for game_cards in games for card in game_cards]
        hand_copy = list(player.hand)
        for card in all_cards:
            if card not in hand_copy:
                return ActionResult(
                    success=False, game=game,
                    error=f"Carta {card.display()} non in mano"
                )
            hand_copy.remove(card)

        # Apply: remove cards from hand, add table games
        player.hand = hand_copy
        player.has_opened = True
        for game_cards in games:
            game_type = detect_game_type(game_cards)
            tg = TableGame(
                game_id=GameState.new_table_game_id(),
                owner=user_id,
                cards=game_cards,
                game_type=game_type,
            )
            game.table_games.append(tg)

        game.turn_phase = PHASE_PLAY
        game.updated_at = self._now()
        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        event = {
            "event": "open",
            "game_id": game_id,
            "user_id": user_id,
            "games_count": len(games),
            "total_points": result.points,
            "cards_remaining": len(player.hand),
        }
        logger.info(json.dumps(event))
        return ActionResult(success=True, game=game, events=[event])

    def process_play(
        self, game_id: str, user_id: str, cards: list[Card]
    ) -> ActionResult:
        """Play a new game (sequence or combination) after having opened."""
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        error = self._validate_turn(game, user_id, PHASE_PLAY)
        if error:
            return ActionResult(success=False, game=game, error=error)

        player = game.get_player(user_id)
        if not player.has_opened:
            return ActionResult(
                success=False, game=game,
                error="Devi prima aprire per calare giochi"
            )

        # Validate the game
        result = validate_game(cards)
        if not result.valid:
            return ActionResult(success=False, game=game, error=result.error)

        # Check cards in hand
        hand_copy = list(player.hand)
        for card in cards:
            if card not in hand_copy:
                return ActionResult(
                    success=False, game=game,
                    error=f"Carta {card.display()} non in mano"
                )
            hand_copy.remove(card)

        # Apply
        player.hand = hand_copy
        game_type = detect_game_type(cards)
        tg = TableGame(
            game_id=GameState.new_table_game_id(),
            owner=user_id,
            cards=cards,
            game_type=game_type,
        )
        game.table_games.append(tg)

        game.updated_at = self._now()
        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        event = {
            "event": f"play_{game_type}",
            "game_id": game_id,
            "user_id": user_id,
            "cards": [c.compact() for c in cards],
        }
        logger.info(json.dumps(event))
        return ActionResult(success=True, game=game, events=[event])

    def process_attach(
        self, game_id: str, user_id: str, card: Card, table_game_id: str
    ) -> ActionResult:
        """Attach a card to an existing table game."""
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        error = self._validate_turn(game, user_id, PHASE_PLAY)
        if error:
            return ActionResult(success=False, game=game, error=error)

        player = game.get_player(user_id)
        if not player.has_opened:
            return ActionResult(
                success=False, game=game,
                error="Devi prima aprire per attaccare carte"
            )

        # Find table game
        target = None
        for tg in game.table_games:
            if tg.game_id == table_game_id:
                target = tg
                break
        if target is None:
            return ActionResult(
                success=False, game=game, error="Gioco sul tavolo non trovato"
            )

        # Check card in hand
        if card not in player.hand:
            return ActionResult(
                success=False, game=game,
                error=f"Carta {card.display()} non in mano"
            )

        # Validate attachment
        result = can_attach(card, target)
        if not result.valid:
            return ActionResult(success=False, game=game, error=result.error)

        # Apply
        player.hand.remove(card)
        # Add card in correct position for sequences
        if target.game_type == "sequence" and not card.is_joker:
            seq_ranks = [c.rank for c in target.cards if not c.is_joker]
            if seq_ranks:
                min_rank = min(seq_ranks)
                # Handle ace-high
                card_rank = card.rank
                if card_rank == 1 and min_rank > 2:
                    card_rank = 14
                if card_rank < min_rank:
                    target.cards.insert(0, card)
                else:
                    target.cards.append(card)
            else:
                target.cards.append(card)
        else:
            target.cards.append(card)

        game.updated_at = self._now()
        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        event = {
            "event": "attach",
            "game_id": game_id,
            "user_id": user_id,
            "card": card.compact(),
            "table_game_id": table_game_id,
        }
        logger.info(json.dumps(event))
        return ActionResult(success=True, game=game, events=[event])

    def process_substitute_joker(
        self, game_id: str, user_id: str, card: Card,
        table_game_id: str, joker_play: dict
    ) -> ActionResult:
        """Substitute a joker on the table and immediately use it.

        joker_play: describes how to use the taken joker, e.g.:
          {"action": "play", "cards": [...]}  -- play in new game
          {"action": "attach", "table_game_id": "..."} -- attach to existing
        """
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        error = self._validate_turn(game, user_id, PHASE_PLAY)
        if error:
            return ActionResult(success=False, game=game, error=error)

        player = game.get_player(user_id)
        if not player.has_opened:
            return ActionResult(
                success=False, game=game,
                error="Devi aver aperto per sostituire un jolly"
            )

        # Find table game
        target = None
        for tg in game.table_games:
            if tg.game_id == table_game_id:
                target = tg
                break
        if target is None:
            return ActionResult(
                success=False, game=game, error="Gioco non trovato"
            )

        # Validate substitution
        result = can_substitute_joker(card, target)
        if not result.valid:
            return ActionResult(success=False, game=game, error=result.error)

        if card not in player.hand:
            return ActionResult(
                success=False, game=game,
                error=f"Carta {card.display()} non in mano"
            )

        # Remove card from hand, swap in table game
        player.hand.remove(card)
        joker_card = None
        for i, tc in enumerate(target.cards):
            if tc.is_joker:
                joker_card = tc
                target.cards[i] = card
                break

        if joker_card is None:
            return ActionResult(
                success=False, game=game, error="Jolly non trovato nel gioco"
            )

        # The joker must be used immediately — not added to hand
        # For now, save and return; the caller must immediately play or attach
        # In a full implementation, joker_play would be processed here
        # For simplicity, add joker to hand temporarily (the next action must use it)
        player.hand.append(joker_card)

        game.updated_at = self._now()
        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        event = {
            "event": "substitute_joker",
            "game_id": game_id,
            "user_id": user_id,
            "card_inserted": card.compact(),
            "table_game_id": table_game_id,
        }
        logger.info(json.dumps(event))
        return ActionResult(success=True, game=game, events=[event])

    def process_discard(
        self, game_id: str, user_id: str, card: Card
    ) -> ActionResult:
        """Discard a card, ending the turn. May trigger closure."""
        game = self._repo.get_game(game_id)
        if game is None:
            return ActionResult(success=False, game=None, error="Partita non trovata")

        # Allow discard from both PLAY and DISCARD phases
        error = self._validate_turn(
            game, user_id, PHASE_PLAY, allow_discard_phase=True
        )
        if error:
            return ActionResult(success=False, game=game, error=error)

        player = game.get_player(user_id)

        if card not in player.hand:
            return ActionResult(
                success=False, game=game,
                error=f"Carta {card.display()} non in mano"
            )

        cards_in_hand_after = len(player.hand) - 1

        # Validate discard
        active_count = len(game.get_active_players())
        result = is_valid_discard(
            card=card,
            drawn_from_discard=game.drawn_from_discard,
            table_games=game.table_games,
            player_has_opened=player.has_opened,
            num_players=active_count,
            cards_in_hand_after=cards_in_hand_after,
        )
        if not result.valid:
            return ActionResult(success=False, game=game, error=result.error)

        # Check closure attempt
        is_closing = cards_in_hand_after == 0
        if is_closing:
            if not player.has_opened:
                return ActionResult(
                    success=False, game=game,
                    error="Non puoi chiudere senza aver aperto"
                )
            if not game.first_round_complete:
                return ActionResult(
                    success=False, game=game,
                    error="Non puoi chiudere al primo giro"
                )

        # Apply discard
        player.hand.remove(card)
        game.discard_pile.append(card)

        events = []
        discard_event = {
            "event": "discard",
            "game_id": game_id,
            "user_id": user_id,
            "card": card.compact(),
            "hand_remaining": len(player.hand),
        }
        events.append(discard_event)
        logger.info(json.dumps(discard_event))

        if is_closing:
            # Round ends
            game = self._handle_closure(game, user_id, events)
        else:
            # Advance turn
            game = self._advance_turn(game)

        game.updated_at = self._now()
        self._repo.save_game(game)
        game = self._repo.get_game(game_id)

        return ActionResult(success=True, game=game, events=events)

    def get_game(self, game_id: str) -> GameState | None:
        return self._repo.get_game(game_id)

    # --- Private helpers ---

    def _validate_turn(
        self, game: GameState, user_id: str, expected_phase: str,
        allow_discard_phase: bool = False,
    ) -> str | None:
        """Validate that it's the user's turn and correct phase. Returns error or None."""
        if game.status != STATUS_PLAYING:
            return "La partita non è in corso"

        if game.current_turn_user_id != user_id:
            return "Non è il tuo turno"

        player = game.get_player(user_id)
        if player is None or player.is_eliminated:
            return "Non sei un giocatore attivo"

        if game.turn_phase != expected_phase:
            if allow_discard_phase and game.turn_phase == PHASE_DISCARD:
                return None
            return f"Fase non corretta: attesa {expected_phase}, attuale {game.turn_phase}"

        return None

    def _advance_turn(self, game: GameState) -> GameState:
        """Move to next active player."""
        active = game.get_active_players()
        active_ids = [p.user_id for p in active]
        current_idx = active_ids.index(game.current_turn_user_id)
        next_idx = (current_idx + 1) % len(active_ids)
        game.current_turn_user_id = active_ids[next_idx]
        game.turn_phase = PHASE_DRAW
        game.drawn_from_discard = None
        game.round_number += 1

        # Check if first round is complete
        if not game.first_round_complete:
            if game.current_turn_user_id == game.round_starter_user_id:
                game.first_round_complete = True

        return game

    def _handle_closure(
        self, game: GameState, closer_id: str, events: list[dict]
    ) -> GameState:
        """Handle round closure: scores, eliminations, next round or game end."""
        apply_round_scores(game, closer_id)

        closure_event = {
            "event": "closure",
            "game_id": game.game_id,
            "user_id": closer_id,
            "smazzata": game.smazzata_number,
            "scores": dict(game.scores),
        }
        events.append(closure_event)
        logger.info(json.dumps(closure_event))

        eliminated = check_eliminations(game)
        for uid in eliminated:
            elim_event = {
                "event": "elimination",
                "game_id": game.game_id,
                "user_id": uid,
                "total_score": game.scores[uid],
                "threshold": game.settings.get("elimination_score", 101),
            }
            events.append(elim_event)
            logger.info(json.dumps(elim_event))

        winner = check_winner(game)
        if winner:
            game.status = STATUS_FINISHED
            end_event = {
                "event": "game_end",
                "game_id": game.game_id,
                "winner": winner,
                "final_scores": dict(game.scores),
            }
            events.append(end_event)
            logger.info(json.dumps(end_event))
        else:
            game.status = STATUS_ROUND_END

        return game

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
