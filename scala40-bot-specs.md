# Specifiche Tecniche — Bot Telegram Scala 40 Multiplayer

## 1. Panoramica del Progetto

### 1.1 Obiettivo
Sviluppare un bot Telegram che consenta a più giocatori di giocare a **Scala 40** online, gestendo lobby, sfide, partite complete e punteggi, secondo il regolamento ufficiale della Federazione Italiana Scala 40.

### 1.2 Stack Tecnologico

| Componente | Tecnologia |
|---|---|
| Runtime | AWS Lambda (Python 3.12) |
| API Gateway | AWS API Gateway (webhook Telegram) |
| Database | Amazon DynamoDB (on-demand billing) |
| Bot Framework | Telegram Bot API via webhook (libreria `python-telegram-bot` o `httpx`/`requests`) |
| Infrastruttura | AWS SAM / Serverless Framework / CDK |
| Linguaggio | **Python 3.12** |

### 1.3 Vincoli di Costo — Solo AWS Free Tier

Tutti i servizi devono rientrare nel Free Tier AWS:

| Servizio | Free Tier |
|---|---|
| Lambda | 1M richieste/mese + 400.000 GB-sec |
| API Gateway | 1M chiamate API/mese (12 mesi) |
| DynamoDB (on-demand) | 25 GB storage, 25 RCU/WCU provisioned oppure 200M request units/mese on-demand (primi 12 mesi) |

Non utilizzare ElastiCache, RDS, o altri servizi a pagamento. Lo stato di gioco è interamente gestito su DynamoDB.

### 1.4 Vincoli Architetturali
- Ogni invocazione Lambda ha un timeout massimo di 29 secondi (API Gateway limit). Le operazioni di gioco devono essere atomiche e rapide.
- Lo stato di gioco è interamente persistito su DynamoDB (Lambda è stateless). Nessun layer di cache esterno.
- Il bot opera tramite **webhook** (non polling), configurato su API Gateway.
- Python 3.12 scelto per **cold start minimi** (~100-200ms), `boto3` preinstallato nel runtime Lambda (non serve includerlo nel bundle).

---

## 2. Architettura

### 2.1 Diagramma dei Flussi

```
Telegram → API Gateway → Lambda (handler) → DynamoDB
                                           → Telegram API (risposte)
```

### 2.2 Struttura Lambda

Singola Lambda con routing interno basato su tipo di update Telegram:
- **Comandi** (`/start`, `/newlobby`, `/join`, `/challenge`, ecc.)
- **Callback query** (bottoni inline per azioni di gioco)
- **Inline query** (opzionale, per visualizzare carte in mano)

### 2.3 Tabelle DynamoDB

#### `Users`
| Campo | Tipo | Descrizione |
|---|---|---|
| `userId` (PK) | String | Telegram user ID |
| `username` | String | Username Telegram |
| `displayName` | String | Nome visualizzato |
| `stats` | Map | `{gamesPlayed, wins, losses, totalPoints}` |
| `currentGameId` | String | ID partita in corso (null se idle) |
| `createdAt` | String | ISO timestamp |

#### `Lobbies`
| Campo | Tipo | Descrizione |
|---|---|---|
| `lobbyId` (PK) | String | UUID |
| `hostUserId` | String | Creatore della lobby |
| `players` | List | `[{userId, username, ready}]` — max 4 |
| `status` | String | `waiting` / `starting` / `in_game` / `closed` |
| `settings` | Map | `{eliminationScore, variants[]}` |
| `chatId` | String | Telegram group/chat ID |
| `createdAt` | String | ISO timestamp |
| `ttl` | Number | Auto-delete lobby inattive (epoch seconds) |

#### `Games`
| Campo | Tipo | Descrizione |
|---|---|---|
| `gameId` (PK) | String | UUID |
| `lobbyId` | String | Lobby di origine |
| `players` | List | `[{userId, hand[], calledGames[], score, hasOpened, isEliminated}]` |
| `deck` | List | Carte rimanenti nel tallone |
| `discardPile` | List | Pozzo degli scarti (ultima carta visibile) |
| `tableGames` | List | Giochi calati sul tavolo `[{owner, cards[], type}]` |
| `currentTurnUserId` | String | Giocatore di turno |
| `turnPhase` | String | `draw` / `play` / `discard` |
| `roundNumber` | Number | Numero del giro corrente |
| `dealerUserId` | String | Cartaro corrente |
| `firstRoundComplete` | Boolean | Flag primo giro (non si può chiudere al primo giro) |
| `smazzataNumber` | Number | Numero smazzata corrente |
| `scores` | Map | Punteggio cumulativo `{userId: totalScore}` |
| `status` | String | `playing` / `round_end` / `finished` |
| `settings` | Map | Impostazioni partita |
| `updatedAt` | String | ISO timestamp |

---

## 3. Regole di Gioco — Implementazione

Questa sezione definisce le regole di Scala 40 che il bot DEVE implementare, derivate dal regolamento ufficiale.

### 3.1 Mazzo e Carte

- **2 mazzi francesi** = 108 carte totali (52×2 + 4 jolly).
- Ogni carta è rappresentata come dizionario: `{"suit": "hearts"|"diamonds"|"clubs"|"spades"|"joker", "rank": 0..13, "deck": 0|1}`.
- `rank: 0` = Jolly, `rank: 1` = Asso, `rank: 11` = Jack, `rank: 12` = Queen, `rank: 13` = King.

**Valori punti:**

| Carta | Valore punti |
|---|---|
| Jolly | 25 |
| Asso (in tris o dopo il Re) | 11 |
| Asso (in scala prima del 2) | 1 |
| Figure (J, Q, K) | 10 |
| Carte numeriche (2-10) | Valore nominale |

### 3.2 Distribuzione

1. Il cartaro mescola (shuffle randomico crittografico).
2. Distribuisce 13 carte a testa, una per volta, in senso orario.
3. Scopre una carta sul pozzo.
4. Le restanti formano il tallone.
5. Il primo a giocare è il giocatore a sinistra del cartaro.

### 3.3 Sequenze (Scale)

- Minimo 3 carte dello **stesso seme**, in ordine consecutivo.
- Massimo 14 carte (A-2-3-4-5-6-7-8-9-10-J-Q-K-A con matta, oppure Matta-2-...-K-A).
- L'Asso può stare PRIMA del 2 (vale 1) OPPURE DOPO il Re (vale 11). Non è "circolare" (non si può fare K-A-2).
- Massimo **1 jolly/matta** per sequenza.

### 3.4 Combinazioni (Tris/Poker)

- Minimo 3, massimo 4 carte dello **stesso valore** ma di **semi diversi**.
- NON si possono avere due carte dello stesso seme in una combinazione.
- Massimo **1 jolly/matta** per combinazione.
- NON sono ammesse combinazioni composte solo da jolly.

### 3.5 Apertura

- Per "aprire" (calare giochi per la prima volta), il valore totale delle carte calate deve essere **≥ 40 punti**.
- Il jolly all'interno dei giochi di apertura prende il valore della carta che sostituisce.
- **Validazione obbligatoria**: il bot deve calcolare e verificare che la somma sia ≥ 40.

### 3.6 Fasi del Turno

```
INIZIO TURNO
│
├─ Se NON ha aperto → DEVE pescare dal tallone
├─ Se HA aperto → PUÒ pescare dal tallone OPPURE raccogliere ultimo scarto dal pozzo
│
▼
FASE DI GIOCO (solo se ha aperto)
│
├─ Calare nuovi giochi (sequenze/combinazioni)
├─ Attaccare carte a giochi esistenti (propri o altrui)
├─ Sostituire un jolly in un gioco sul tavolo (obbligatorio usarlo subito)
│
▼
SCARTO (obbligatorio, chiude il turno)
│
├─ Se ha raccolto dallo scarto → NON può scartare la stessa carta raccolta
├─ NON può scartare una carta che attacca a giochi sul tavolo (in partite >2 giocatori)
│   (consentito nel 1v1 se ha già aperto, o se chiude con lo scarto)
└─ Può chiudere scartando l'ultima carta
```

### 3.7 Regole sullo Scarto

1. Se un giocatore raccoglie l'ultima carta dal pozzo, **DEVE** utilizzarla in un gioco (calare, attaccare o inserire in combinazione/sequenza) nello stesso turno. Non può tenerla e scartarne un'altra senza averla usata.
2. Non si può scartare la stessa carta appena raccolta dal pozzo (a meno che si possieda un duplicato identico — stessa carta, stesso seme, altro mazzo — in quel caso si deve dichiararlo).
3. In partite con più di 2 giocatori, è **vietato** scartare una carta che potrebbe essere attaccata a un gioco già presente sul tavolo, a meno che si chiuda con quello scarto.
4. Le carte nel pozzo devono essere impilate in modo che solo l'ultima sia visibile.

### 3.8 Sostituzione Jolly

- Solo un giocatore che ha **già aperto** può sostituire un jolly sul tavolo.
- Deve avere in mano la carta specifica che il jolly sostituisce.
- Il jolly preso **DEVE** essere immediatamente utilizzato in un gioco (calato in nuova combinazione/sequenza o attaccato a gioco esistente). Non può finire in mano.

### 3.9 Chiusura

- Si chiude scartando l'ultima carta nel pozzo (devono rimanere **0 carte** in mano dopo lo scarto).
- **NON** è possibile chiudere al primo giro: ogni giocatore deve aver giocato almeno un turno completo.
- **NON** è possibile chiudere senza scartare. Se un giocatore resta senza carte senza aver scartato, deve riprendere l'ultimo gioco calato e rigiocare correttamente.
- Se il tallone si esaurisce senza che nessuno chiuda: il pozzo (tranne l'ultima carta scartata) viene mescolato e diventa il nuovo tallone.

### 3.10 Punteggio

Alla chiusura di un giocatore:
- Chi ha chiuso: **0 punti** per quella smazzata.
- Gli altri: somma dei valori delle carte rimaste in mano (Jolly=25, Asso=11, Figure=10, altre=nominale).
- I punti si accumulano tra le smazzate.
- Chi raggiunge o supera il **punteggio di eliminazione** (default 101, configurabile a 201) è eliminato.
- Vince l'ultimo giocatore rimasto sotto la soglia.

### 3.11 Varianti (Configurabili per Lobby)

| Variante | Descrizione | Default |
|---|---|---|
| **Apertura con lo scarto** | Si può raccogliere dal pozzo anche senza aver aperto, purché si apra nello stesso turno usando quella carta nei giochi dell'apertura. | OFF |
| **Chiusura in mano** | Chi chiude calando tutto in una volta: gli avversari contano doppio. Chi ha tutte 13 carte in mano: 100 punti fissi. | OFF |
| **Apertura senza jolly** | Il jolly non può essere usato nell'apertura, a meno che si calino anche giochi "puliti" che da soli raggiungano ≥ 40 punti. | OFF |

---

## 4. Comandi Telegram

### 4.1 Comandi Generali

| Comando | Descrizione |
|---|---|
| `/start` | Registrazione utente e messaggio di benvenuto |
| `/help` | Regole e lista comandi |
| `/stats` | Statistiche personali |
| `/leaderboard` | Classifica globale top 10 |

### 4.2 Comandi Lobby

| Comando | Descrizione |
|---|---|
| `/newlobby` | Crea una nuova lobby (2-4 giocatori) |
| `/join <codice>` | Entra in una lobby tramite codice |
| `/leave` | Lascia la lobby corrente |
| `/ready` | Segnala che sei pronto |
| `/settings` | Mostra/modifica impostazioni lobby (solo host) |
| `/startgame` | Avvia la partita (solo host, tutti devono essere ready) |
| `/lobby` | Mostra stato corrente della lobby |

### 4.3 Comandi di Gioco

Il gioco si svolge primariamente tramite **inline keyboard** (bottoni), ma con comandi testuali come fallback.

| Comando / Azione | Descrizione |
|---|---|
| `/hand` | Mostra le carte in mano (messaggio privato) |
| `/draw` | Pesca dal tallone |
| `/pickup` | Raccoglie l'ultima carta dal pozzo |
| `/play` | Avvia la fase di calata (apre menu interattivo) |
| `/attach` | Attacca una carta a un gioco sul tavolo |
| `/discard <carta>` | Scarta una carta |
| `/table` | Mostra i giochi attualmente sul tavolo |
| `/scores` | Mostra punteggi della partita |
| `/quit` | Abbandona la partita (penalità) |

---

## 5. Interfaccia Utente Telegram

### 5.1 Visualizzazione Carte

Le carte vengono rappresentate con **emoji Unicode**:

```
♠ ♥ ♦ ♣ 🃏

Esempi:
A♠  2♥  3♦  4♣  5♠  ...  J♥  Q♦  K♣  🃏
```

### 5.2 Mano del Giocatore

Inviata come **messaggio privato** (DM) per garantire segretezza:

```
🎴 La tua mano (13 carte):
1. A♠   2. 3♥   3. 3♦   4. 5♣   5. 7♠
6. 8♥   7. 9♦   8. 10♣  9. J♠   10. Q♥
11. K♦  12. K♣  13. 🃏

[Ordina per Seme] [Ordina per Valore]
```

### 5.3 Stato del Tavolo

Inviato nella chat di gruppo/partita:

```
🎲 SCALA 40 — Smazzata #2

👤 Turno di: @giocatore2 (fase: Gioco)

♠ Pozzo: K♥
📦 Tallone: 42 carte

📋 Giochi sul tavolo:
  @giocatore1: [3♥ 4♥ 5♥ 6♥] | [J♠ J♥ J♦]
  @giocatore3: [🃏 8♦ 9♦ 10♦]

🖐 Carte in mano:
  @giocatore1: 6 carte
  @giocatore2: 11 carte ← turno
  @giocatore3: 9 carte
  @giocatore4: 13 carte (non ha aperto)

📊 Punteggi: P1: 23 | P2: 45 | P3: 12 | P4: 67
```

### 5.4 Inline Keyboard per Azioni

Durante il proprio turno, il giocatore riceve bottoni contestuali:

**Fase Draw:**
```
[🎴 Pesca dal Tallone]  [♻️ Prendi dal Pozzo (K♥)]
```

**Fase Play (dopo apertura):**
```
[📤 Cala Gioco]  [📎 Attacca Carta]  [🔄 Sostituisci Jolly]  [🚮 Scarta]
```

**Selezione carte** (multi-select con conferma):
```
[A♠ ✓] [3♥] [3♦ ✓] [5♣] [7♠ ✓] ...
[✅ Conferma] [❌ Annulla]
```

---

## 6. Game Engine — Logica Core

### 6.1 Modulo `deck.py`

```python
def shuffle(cards: list[dict]) -> list[dict]
    # Fisher-Yates con secrets.SystemRandom (crittografico)

def deal(deck: list, num_players: int, cards_each: int = 13) -> dict:
    # returns {"hands": [...], "deck": [...], "first_discard": {...}}

def draw_from_deck(deck: list) -> tuple[dict, list]

def draw_from_discard(discard_pile: list) -> tuple[dict, list]

def reshuffle_discard(discard_pile: list) -> tuple[list, dict]:
    # quando il tallone finisce → nuovo tallone + ultima carta come nuovo pozzo
```

### 6.2 Modulo `validator.py`

```python
def is_valid_sequence(cards: list[dict]) -> dict:
    # returns {"valid": bool, "points": int, "error": str|None}

def is_valid_combination(cards: list[dict]) -> dict:

def is_valid_opening(games: list[list[dict]]) -> dict:
    # verifica ≥ 40 punti totali

def can_attach(card: dict, existing_game: list[dict]) -> dict:

def can_substitute_joker(card: dict, existing_game: list[dict]) -> dict:

def is_valid_discard(card: dict, discard_pile: list, table_games: list,
                     player_has_opened: bool, num_players: int) -> dict:
```

### 6.3 Modulo `engine.py`

```python
def start_round(game: dict) -> dict
def process_draw(game: dict, user_id: str, source: str) -> dict
def process_play(game: dict, user_id: str, action: dict) -> dict
def process_discard(game: dict, user_id: str, card: dict) -> dict
def check_closure(game: dict, user_id: str) -> dict
def advance_turn(game: dict) -> dict
def check_elimination(game: dict) -> dict
```

### 6.4 State Machine del Turno

```
WAITING_FOR_DRAW
    ↓ (draw/pickup)
WAITING_FOR_PLAY
    ↓ (play actions, opzionali e ripetibili)
WAITING_FOR_DISCARD
    ↓ (discard)
TURN_END → avanza al giocatore successivo → WAITING_FOR_DRAW
```

Se il giocatore non ha ancora aperto e non apre in questo turno, la fase `WAITING_FOR_PLAY` viene saltata (pesca e scarta).

---

## 7. Gestione Lobby e Matchmaking

### 7.1 Flusso Creazione Lobby

```
1. /newlobby → genera codice alfanumerico (6 char)
2. Bot invia link di invito + codice
3. Altri giocatori: /join <codice>
4. Ogni giocatore fa /ready
5. Host fa /startgame quando tutti sono ready (min 2, max 4)
6. Bot crea Game, invia carte in DM a ciascuno
```

### 7.2 Gestione Disconnessioni

- Se un giocatore non risponde entro **120 secondi** durante il suo turno → promemoria.
- Dopo **300 secondi** totali → turno automatico (pesca e scarta carta più alta).
- Se un giocatore lascia la partita → punteggio di eliminazione assegnato + continua con i restanti.
- Se rimane un solo giocatore → vittoria automatica.

### 7.3 Timeout Lobby

- Lobby inattiva per **30 minuti** → auto-chiusura (TTL DynamoDB).
- Partita inattiva per **1 ora** → auto-chiusura.

---

## 8. AWS Lambda — Dettagli Implementativi

### 8.1 Handler Principale

```
webhook POST /bot → Lambda handler
    ├── parse Telegram Update
    ├── routing (command / callback_query / etc.)
    ├── load game state da DynamoDB
    ├── esegui logica di gioco
    ├── salva state aggiornato su DynamoDB (conditional write per concurrency)
    └── rispondi via Telegram API (sendMessage, editMessageReplyMarkup, etc.)
```

### 8.2 Concurrency e Race Conditions

- Usare **conditional writes** DynamoDB (`ConditionExpression`) con version number per evitare conflitti.
- Ogni modifica allo stato di gioco è atomica: read → validate → write-if-version-matches.
- In caso di conflitto, ritentare (max 3 retry con backoff).

### 8.3 Cold Start Optimization

- **Python 3.12** scelto specificamente per cold start minimi (~100-200ms vs ~500-800ms Node.js).
- `boto3` è **preinstallato** nel runtime Lambda Python → non includerlo nel deployment package per ridurre il bundle.
- Mantenere il deployment package **< 3 MB** (solo codice applicativo + dipendenze leggere come `httpx`).
- Inizializzare il client DynamoDB **fuori dall'handler** (a livello di modulo) per riutilizzarlo tra invocazioni calde.
- Usare **128 MB** di RAM (sufficiente per Python, riduce i costi).
- NON usare Provisioned Concurrency (a pagamento). I cold start Python sono già accettabili.

```python
# handler.py — esempio pattern di inizializzazione
import boto3

# Inizializzato una volta sola, riutilizzato tra invocazioni calde
dynamodb = boto3.resource("dynamodb")
games_table = dynamodb.Table("Scala40_Games")

def lambda_handler(event, context):
    # ... logica qui, usa games_table direttamente
```

### 8.4 Configurazione Lambda

| Parametro | Valore |
|---|---|
| Memory | 128 MB |
| Timeout | 29 secondi |
| Runtime | Python 3.12 |
| Environment vars | `TELEGRAM_BOT_TOKEN`, `DYNAMODB_TABLE_PREFIX`, `GAME_TIMEOUT_SECONDS` |

---

## 9. Sicurezza

- **Validazione webhook**: verificare l'header `X-Telegram-Bot-Api-Secret-Token` per assicurarsi che le richieste provengano da Telegram.
- **Autorizzazione azioni**: ogni azione di gioco verifica che `userId === currentTurnUserId` e che il giocatore sia parte della partita.
- **Anti-cheat**: le carte in mano sono visibili solo al proprietario (DM). Lo stato completo è solo server-side. Il client (Telegram) non riceve mai informazioni su carte altrui.
- **Rate limiting**: API Gateway throttling per prevenire abusi.
- **Secrets**: Token Telegram in AWS Secrets Manager o Parameter Store, referenziato via environment variable crittografata.

---

## 10. Testing

### 10.1 Unit Tests

- `Deck`: shuffle uniformità, distribuzione corretta 13 carte.
- `Validator`: tutti i casi di sequenze/combinazioni valide e invalide, apertura a 40 punti, scarto irregolare, sostituzione jolly.
- `GameEngine`: ogni transizione di stato, chiusura, gestione tallone esaurito, eliminazione giocatore.

### 10.2 Integration Tests

- Flusso completo: creazione lobby → join → start → partita completa → vittoria.
- Gestione errori: azioni fuori turno, carte invalide, disconnessioni.
- Concurrency: multiple azioni simultanee sullo stesso stato.

### 10.3 Edge Cases Critici da Testare

- Apertura con esattamente 40 punti (boundary).
- Asso che vale 1 vs 11 in contesti diversi.
- Sostituzione jolly con obbligo di utilizzo immediato.
- Raccolta da pozzo con obbligo di utilizzo della carta.
- Chiusura al primo giro (deve essere bloccata).
- Chiusura senza scarto (deve essere bloccata).
- Tallone esaurito → rimescola pozzo.
- Scarto di carta che attacca (vietato in partite >2 giocatori).
- Duplicato della carta raccolta dal pozzo (eccezione allo scarto).
- Due giochi uguali sul tavolo (possibile con 2 mazzi).
- Giocatore con 1 carta che non può scartare legalmente.

---

## 11. Struttura del Progetto

```
scala40-bot/
├── src/
│   ├── handler.py              # Lambda entry point (solo adapter, delega a bot/)
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── commands.py         # Gestione comandi (/start, /help, etc.)
│   │   ├── callbacks.py        # Gestione callback query (bottoni)
│   │   └── messages.py         # Template messaggi e formattazione
│   ├── game/
│   │   ├── __init__.py
│   │   ├── deck.py             # Mazzo, shuffle, distribuzione
│   │   ├── validator.py        # Validazione giochi, aperture, scarti
│   │   ├── engine.py           # Game engine principale
│   │   ├── scoring.py          # Calcolo punteggi e eliminazioni
│   │   └── models.py           # Dataclass / TypedDict per le entità di gioco
│   ├── lobby/
│   │   ├── __init__.py
│   │   ├── manager.py          # Creazione/gestione lobby
│   │   └── matchmaking.py      # Logica sfide e inviti
│   ├── db/
│   │   ├── __init__.py
│   │   ├── repository.py       # Interfaccia astratta (Protocol) per persistenza
│   │   ├── dynamodb.py         # Implementazione DynamoDB (produzione)
│   │   ├── memory.py           # Implementazione in-memory (test/locale)
│   │   └── schemas.py          # Schema e mapping tabelle
│   └── utils/
│       ├── __init__.py
│       ├── telegram.py         # Wrapper Telegram API (httpx)
│       ├── crypto.py           # Random sicuro per shuffle (secrets)
│       └── constants.py        # Costanti di gioco
├── cli/
│   ├── __init__.py
│   ├── play.py                 # CLI interattiva per giocare partite locali
│   ├── simulate.py             # Simulatore partite automatiche (AI vs AI)
│   └── inspect_state.py        # Dump e ispezione stato di gioco
├── tests/
│   ├── unit/
│   │   ├── test_deck.py
│   │   ├── test_validator.py
│   │   └── test_engine.py
│   ├── integration/
│   │   └── test_game_flow.py
│   └── conftest.py             # Fixtures pytest (in-memory repo, game factory)
├── .github/
│   └── workflows/
│       └── deploy.yml          # CI/CD: lint, test, deploy via OIDC
├── infra/
│   ├── template.yaml           # SAM template
│   └── dynamodb-tables.yaml    # CloudFormation per tabelle
├── requirements.txt            # Dipendenze produzione (httpx — NO boto3)
├── requirements-dev.txt        # pytest, moto, ruff, mypy, etc.
├── Makefile                    # Shortcut: make test, make local, make deploy
└── README.md
```

> **Nota**: `boto3` NON va incluso in `requirements.txt` perché è già presente nel runtime Lambda Python. Includerlo aumenterebbe inutilmente il bundle e il cold start.

---

## 12. Sviluppo Locale e Separazione dal Runtime Lambda

### 12.1 Principio Architetturale

Il codice DEVE essere strutturato in modo che il game engine, la logica di lobby e tutta la business logic siano **completamente indipendenti** da Lambda, Telegram e DynamoDB. Lambda è solo un adapter (entry point) che riceve eventi e li inoltra alla logica core.

```
┌─────────────────────────────────────────────┐
│               Entry Points                   │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐ │
│  │ Lambda   │  │ CLI      │  │ pytest    │ │
│  │ handler  │  │ play.py  │  │ fixtures  │ │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘ │
│       │              │              │        │
│       ▼              ▼              ▼        │
│  ┌──────────────────────────────────────┐   │
│  │         Business Logic               │   │
│  │  game/engine.py  game/validator.py   │   │
│  │  lobby/manager.py  scoring.py        │   │
│  └──────────────┬───────────────────────┘   │
│                 │                            │
│       ┌─────────┴─────────┐                 │
│       ▼                   ▼                 │
│  ┌──────────┐      ┌───────────┐            │
│  │ DynamoDB │      │ In-Memory │            │
│  │ Repo     │      │ Repo      │            │
│  └──────────┘      └───────────┘            │
└─────────────────────────────────────────────┘
```

### 12.2 Repository Pattern (Dependency Injection)

Il layer di persistenza deve seguire un **Protocol** (interfaccia) Python, con due implementazioni:

```python
# src/db/repository.py
from typing import Protocol

class GameRepository(Protocol):
    def get_game(self, game_id: str) -> dict | None: ...
    def save_game(self, game: dict) -> None: ...
    def delete_game(self, game_id: str) -> None: ...

class LobbyRepository(Protocol):
    def get_lobby(self, lobby_id: str) -> dict | None: ...
    def save_lobby(self, lobby: dict) -> None: ...
    def list_open_lobbies(self) -> list[dict]: ...

# src/db/dynamodb.py → implementazione produzione
# src/db/memory.py   → implementazione in-memory per test e CLI
```

Il game engine e la lobby ricevono il repository come parametro (constructor injection), MAI import diretto di boto3/DynamoDB.

### 12.3 Esecuzione Locale

#### CLI Interattiva (`cli/play.py`)

Permette di giocare una partita completa da terminale senza Telegram né Lambda:

```bash
# Partita locale a 2 giocatori (umano vs umano)
python -m cli.play --players 2

# Partita con seed fisso (riproducibile per debug)
python -m cli.play --players 3 --seed 42
```

La CLI deve:
- Usare il repository **in-memory** (nessun database necessario).
- Mostrare lo stato del tavolo, la mano del giocatore corrente, le azioni disponibili.
- Accettare input testuale per le azioni (es. `draw`, `play 3h 4h 5h`, `discard Ks`).
- Validare le azioni usando lo stesso `validator.py` usato in produzione.
- Stampare log strutturati di ogni transizione di stato.

#### Simulatore (`cli/simulate.py`)

Esegue partite automatiche con giocatori AI basici (strategia random o euristica) per stress-test dell'engine:

```bash
# Simula 1000 partite a 4 giocatori e stampa statistiche
python -m cli.simulate --games 1000 --players 4

# Simula con seed per riprodurre un bug
python -m cli.simulate --games 1 --players 3 --seed 12345 --verbose
```

#### Makefile

```makefile
test:           ## Esegue tutti i test
	pytest tests/ -v

test-unit:      ## Solo unit test
	pytest tests/unit/ -v

test-cov:       ## Test con coverage report
	pytest tests/ --cov=src --cov-report=html

local-play:     ## Partita locale interattiva
	python -m cli.play --players 2

simulate:       ## Simula 100 partite
	python -m cli.simulate --games 100 --players 4

lint:           ## Linting e type checking
	ruff check src/ tests/ cli/
	mypy src/

format:         ## Auto-format
	ruff format src/ tests/ cli/
```

---

## 13. Osservabilità e Testabilità del Game Engine

### 13.1 Obiettivo

L'agente LLM che sviluppa il progetto DEVE poter **testare e validare il game engine in completa autonomia**, senza dipendere da Telegram, AWS o qualsiasi servizio esterno. Ogni bug nel game engine deve essere riproducibile e diagnosticabile solo con Python e pytest.

### 13.2 Logging Strutturato

Ogni azione del game engine deve produrre log strutturati (JSON) che documentino completamente la transizione di stato:

```python
import logging, json

logger = logging.getLogger("scala40.engine")

def process_draw(game: dict, user_id: str, source: str) -> dict:
    # ... logica ...
    logger.info(json.dumps({
        "event": "draw",
        "game_id": game["gameId"],
        "user_id": user_id,
        "source": source,            # "deck" o "discard"
        "card_drawn": card_code,      # es. "8h"
        "deck_remaining": len(game["deck"]),
        "turn_phase": "play",
        "hand_size": len(player["hand"]),
    }))
    return game
```

**Eventi da loggare obbligatoriamente:**

| Evento | Dati chiave |
|---|---|
| `round_start` | gameId, smazzata, dealer, carte distribuite per giocatore (solo count) |
| `draw` | userId, source, carta pescata, carte rimanenti nel tallone |
| `open` | userId, giochi calati, punti totali apertura |
| `play_sequence` | userId, carte della sequenza |
| `play_combination` | userId, carte della combinazione |
| `attach` | userId, carta attaccata, gioco target |
| `substitute_joker` | userId, carta inserita, jolly rimosso, dove usato il jolly |
| `discard` | userId, carta scartata |
| `invalid_action` | userId, azione tentata, motivo rifiuto |
| `closure` | userId, smazzata, punteggi tutti i giocatori |
| `elimination` | userId, punteggio totale, soglia |
| `game_end` | vincitore, punteggi finali |

### 13.3 Game State Snapshot e Replay

Il game engine deve esporre una funzione per esportare lo **stato completo** della partita in formato JSON serializzabile:

```python
def export_state(game: dict) -> str:
    """Esporta lo stato completo in JSON leggibile per debug/replay."""
    return json.dumps(game, indent=2, ensure_ascii=False)

def import_state(json_str: str) -> dict:
    """Importa uno stato per riprendere o riprodurre una partita."""
    return json.loads(json_str)
```

Questo permette all'agente LLM di:
- Salvare lo stato in un punto qualsiasi della partita.
- Riprodurre un bug caricando lo snapshot e riapplicando l'azione problematica.
- Scrivere test che partono da stati specifici senza dover giocare dall'inizio.

### 13.4 Test Fixtures e Factory

```python
# tests/conftest.py
import pytest
from src.db.memory import InMemoryGameRepository, InMemoryLobbyRepository
from src.game.engine import GameEngine
from src.game.deck import create_deck, shuffle, deal

@pytest.fixture
def engine():
    """Engine con repository in-memory, pronto all'uso."""
    repo = InMemoryGameRepository()
    return GameEngine(repo)

@pytest.fixture
def started_game(engine):
    """Partita già iniziata con 4 giocatori e carte distribuite."""
    game = engine.create_game(
        player_ids=["p1", "p2", "p3", "p4"],
        settings={"elimination_score": 101}
    )
    engine.start_round(game["gameId"])
    return engine.get_game(game["gameId"])

@pytest.fixture
def opened_game(started_game, engine):
    """Partita dove il primo giocatore ha già aperto (per testare attacchi, scarti, etc.)."""
    # ... setup con apertura forzata ...
    return game
```

### 13.5 Ispezione Stato da CLI (`cli/inspect_state.py`)

Tool per caricare e ispezionare un game state salvato:

```bash
# Dump stato leggibile
python -m cli.inspect_state --file game_snapshot.json

# Mostra mano di un giocatore specifico
python -m cli.inspect_state --file game_snapshot.json --player p2 --show hand

# Mostra giochi sul tavolo
python -m cli.inspect_state --file game_snapshot.json --show table

# Valida che lo stato sia coerente (carte totali = 108, nessuna duplicazione illecita)
python -m cli.inspect_state --file game_snapshot.json --validate
```

### 13.6 State Integrity Checker

Implementare una funzione di **validazione invarianti** eseguibile in qualsiasi momento:

```python
def validate_game_integrity(game: dict) -> list[str]:
    """
    Verifica che lo stato di gioco sia coerente. Ritorna lista di errori (vuota = OK).
    Controlla:
    - Totale carte = 108 (mani + tallone + pozzo + tavolo)
    - Nessuna carta duplicata illegalmente
    - Tutti i giochi sul tavolo sono validi (sequenze/combinazioni)
    - Il giocatore di turno esiste ed è attivo
    - La fase del turno è coerente con le azioni eseguite
    """
```

Questa funzione va chiamata:
- Dopo ogni azione nei **test**.
- Opzionalmente in **produzione** (dietro flag, per debug).
- Sempre nel **simulatore**.

---

## 14. CI/CD — GitHub Actions con OIDC Deploy su AWS

### 14.1 Repository GitHub

Il progetto è ospitato su GitHub. Il branch `main` è protetto e il deploy avviene solo da esso.

### 14.2 Pipeline CI/CD (`.github/workflows/deploy.yml`)

```yaml
name: CI/CD Scala 40 Bot

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  id-token: write   # Necessario per OIDC
  contents: read

env:
  AWS_REGION: eu-south-1        # Milano
  STACK_NAME: scala40-bot
  PYTHON_VERSION: "3.12"

jobs:

  # ── Job 1: Lint + Type Check ──────────────────────
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: pip install ruff mypy
      - run: ruff check src/ tests/ cli/
      - run: mypy src/

  # ── Job 2: Test ───────────────────────────────────
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: pytest tests/ -v --tb=short --cov=src --cov-report=xml
      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml

  # ── Job 3: Build + Deploy (solo su main) ──────────
  deploy:
    needs: [lint, test]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - uses: aws-actions/setup-sam@v2

      # ── OIDC Authentication (no secret keys!) ──
      - name: Configure AWS credentials via OIDC
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::${{ secrets.AWS_ACCOUNT_ID }}:role/GitHubActionsDeployRole
          aws-region: ${{ env.AWS_REGION }}

      # ── Build ──
      - run: sam build --use-container

      # ── Deploy ──
      - run: |
          sam deploy \
            --stack-name ${{ env.STACK_NAME }} \
            --region ${{ env.AWS_REGION }} \
            --capabilities CAPABILITY_IAM \
            --no-confirm-changeset \
            --no-fail-on-empty-changeset \
            --parameter-overrides \
              TelegramBotToken=${{ secrets.TELEGRAM_BOT_TOKEN }}
```

### 14.3 Setup OIDC su AWS

Per eliminare la necessità di access key statiche, configurare OIDC trust tra GitHub e AWS:

**1. Creare un Identity Provider in IAM:**
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

**2. Creare il ruolo IAM `GitHubActionsDeployRole`:**

Trust policy:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:<GITHUB_ORG>/<REPO_NAME>:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

**3. Permission policy del ruolo** (minime necessarie):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "lambda:*",
        "apigateway:*",
        "dynamodb:CreateTable",
        "dynamodb:DescribeTable",
        "dynamodb:UpdateTable",
        "dynamodb:DeleteTable",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:DeleteRole",
        "iam:GetRole",
        "iam:PassRole",
        "s3:*"
      ],
      "Resource": "*"
    }
  ]
}
```

> **Nota**: restringere le `Resource` al minimo necessario in produzione. L'esempio sopra è permissivo per semplicità di setup iniziale.

### 14.4 Secrets GitHub

Configurare nel repository GitHub (Settings → Secrets):

| Secret | Descrizione |
|---|---|
| `AWS_ACCOUNT_ID` | ID account AWS (12 cifre) |
| `TELEGRAM_BOT_TOKEN` | Token del bot da BotFather |

**Non servono `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`** grazie a OIDC.

## 15. Roadmap di Sviluppo

### Fase 1 — Core (MVP)
- [ ] Setup progetto, infrastruttura AWS (Lambda + API Gateway + DynamoDB)
- [ ] Repository pattern con implementazione in-memory e DynamoDB
- [ ] Registrazione utente (`/start`)
- [ ] Sistema lobby (creazione, join, ready, start)
- [ ] Game engine: mazzo, distribuzione, turni
- [ ] Validazione giochi (sequenze, combinazioni, apertura ≥ 40)
- [ ] CLI locale interattiva (`cli/play.py`)
- [ ] Flusso completo di una smazzata (pesca → gioco → scarto → chiusura)
- [ ] Punteggio e gestione smazzate multiple
- [ ] Eliminazione giocatori e vittoria
- [ ] State integrity checker
- [ ] Pipeline CI/CD GitHub Actions con OIDC

### Fase 2 — Completezza
- [ ] Sostituzione jolly
- [ ] Gestione tallone esaurito (rimescola)
- [ ] Regola scarto che attacca
- [ ] Regola primo giro (no chiusura)
- [ ] Raccolta da pozzo con obbligo utilizzo
- [ ] Timeout turni e auto-play
- [ ] Gestione disconnessioni
- [ ] Simulatore partite automatiche (`cli/simulate.py`)
- [ ] Logging strutturato completo (tutti gli eventi della Sezione 13.2)

### Fase 3 — Varianti e Polish
- [ ] Implementare varianti configurabili (apertura con scarto, chiusura in mano, apertura senza jolly)
- [ ] Leaderboard e statistiche
- [ ] Notifiche turno (mention Telegram)
- [ ] Tutorial interattivo per nuovi giocatori
- [ ] Ottimizzazione performance e cold start

---

## 16. Note per l'Agente LLM Sviluppatore

1. **Regolamento ufficiale**: tutte le regole nella Sezione 3 sono derivate dal regolamento ufficiale della Federazione Italiana Scala 40 e devono essere implementate fedelmente. In caso di ambiguità, fare riferimento al regolamento allegato.

2. **Priorità assoluta**: la correttezza delle regole di gioco è più importante di qualsiasi ottimizzazione. Ogni azione del giocatore deve essere validata server-side.

3. **Atomicità**: ogni operazione di gioco (draw, play, discard) deve essere una singola transazione atomica su DynamoDB. Non lasciare mai lo stato in una condizione intermedia.

4. **Privacy**: le carte in mano di un giocatore non devono MAI essere visibili ad altri giocatori. Usare esclusivamente messaggi privati per mostrare la mano.

5. **UX Telegram**: l'interfaccia deve essere fluida. Usare `editMessageReplyMarkup` per aggiornare i bottoni in-place anziché inviare nuovi messaggi quando possibile. Minimizzare lo spam di messaggi.

6. **Idempotenza**: le callback query di Telegram possono arrivare duplicate. Ogni azione deve essere idempotente (controllare lo stato attuale prima di eseguire).

7. **Encoding carte**: definire un encoding compatto per le carte (es. `"8h"` = 8 di cuori, `"Ks"` = Re di picche, `"J0"` = Jolly mazzo 1) per minimizzare lo spazio in DynamoDB e ridurre i costi di lettura/scrittura.

8. **Lingua**: l'interfaccia utente del bot deve essere in **italiano**.

9. **DynamoDB — Ottimizzazione costi Free Tier**:
   - Usare **on-demand billing mode** per non pagare capacity inutilizzata.
   - Usare **eventually consistent reads** (default, metà costo) per tutto tranne lo stato di gioco attivo durante un turno, dove usare **strongly consistent reads**.
   - Attivare **TTL** sulle tabelle Lobbies e Games per eliminare automaticamente i record scaduti senza costo di scrittura.
   - Compattare lo stato di gioco: una singola riga DynamoDB per partita (evitare item multipli per turno).

10. **Dipendenze Python**: mantenere le dipendenze al minimo assoluto. `boto3` è già nel runtime. Per le chiamate HTTP a Telegram, usare `urllib3` (già incluso come dipendenza di `botocore`) oppure `httpx` (leggero). Evitare framework pesanti.

11. **Separazione engine/infrastruttura**: il game engine (`src/game/`) NON deve MAI importare `boto3`, `telegram`, o qualsiasi dipendenza infrastrutturale. Deve funzionare con solo Python standard + i propri moduli. L'unica dipendenza esterna è il repository, iniettato come parametro.

12. **Testabilità first**: ogni feature del game engine deve avere test automatici PRIMA o DURANTE lo sviluppo. Il simulatore (`cli/simulate.py`) va usato come smoke test continuo: se 1000 partite simulate non producono errori, l'engine è probabilmente corretto.

13. **Riproducibilità**: supportare un parametro `seed` per il random, in modo che qualsiasi partita (locale, simulata, o test) possa essere riprodotta esattamente per debug. In produzione il seed è generato crittograficamente; in test/CLI è fissabile.

14. **CI obbligatoria**: nessun merge su `main` senza che lint + test passino. Il deploy è automatico solo da `main` via OIDC. Non usare MAI access key statiche AWS nel repository.
