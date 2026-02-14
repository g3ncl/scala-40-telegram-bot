"""Data models for Scala 40 game state."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from src.utils.constants import (
    ACE,
    ACE_POINTS_HIGH,
    ACE_POINTS_LOW,
    FACE_POINTS,
    JACK,
    JOKER_POINTS,
    JOKER_RANK,
    JOKER_SUIT,
    KING,
    PHASE_DRAW,
    QUEEN,
    RANK_NAMES,
    STATUS_PLAYING,
    SUIT_SYMBOLS,
)


@dataclass(frozen=True)
class Card:
    """A single playing card.

    Compact encoding examples: "8h" = 8 of hearts, "Ks" = King of spades,
    "J0" = Joker from deck 0, "J1" = Joker from deck 1.
    """

    suit: str  # "h", "d", "c", "s", "j"
    rank: int  # 0=Joker, 1=Ace, 2-10, 11=J, 12=Q, 13=K
    deck: int  # 0 or 1

    @property
    def is_joker(self) -> bool:
        return self.suit == JOKER_SUIT and self.rank == JOKER_RANK

    def points(self, low_ace: bool = False) -> int:
        """Point value of this card."""
        if self.is_joker:
            return JOKER_POINTS
        if self.rank == ACE:
            return ACE_POINTS_LOW if low_ace else ACE_POINTS_HIGH
        if self.rank >= JACK:
            return FACE_POINTS
        return self.rank

    def compact(self) -> str:
        """Encode to compact string."""
        if self.is_joker:
            return f"J{self.deck}"
        rank_str = RANK_NAMES[self.rank]
        return f"{rank_str}{self.suit}{self.deck}"

    @classmethod
    def from_compact(cls, code: str) -> Card:
        """Decode from compact string.

        Formats:
        - "J0", "J1" -> Joker
        - "8h0", "Ks1", "Ad0", "10c0" -> suited card with deck index
        - "8h", "Ks", "Ad", "10c" -> suited card, defaults to deck 0
        """
        if code.startswith("J") and len(code) == 2 and code[1].isdigit():
            return cls(suit=JOKER_SUIT, rank=JOKER_RANK, deck=int(code[1]))

        # Parse deck index (last char if digit after suit)
        deck = 0
        remaining = code
        if len(remaining) >= 3 and remaining[-1].isdigit() and remaining[-2].isalpha():
            deck = int(remaining[-1])
            remaining = remaining[:-1]

        # Parse suit (last char)
        suit = remaining[-1]
        rank_str = remaining[:-1]

        # Parse rank
        rank_map = {v: k for k, v in RANK_NAMES.items()}
        rank = rank_map[rank_str]

        return cls(suit=suit, rank=rank, deck=deck)

    def display(self) -> str:
        """Unicode display string."""
        if self.is_joker:
            return "🃏"
        symbol = SUIT_SYMBOLS[self.suit]
        return f"{RANK_NAMES[self.rank]}{symbol}"

    def to_dict(self) -> dict:
        """Serialize for storage."""
        return {"suit": self.suit, "rank": self.rank, "deck": self.deck}

    @classmethod
    def from_dict(cls, d: dict) -> Card:
        """Deserialize from storage."""
        return cls(suit=d["suit"], rank=d["rank"], deck=d["deck"])


@dataclass
class PlayerState:
    """State of a single player within a game."""

    user_id: str
    hand: list[Card] = field(default_factory=list)
    has_opened: bool = False
    is_eliminated: bool = False
    score: int = 0

    def to_dict(self) -> dict:
        return {
            "userId": self.user_id,
            "hand": [c.to_dict() for c in self.hand],
            "hasOpened": self.has_opened,
            "isEliminated": self.is_eliminated,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PlayerState:
        return cls(
            user_id=d["userId"],
            hand=[Card.from_dict(c) for c in d.get("hand", [])],
            has_opened=d.get("hasOpened", False),
            is_eliminated=d.get("isEliminated", False),
            score=d.get("score", 0),
        )


@dataclass
class TableGame:
    """A game (sequence or combination) laid on the table."""

    game_id: str
    owner: str
    cards: list[Card]
    game_type: str  # "sequence" or "combination"

    def to_dict(self) -> dict:
        return {
            "gameId": self.game_id,
            "owner": self.owner,
            "cards": [c.to_dict() for c in self.cards],
            "type": self.game_type,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TableGame:
        return cls(
            game_id=d["gameId"],
            owner=d["owner"],
            cards=[Card.from_dict(c) for c in d["cards"]],
            game_type=d["type"],
        )


@dataclass
class GameState:
    """Complete state of a Scala 40 game (maps to one DynamoDB row)."""

    game_id: str
    lobby_id: str
    players: list[PlayerState]
    deck: list[Card]
    discard_pile: list[Card]
    table_games: list[TableGame]
    current_turn_user_id: str
    turn_phase: str
    round_number: int
    dealer_user_id: str
    first_round_complete: bool
    smazzata_number: int
    scores: dict[str, int]
    status: str
    settings: dict
    updated_at: str
    drawn_from_discard: Card | None = None
    version: int = 1
    # Track which player started the current round (for first_round_complete detection)
    round_starter_user_id: str = ""

    def get_player(self, user_id: str) -> PlayerState | None:
        for p in self.players:
            if p.user_id == user_id:
                return p
        return None

    def get_active_players(self) -> list[PlayerState]:
        return [p for p in self.players if not p.is_eliminated]

    def to_dict(self) -> dict:
        return {
            "gameId": self.game_id,
            "lobbyId": self.lobby_id,
            "players": [p.to_dict() for p in self.players],
            "deck": [c.to_dict() for c in self.deck],
            "discardPile": [c.to_dict() for c in self.discard_pile],
            "tableGames": [tg.to_dict() for tg in self.table_games],
            "currentTurnUserId": self.current_turn_user_id,
            "turnPhase": self.turn_phase,
            "roundNumber": self.round_number,
            "dealerUserId": self.dealer_user_id,
            "firstRoundComplete": self.first_round_complete,
            "smazzataNumber": self.smazzata_number,
            "scores": self.scores,
            "status": self.status,
            "settings": self.settings,
            "updatedAt": self.updated_at,
            "drawnFromDiscard": self.drawn_from_discard.to_dict() if self.drawn_from_discard else None,
            "version": self.version,
            "roundStarterUserId": self.round_starter_user_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> GameState:
        drawn = d.get("drawnFromDiscard")
        return cls(
            game_id=d["gameId"],
            lobby_id=d["lobbyId"],
            players=[PlayerState.from_dict(p) for p in d["players"]],
            deck=[Card.from_dict(c) for c in d["deck"]],
            discard_pile=[Card.from_dict(c) for c in d["discardPile"]],
            table_games=[TableGame.from_dict(tg) for tg in d["tableGames"]],
            current_turn_user_id=d["currentTurnUserId"],
            turn_phase=d["turnPhase"],
            round_number=d["roundNumber"],
            dealer_user_id=d["dealerUserId"],
            first_round_complete=d["firstRoundComplete"],
            smazzata_number=d["smazzataNumber"],
            scores=d["scores"],
            status=d["status"],
            settings=d["settings"],
            updated_at=d["updatedAt"],
            drawn_from_discard=Card.from_dict(drawn) if drawn else None,
            version=d.get("version", 1),
            round_starter_user_id=d.get("roundStarterUserId", ""),
        )

    @staticmethod
    def new_game_id() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def new_table_game_id() -> str:
        return str(uuid.uuid4())[:8]
