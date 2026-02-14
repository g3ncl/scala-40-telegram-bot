# Scala 40 Telegram Bot

A multiplayer Scala 40 card game bot for Telegram, built on AWS serverless infrastructure.

Scala 40 is an Italian rummy-style card game played with two French decks (108 cards total, including 4 jokers). Players draw and discard cards, forming sequences (consecutive same-suit cards) and combinations (same-rank cards of different suits). The first player to empty their hand closes the round; players exceeding the score threshold are eliminated. Last player standing wins.

## Project structure

```
src/
  game/
    models.py       Card, PlayerState, TableGame, GameState data models
    deck.py         Deck creation, shuffle, deal, draw operations
    validator.py    Sequence/combination validation, opening, discard rules
    scoring.py      Hand scoring, elimination, winner detection
    engine.py       Turn orchestration and game flow
    integrity.py    State integrity checker (108-card conservation)
  lobby/
    manager.py      Lobby creation, join, ready, game start
  db/
    repository.py   Protocol interfaces (GameRepository, LobbyRepository, UserRepository)
    memory.py       In-memory implementations for tests and CLI
    dynamodb.py     DynamoDB implementations with optimistic locking
  utils/
    constants.py    Suits, ranks, phases, statuses, thresholds
    crypto.py       Deterministic/secure RNG, lobby code generation
  bot/
    router.py       Update routing (commands vs callbacks)
    commands.py     Slash command handlers (/start, /newlobby, /join, etc.)
    callbacks.py    Inline keyboard callback handlers (draw, play, discard, attach)
    notifications.py Turn notifications and round-end announcements
    messages.py     Message formatting and keyboard builders
    deps.py         Dependency container
  handler.py        AWS Lambda entry point
cli/
  play.py           Interactive local game (terminal)
  simulate.py       AI game simulator for stress testing
  inspect_state.py  Debug tool for inspecting saved game state
infra/
  template.yaml     SAM template (Lambda, API Gateway, DynamoDB tables)
tests/
  unit/             238 tests covering all modules
  integration/      Full game flow, simulated games, end-to-end bot flow
```

## Game rules implemented

- 2-4 players, 13 cards each
- Draw from deck or discard pile (discard pile requires having opened)
- Opening requires valid games totaling at least 40 points
- Sequences: 3+ consecutive same-suit cards, max 1 joker, ace low (A-2-3) or high (Q-K-A), no wrapping
- Combinations: 3-4 same-rank different-suit cards, max 1 joker
- After opening: play new games, attach cards to existing table games, substitute jokers
- Discard rules: cannot discard the card just picked from discard pile; in 3+ player games, cannot discard a card attachable to a table game (unless closing)
- Closing: discard last card after opening and completing at least one full round
- Scoring: ace = 11, face cards = 10, joker = 25, number cards = face value
- Elimination at 101 points (configurable); last player standing wins

## Requirements

- Python 3.12+
- Dependencies: `pip install -r requirements.txt`
- Dev dependencies: `pip install -r requirements-dev.txt`

## Usage

### Run tests

```bash
make test          # all tests
make test-unit     # unit tests only
make test-cov      # with HTML coverage report
make lint          # ruff + mypy
```

### Play locally

```bash
python -m cli.play --players 2 --seed 42
```

Commands: `draw`, `pickup`, `open`, `play`, `attach`, `discard`, `hand`, `table`, `quit`.

### Simulate games

```bash
python -m cli.simulate --games 100 --players 4 --seed 1
```

Runs AI-driven games with integrity checks after every turn. Reports completion rate, average turns, and win distribution.

## Deployment

The project deploys to AWS using SAM. Infrastructure is defined in `infra/template.yaml`:

- AWS Lambda (Python 3.12, 128 MB, 29s timeout)
- API Gateway (POST /bot webhook)
- DynamoDB tables: Games, Users, Lobbies (with TTL)

CI/CD runs via GitHub Actions (`.github/workflows/deploy.yml`): lint, test, then SAM deploy on push to main. AWS authentication uses OIDC (no static keys).

Required GitHub secrets: `AWS_ACCOUNT_ID`, `AWS_REGION`, `TELEGRAM_BOT_TOKEN`.

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Register and see welcome message |
| `/help` | Game rules and command list |
| `/newlobby` | Create a new game lobby |
| `/join CODE` | Join a lobby by code |
| `/ready` | Toggle ready status |
| `/startgame` | Start game (host only, all must be ready) |
| `/hand` | Show your current hand |
| `/table` | Show table state |
| `/scores` | Show score table |
| `/leave` | Leave current lobby |

During gameplay, players interact via inline keyboards: draw from deck/discard, select cards to play/open/attach, and discard.
