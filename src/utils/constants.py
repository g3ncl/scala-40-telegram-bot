"""Game constants for Scala 40."""

# Suits (compact encoding)
HEARTS = "h"
DIAMONDS = "d"
CLUBS = "c"
SPADES = "s"
JOKER_SUIT = "j"
SUITS = [HEARTS, DIAMONDS, CLUBS, SPADES]

# Suit display symbols
SUIT_SYMBOLS = {
    HEARTS: "♥",
    DIAMONDS: "♦",
    CLUBS: "♣",
    SPADES: "♠",
    JOKER_SUIT: "🃏",
}

# Ranks
JOKER_RANK = 0
ACE = 1
JACK = 11
QUEEN = 12
KING = 13
RANKS = list(range(1, 14))  # 1-13

# Rank display names
RANK_NAMES = {
    1: "A",
    2: "2",
    3: "3",
    4: "4",
    5: "5",
    6: "6",
    7: "7",
    8: "8",
    9: "9",
    10: "10",
    11: "J",
    12: "Q",
    13: "K",
}

# Game parameters
CARDS_PER_PLAYER = 13
NUM_DECKS = 2
JOKERS_PER_DECK = 2
TOTAL_CARDS = 108  # 52*2 + 4
OPENING_THRESHOLD = 40
DEFAULT_ELIMINATION_SCORE = 101
MAX_PLAYERS = 4
MIN_PLAYERS = 2

# Point values for scoring (cards in hand at round end)
# Joker=25, Ace=11, Face cards=10, others=face value
JOKER_POINTS = 25
ACE_POINTS_HIGH = 11
ACE_POINTS_LOW = 1
FACE_POINTS = 10

# Turn phases
PHASE_DRAW = "draw"
PHASE_PLAY = "play"
PHASE_DISCARD = "discard"

# Game statuses
STATUS_WAITING = "waiting"
STATUS_STARTING = "starting"
STATUS_IN_GAME = "in_game"
STATUS_PLAYING = "playing"
STATUS_ROUND_END = "round_end"
STATUS_FINISHED = "finished"
STATUS_CLOSED = "closed"

# Table game types
GAME_TYPE_SEQUENCE = "sequence"
GAME_TYPE_COMBINATION = "combination"

# Lobby
LOBBY_CODE_LENGTH = 6
