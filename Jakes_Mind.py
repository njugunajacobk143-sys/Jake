# ============================================================
# JAKE'S MIND TERMINAL
#
# Streamlit + Python-Chess + Stockfish + Groq + Voice
# 
# FEATURES
# ------------------------------------------------------------
# - Interactive clickable chessboard
# - Jake automatically plays White
# - User plays Black
# - Dynamic chess leveling
# - Persistent chess_learnings.md
# - Adaptive Stockfish Skill Level + Depth
# - Manual difficulty override
# - Move history
# - Undo complete turn
# - PGN export
# - Persistent chat
# - Persistent ideas vault
# - Persistent poetry journal
# - Browser microphone input
# - Windows pyttsx3 speech output
# - Groq retry/backoff
# - Secure API-key loading
# - Logging
# - Sticky chess column
# - Three-row right-hand terminal
#
# REQUIREMENT:
#     Streamlit >= 1.52
#
# ============================================================


# ============================================================
# 1. STANDARD LIBRARY
# ============================================================

import io
import json
import logging
import os
import queue
import random
import re
import threading
import time
from datetime import datetime
from pathlib import Path


# ============================================================
# 2. THIRD-PARTY
# ============================================================

import chess
import chess.engine
import chess.pgn

import pyttsx3
import speech_recognition as sr

import streamlit as st
from groq import Groq


# ============================================================
# 3. STREAMLIT COMPONENTS V2
# ============================================================

try:
    import streamlit.components.v2 as components_v2

    COMPONENTS_V2_AVAILABLE = True

except Exception:

    COMPONENTS_V2_AVAILABLE = False


# ============================================================
# 4. PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Jake's Mind Terminal",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# 5. APPLICATION PATHS
# ============================================================

BASE_DIR = Path(
    __file__
).resolve().parent

VAULT_DIR = (
    BASE_DIR /
    "Brain_vault"
)

VAULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


PHILOSOPHY_PATH = (
    VAULT_DIR /
    "My_Philosophy.txt"
)

IDEAS_LOG_PATH = (
    VAULT_DIR /
    "ideas_log.md"
)

POETRY_LOG_PATH = (
    VAULT_DIR /
    "poetry_journal.md"
)

CHESS_LEARNINGS_PATH = (
    VAULT_DIR /
    "chess_learnings.md"
)

CHAT_HISTORY_PATH = (
    VAULT_DIR /
    "chat_history.json"
)

GAMES_PGN_PATH = (
    VAULT_DIR /
    "games.pgn"
)

APP_LOG_PATH = (
    VAULT_DIR /
    "jake_terminal.log"
)


STOCKFISH_PATH = (
    BASE_DIR /
    "stockfish.exe"
)


# ============================================================
# 6. LOGGING
# ============================================================

logger = logging.getLogger(
    "jake_mind_terminal"
)

logger.setLevel(
    logging.INFO
)

if not logger.handlers:

    file_handler = logging.FileHandler(
        APP_LOG_PATH,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    )

    file_handler.setFormatter(
        formatter
    )

    logger.addHandler(
        file_handler
    )


# ============================================================
# 7. SAFE FILE HELPERS
# ============================================================

def safe_read_text(
    path: Path,
    default: str = "",
) -> str:

    try:

        if not path.exists():
            return default

        return path.read_text(
            encoding="utf-8"
        )

    except Exception as exc:

        logger.exception(
            "Could not read %s",
            path,
        )

        return default


def safe_write_text(
    path: Path,
    content: str,
) -> bool:

    try:

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = (
            path.with_suffix(
                path.suffix + ".tmp"
            )
        )

        temporary_path.write_text(
            content,
            encoding="utf-8",
        )

        temporary_path.replace(
            path
        )

        return True

    except Exception:

        logger.exception(
            "Could not write %s",
            path,
        )

        return False


def safe_append_text(
    path: Path,
    content: str,
) -> bool:

    try:

        with path.open(
            "a",
            encoding="utf-8",
        ) as file:

            file.write(
                content
            )

        return True

    except Exception:

        logger.exception(
            "Could not append to %s",
            path,
        )

        return False


# ============================================================
# 8. INITIALIZE VAULT
# ============================================================

if not PHILOSOPHY_PATH.exists():

    safe_write_text(
        PHILOSOPHY_PATH,
        (
            "Identity: Jake (AI clone & Emotional Anchor).\n"
            "Core Philosophy: Stoic equilibrium.\n"
            "Chess Style: Calculated, positional and tactical.\n"
            "Development Philosophy: Learn through repeated games.\n"
        ),
    )


for empty_file in (
    IDEAS_LOG_PATH,
    POETRY_LOG_PATH,
    CHESS_LEARNINGS_PATH,
    GAMES_PGN_PATH,
):

    if not empty_file.exists():

        safe_write_text(
            empty_file,
            "",
        )


if not CHAT_HISTORY_PATH.exists():

    safe_write_text(
        CHAT_HISTORY_PATH,
        "[]",
    )


# ============================================================
# 9. SESSION STATE
# ============================================================

def initialize_session_state():

    defaults = {

        "board": chess.Board(),

        "chat_history": [],

        "undo_stack": [],

        "last_jake_move": None,

        "last_jake_reply": "",

        "last_move_san": None,

        "pending_board_move": None,

        "game_recorded": False,

        "game_started_at": datetime.now().isoformat(),

        "board_flipped": False,

        "difficulty_mode": "Adaptive",

        "tts_queue": None,

        "tts_thread": None,

        "tts_enabled": (
            os.environ.get(
                "JAKE_TTS",
                "1"
            ) == "1"
        ),

        "last_voice_hash": None,

    }

    for key, value in defaults.items():

        if key not in st.session_state:

            st.session_state[key] = value


initialize_session_state()


# ============================================================
# 10. PERSISTENT CHAT
# ============================================================

def load_chat_history():

    raw = safe_read_text(
        CHAT_HISTORY_PATH,
        "[]",
    )

    try:

        data = json.loads(
            raw
        )

        if not isinstance(
            data,
            list,
        ):
            return []

        cleaned = []

        for item in data:

            if not isinstance(
                item,
                dict,
            ):
                continue

            role = item.get(
                "role"
            )

            content = item.get(
                "content"
            )

            if role not in (
                "user",
                "assistant",
            ):
                continue

            if not isinstance(
                content,
                str,
            ):
                continue

            cleaned.append(
                {
                    "role": role,
                    "content": content,
                }
            )

        return cleaned[
            -100:
        ]

    except Exception:

        logger.exception(
            "Invalid chat history JSON."
        )

        return []


def save_chat_history():

    payload = (
        st.session_state.chat_history[
            -100:
        ]
    )

    safe_write_text(
        CHAT_HISTORY_PATH,
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
    )


if not st.session_state.chat_history:

    st.session_state.chat_history = (
        load_chat_history()
    )


def add_chat_message(
    role,
    content,
):

    if not content:
        return

    st.session_state.chat_history.append(
        {
            "role": role,
            "content": str(content),
        }
    )

    st.session_state.chat_history = (
        st.session_state.chat_history[
            -100:
        ]
    )

    save_chat_history()


# ============================================================
# 11. PHILOSOPHY
# ============================================================

def load_philosophy():

    return safe_read_text(
        PHILOSOPHY_PATH,
        (
            "Identity: Jake.\n"
            "Core Philosophy: Stoic equilibrium."
        ),
    ).strip()


# ============================================================
# 12. IDEAS VAULT
# ============================================================

def parse_ideas_file():

    content = safe_read_text(
        IDEAS_LOG_PATH
    )

    if not content.strip():
        return []

    blocks = re.split(
        r"(?=^###\s)",
        content,
        flags=re.MULTILINE,
    )

    ideas = []

    for block in blocks:

        block = block.strip()

        if not block:
            continue

        lines = block.splitlines()

        if not lines:
            continue

        heading = lines[0]

        title = re.sub(
            r"^###\s*",
            "",
            heading,
        ).strip()

        completed = (
            "[✅]" in title
        )

        title = re.sub(
            r"\[(?:✅|❌)\]\s*",
            "",
            title,
        ).strip()

        ideas.append(
            {
                "title": title,
                "completed": completed,
                "raw_block": block,
            }
        )

    return ideas


def rewrite_ideas_file(
    ideas,
):

    output = []

    for idea in ideas:

        prefix = (
            "[✅]"
            if idea["completed"]
            else "[❌]"
        )

        title = idea["title"].strip()

        raw_block = (
            idea.get(
                "raw_block",
                "",
            )
            .strip()
        )

        lines = raw_block.splitlines()

        rest = ""

        if len(lines) > 1:

            rest = "\n".join(
                lines[1:]
            ).strip()

        output.append(
            f"### {prefix} {title}\n"
        )

        if rest:

            output.append(
                f"{rest}\n"
            )

        output.append(
            "\n"
        )

    safe_write_text(
        IDEAS_LOG_PATH,
        "".join(output),
    )


# ============================================================
# 13. POETRY
# ============================================================

def save_poetry_line(
    poetry_text,
):

    poetry_text = (
        str(poetry_text)
        .strip()
    )

    if not poetry_text:
        return False

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    safe_append_text(
        POETRY_LOG_PATH,
        (
            "\n---\n"
            f"*Captured: {timestamp}*\n"
            f"> {poetry_text.replace(chr(10), chr(10) + '> ')}\n"
        ),
    )

    return True


# ============================================================
# 14. GROQ CONFIGURATION
# ============================================================

GROQ_API_KEY = (
    os.environ.get(
        "GROQ_API_KEY"
    )
)

if not GROQ_API_KEY:

    try:

        GROQ_API_KEY = (
            st.secrets.get(
                "GROQ_API_KEY"
            )
        )

    except Exception:

        GROQ_API_KEY = None


GROQ_MODEL = (
    os.environ.get(
        "GROQ_MODEL",
        "openai/gpt-oss-20b",
    )
)


GROQ_MAX_COMPLETION_TOKENS = int(
    os.environ.get(
        "GROQ_MAX_COMPLETION_TOKENS",
        "700",
    )
)


groq_client = None

if GROQ_API_KEY:

    try:

        groq_client = Groq(
            api_key=GROQ_API_KEY,
            timeout=30.0,
            max_retries=0,
        )

    except Exception:

        logger.exception(
            "Could not initialize Groq client."
        )


# ============================================================
# 15. GROQ MESSAGE SANITIZATION
# ============================================================

def clean_prompt_text(
    text,
    limit=6000,
):

    text = str(
        text or ""
    )

    text = text.replace(
        "\x00",
        "",
    )

    return text[
        -limit:
    ]


def build_recent_chat_messages():

    messages = []

    for item in (
        st.session_state.chat_history[
            -12:
        ]
    ):

        messages.append(
            {
                "role": item["role"],
                "content": clean_prompt_text(
                    item["content"],
                    2500,
                ),
            }
        )

    return messages


# ============================================================
# 16. GROQ CALL
# ============================================================

def ask_jake(
    user_message,
    system_prompt,
    temperature=0.65,
    max_tokens=None,
):

    if groq_client is None:

        return (
            "My Groq connection is not configured. "
            "Set GROQ_API_KEY in your environment or "
            "Streamlit secrets."
        )

    user_message = clean_prompt_text(
        user_message,
        6000,
    )

    system_prompt = clean_prompt_text(
        system_prompt,
        10000,
    )

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    messages.extend(
        build_recent_chat_messages()
    )

    messages.append(
        {
            "role": "user",
            "content": user_message,
        }
    )

    token_limit = (
        max_tokens
        or GROQ_MAX_COMPLETION_TOKENS
    )

    for attempt in range(3):

        try:

            started = time.perf_counter()

            response = (
                groq_client
                .chat
                .completions
                .create(
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=temperature,
                    max_completion_tokens=token_limit,
                    reasoning_effort="medium",
                )
            )

            elapsed = (
                time.perf_counter()
                - started
            )

            logger.info(
                "Groq request succeeded | "
                "model=%s | latency=%.2fs",
                GROQ_MODEL,
                elapsed,
            )

            content = (
                response
                .choices[0]
                .message
                .content
            )

            if not content:

                return (
                    "The language model returned "
                    "an empty response."
                )

            return content.strip()

        except Exception as exc:

            status_code = getattr(
                exc,
                "status_code",
                None,
            )

            logger.warning(
                "Groq request failed | "
                "attempt=%s | status=%s | error=%s",
                attempt + 1,
                status_code,
                type(exc).__name__,
            )

            if (
                status_code in (
                    400,
                    401,
                    403,
                    404,
                    422,
                )
            ):

                break

            if attempt < 2:

                time.sleep(
                    (2 ** attempt)
                    + random.random()
                )

    return (
        "Cloud interface handshake failed. "
        "Check the Groq API key, model name, "
        "network connection, or account limits."
    )


# ============================================================
# 17. DYNAMIC CHESS LEVELING
# ============================================================

LEVELS = [
    {
        "name": "Beginner",
        "min_games": 0,
        "skill": 2,
        "depth": 5,
    },
    {
        "name": "Novice",
        "min_games": 3,
        "skill": 5,
        "depth": 7,
    },
    {
        "name": "Club Player",
        "min_games": 8,
        "skill": 9,
        "depth": 10,
    },
    {
        "name": "Advanced",
        "min_games": 15,
        "skill": 13,
        "depth": 13,
    },
    {
        "name": "Expert",
        "min_games": 25,
        "skill": 16,
        "depth": 16,
    },
    {
        "name": "Master Candidate",
        "min_games": 40,
        "skill": 18,
        "depth": 19,
    },
    {
        "name": "Master",
        "min_games": 60,
        "skill": 20,
        "depth": 22,
    },
]


def count_completed_games():

    content = safe_read_text(
        CHESS_LEARNINGS_PATH
    )

    if not content.strip():
        return 0

    matches = re.findall(
        r"(?im)^\s*-\s*Result:\s*"
        r"(1-0|0-1|1/2-1/2)\s*$",
        content,
    )

    return len(matches)


def get_adaptive_profile(
    completed_games,
):

    selected = LEVELS[0]

    for level in LEVELS:

        if completed_games >= level[
            "min_games"
        ]:

            selected = level

    return {
        "name": selected["name"],
        "skill": selected["skill"],
        "depth": selected["depth"],
        "games": completed_games,
        "mode": "Adaptive",
    }


def get_difficulty_profile():

    completed_games = (
        count_completed_games()
    )

    mode = (
        st.session_state
        .difficulty_mode
    )

    adaptive = get_adaptive_profile(
        completed_games
    )

    if mode == "Adaptive":

        return adaptive

    fixed = {
        item["name"]: item
        for item in LEVELS
    }.get(
        mode,
        LEVELS[0],
    )

    return {
        "name": fixed["name"],
        "skill": fixed["skill"],
        "depth": fixed["depth"],
        "games": completed_games,
        "mode": "Manual",
    }


# ============================================================
# 18. STOCKFISH ENGINE
# ============================================================

@st.cache_resource(
    scope="session",
    on_release=lambda engine: (
        engine.quit()
        if engine is not None
        else None
    ),
)
def get_stockfish_engine(
    executable_path,
):

    if not executable_path:
        return None

    path = Path(
        executable_path
    )

    if not path.exists():
        return None

    try:

        engine = (
            chess.engine
            .SimpleEngine
            .popen_uci(
                str(path)
            )
        )

        logger.info(
            "Stockfish engine initialized."
        )

        return engine

    except Exception:

        logger.exception(
            "Stockfish initialization failed."
        )

        return None


stockfish_engine = get_stockfish_engine(
    str(STOCKFISH_PATH)
)


# ============================================================
# 19. STOCKFISH MOVE CALCULATION
# ============================================================

def calculate_jake_move(
    board,
):

    legal_moves = list(
        board.legal_moves
    )

    if not legal_moves:
        return None

    profile = get_difficulty_profile()

    if stockfish_engine is None:

        logger.warning(
            "Stockfish unavailable; "
            "using deterministic legal fallback."
        )

        return legal_moves[0]

    try:

        engine = stockfish_engine

        # ----------------------------------------------------
        # Skill level
        # ----------------------------------------------------

        try:

            engine.configure(
                {
                    "Skill Level": profile[
                        "skill"
                    ]
                }
            )

        except Exception:

            logger.exception(
                "Could not configure "
                "Stockfish Skill Level."
            )

        # ----------------------------------------------------
        # Search
        # ----------------------------------------------------

        result = engine.play(
            board,
            chess.engine.Limit(
                depth=profile["depth"]
            ),
        )

        if result.move:

            return result.move

    except Exception:

        logger.exception(
            "Stockfish calculation failed."
        )

    return legal_moves[0]


# ============================================================
# 20. TTS QUEUE
# ============================================================

def _tts_worker(
    speech_queue,
):

    try:

        engine = pyttsx3.init()

        engine.setProperty(
            "rate",
            160,
        )

        engine.setProperty(
            "volume",
            1.0,
        )

    except Exception:

        logger.exception(
            "Could not initialize pyttsx3."
        )

        return

    while True:

        text = (
            speech_queue
            .get()
        )

        if text is None:

            break

        try:

            clean = re.sub(
                r"[*#_`]",
                "",
                str(text),
            )

            clean = re.sub(
                r"\s+",
                " ",
                clean,
            ).strip()

            if clean:

                engine.say(
                    clean
                )

                engine.runAndWait()

        except Exception:

            logger.exception(
                "pyttsx3 speech failure."
            )

        finally:

            speech_queue.task_done()

    try:

        engine.stop()

    except Exception:

        pass


def ensure_tts_worker():

    if not st.session_state.tts_enabled:
        return

    if (
        st.session_state.tts_queue
        is None
    ):

        st.session_state.tts_queue = (
            queue.Queue()
        )

    thread = (
        st.session_state.tts_thread
    )

    if (
        thread is None
        or not thread.is_alive()
    ):

        thread = threading.Thread(
            target=_tts_worker,
            args=(
                st.session_state.tts_queue,
            ),
            daemon=True,
        )

        thread.start()

        st.session_state.tts_thread = (
            thread
        )


def jake_speak(
    text,
):

    if not text:
        return

    if not st.session_state.tts_enabled:
        return

    try:

        ensure_tts_worker()

        st.session_state.tts_queue.put(
            str(text)
        )

    except Exception:

        logger.exception(
            "Could not queue TTS speech."
        )


# ============================================================
# 21. BROWSER VOICE INPUT
# ============================================================

def transcribe_browser_audio(
    audio_file,
):

    if audio_file is None:
        return ""

    try:

        audio_bytes = (
            audio_file.getvalue()
        )

        recognizer = (
            sr.Recognizer()
        )

        with sr.AudioFile(
            io.BytesIO(
                audio_bytes
            )
        ) as source:

            audio = (
                recognizer.record(
                    source
                )
            )

        text = (
            recognizer
            .recognize_google(
                audio
            )
        )

        return text.strip()

    except sr.UnknownValueError:

        st.warning(
            "Jake could not understand "
            "that recording."
        )

    except sr.RequestError as exc:

        st.error(
            f"Speech recognition service "
            f"error: {exc}"
        )

    except Exception as exc:

        logger.exception(
            "Browser voice transcription failed."
        )

        st.error(
            f"Voice processing failed: {exc}"
        )

    return ""


# ============================================================
# 22. IDEAS THROUGH GROQ
# ============================================================

def process_and_save_idea(
    idea_text,
):

    idea_text = clean_prompt_text(
        idea_text,
        5000,
    ).strip()

    if not idea_text:
        return

    today = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    system_prompt = f"""
You are Jacob's intellectual vault assistant.

Transform the user's raw thought into a concise
knowledge-vault entry.

Return exactly:

[Core Idea Title]
- Date: {today}
- Summary: [precise two-sentence summary]

Do not add Markdown headings.
Do not add commentary.
Do not invent facts.
"""

    result = ask_jake(
        idea_text,
        system_prompt,
        temperature=0.3,
        max_tokens=250,
    )

    result = re.sub(
        r"^#+\s*",
        "",
        result,
    ).strip()

    safe_append_text(
        IDEAS_LOG_PATH,
        (
            "\n\n"
            f"### [❌] {result}\n"
        ),
    )


# ============================================================
# 23. CHESS COMMENTARY
# ============================================================

def generate_chess_commentary(
    board,
    move,
):

    profile = get_difficulty_profile()

    My_Philosophy = load_philosophy()

    san = "?"

    try:

        san = board.peek().uci()

    except Exception:

        pass

    system_prompt = f"""
You are Jake, an AI chess companion.

You are calm, analytical and concise.

Philosophy:
{My_Philosophy}

Current chess development:
- Level: {profile['name']}
- Completed games: {profile['games']}
- Stockfish skill: {profile['skill']}/20
- Search depth: {profile['depth']}

Jake just played:
{move.uci()}

Position after the move:
{board.fen()}

Explain why the move makes strategic or tactical sense.

Rules:
- Never invent pieces.
- Never claim a tactic that does not exist.
- Keep the answer to 2-3 sentences.
- Start with:
  "I play {move.uci()}."
"""

    return ask_jake(
        (
            "Analyze this chess position.\n"
            f"FEN: {board.fen()}"
        ),
        system_prompt,
        temperature=0.35,
        max_tokens=250,
    )


# ============================================================
# 24. PERSISTENT CHESS RECORDING
# ============================================================

def export_current_pgn(
    board,
    result="*",
):

    game = chess.pgn.Game()

    game.headers[
        "Event"
    ] = "Jake's Mind Terminal"

    game.headers[
        "Site"
    ] = "Local Streamlit Terminal"

    game.headers[
        "Date"
    ] = datetime.now().strftime(
        "%Y.%m.%d"
    )

    game.headers[
        "White"
    ] = "Jake"

    game.headers[
        "Black"
    ] = "You"

    game.headers[
        "Result"
    ] = result

    node = game

    replay_board = (
        chess.Board()
    )

    for move in board.move_stack:

        node = node.add_variation(
            move
        )

        replay_board.push(
            move
        )

    exporter = (
        chess.pgn.StringExporter(
            headers=True,
            variations=False,
            comments=False,
            columns=80,
        )
    )

    return game.accept(
        exporter
    )


def record_completed_game(
    board,
):

    if not board.is_game_over(
        claim_draw=True
    ):

        return

    if st.session_state.game_recorded:

        return

    outcome = board.outcome(
        claim_draw=True
    )

    if outcome is None:
        return

    result = outcome.result()

    termination = (
        outcome.termination
        .name
        .replace(
            "_",
            " ",
        )
        .title()
    )

    profile = get_difficulty_profile()

    timestamp = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    pgn = export_current_pgn(
        board,
        result,
    )

    game_number = (
        count_completed_games()
        + 1
    )

    learning_entry = (
        "\n\n"
        f"## Completed Game {game_number}\n\n"
        f"- Date: {timestamp}\n"
        f"- Result: {result}\n"
        f"- Termination: {termination}\n"
        f"- Final FEN: `{board.fen()}`\n"
        f"- Jake Level: {profile['name']}\n"
        f"- Jake Skill: {profile['skill']}/20\n"
        f"- Jake Depth: {profile['depth']}\n"
        f"- Moves: {board.fullmove_number}\n"
        "- Lesson: Game completed and added "
        "to Jake's developmental history.\n"
    )

    safe_append_text(
        CHESS_LEARNINGS_PATH,
        learning_entry,
    )

    safe_append_text(
        GAMES_PGN_PATH,
        "\n\n" + pgn + "\n",
    )

    st.session_state.game_recorded = True

    logger.info(
        "Completed chess game recorded | "
        "game=%s | result=%s | level=%s",
        game_number,
        result,
        profile["name"],
    )


# ============================================================
# 25. UNDO
# ============================================================

def undo_last_turn():

    if not st.session_state.undo_stack:

        st.warning(
            "There is no completed turn to undo."
        )

        return False

    previous_board = (
        st.session_state.undo_stack.pop()
    )

    st.session_state.board = (
        previous_board.copy(
            stack=True
        )
    )

    st.session_state.last_jake_move = None

    st.session_state.last_jake_reply = ""

    st.session_state.last_move_san = None

    st.session_state.game_recorded = False

    add_chat_message(
        "assistant",
        "↩️ The last complete turn has been undone.",
    )

    return True


# ============================================================
# 26. RESET GAME
# ============================================================

def reset_game():

    st.session_state.board = (
        chess.Board()
    )

    st.session_state.undo_stack = []

    st.session_state.last_jake_move = None

    st.session_state.last_jake_reply = ""

    st.session_state.last_move_san = None

    st.session_state.game_recorded = False

    st.session_state.game_started_at = (
        datetime.now().isoformat()
    )

    add_chat_message(
        "assistant",
        "♟ New chess game initialized. Jake will calculate first.",
    )


# ============================================================
# 27. APPLY USER MOVE
# ============================================================

def apply_user_move(
    uci_move,
):

    board = st.session_state.board

    if board.is_game_over(
        claim_draw=True
    ):

        st.warning(
            "The game is already over."
        )

        return False

    if board.turn != chess.BLACK:

        st.warning(
            "It is currently Jake's turn."
        )

        return False

    try:

        move = chess.Move.from_uci(
            uci_move
        )

    except ValueError:

        st.error(
            f"Invalid chess move: {uci_move}"
        )

        return False

    if move not in board.legal_moves:

        st.error(
            "That move is not legal in the current position."
        )

        return False

    # --------------------------------------------------------
    # Save position BEFORE user's move.
    # This makes Undo restore the complete turn.
    # --------------------------------------------------------

    st.session_state.undo_stack.append(
        board.copy(
            stack=True
        )
    )

    try:

        san = board.san(
            move
        )

        board.push(
            move
        )

    except Exception:

        logger.exception(
            "Could not apply user move."
        )

        st.session_state.undo_stack.pop()

        st.error(
            "The move could not be applied."
        )

        return False

    st.session_state.last_move_san = (
        san
    )

    add_chat_message(
        "user",
        f"I play **{san}** (`{uci_move}`).",
    )

    # --------------------------------------------------------
    # User ended game
    # --------------------------------------------------------

    if board.is_game_over(
        claim_draw=True
    ):

        record_completed_game(
            board
        )

        return True

    return True


# ============================================================
# 28. PLAY JAKE TURN
# ============================================================

def play_jake_turn():

    board = st.session_state.board

    if board.is_game_over(
        claim_draw=True
    ):

        return False

    if board.turn != chess.WHITE:

        return False

    move = calculate_jake_move(
        board
    )

    if move is None:
        return False

    try:

        san = board.san(
            move
        )

        board.push(
            move
        )

    except Exception:

        logger.exception(
            "Could not apply Jake's move."
        )

        return False

    st.session_state.last_jake_move = (
        move.uci()
    )

    st.session_state.last_move_san = (
        san
    )

    add_chat_message(
        "assistant",
        f"♟ Jake plays **{san}** (`{move.uci()}`).",
    )

    profile = get_difficulty_profile()

    with st.spinner(
        "Jake is calculating the position..."
    ):

        commentary = (
            generate_chess_commentary(
                board,
                move,
            )
        )

    st.session_state.last_jake_reply = (
        commentary
    )

    add_chat_message(
        "assistant",
        commentary,
    )

    jake_speak(
        commentary
    )

    if board.is_game_over(
        claim_draw=True
    ):

        record_completed_game(
            board
        )

    logger.info(
        "Jake move | "
        "move=%s | level=%s | skill=%s | depth=%s",
        move.uci(),
        profile["name"],
        profile["skill"],
        profile["depth"],
    )

    return True


# ============================================================
# 29. CHAT RESPONSE
# ============================================================

def generate_chat_response(
    user_message,
):

    board = st.session_state.board

    profile = get_difficulty_profile()

    My_Philosophy = load_philosophy()

    system_prompt = f"""
You are Jake, the personal AI companion of Jacob.

Core philosophy:
{My_Philosophy}

Communication style:
- calm
- grounded
- emotionally balanced
- thoughtful
- concise
- honest

Current chess state:
FEN: {board.fen()}
Turn: {"Jake" if board.turn == chess.WHITE else "You"}

Jake chess development:
- Level: {profile['name']}
- Completed games: {profile['games']}
- Skill: {profile['skill']}/20
- Depth: {profile['depth']}

If the user discusses chess:
provide accurate tactical and positional reasoning.

If the user discusses poetry:
be thoughtful and creative.

If the user discusses ideas:
help organize and develop them.

Do not pretend to have memories that are not supplied.
Do not reveal API keys or internal configuration.
"""

    return ask_jake(
        user_message,
        system_prompt,
        temperature=0.65,
        max_tokens=600,
    )


# ============================================================
# 30. INTERACTIVE CHESSBOARD COMPONENT
# ============================================================

if COMPONENTS_V2_AVAILABLE:

    CHESSBOARD_HTML = """
    <div class="jake-board-shell">

        <div id="board"></div>

        <div
            id="promotion-panel"
            class="promotion-panel hidden"
        ></div>

        <div
            id="board-message"
            class="board-message"
        ></div>

    </div>
    """

    CHESSBOARD_CSS = """

    .jake-board-shell {
        width: 100%;
        max-width: 620px;
        margin: 0 auto;
        position: relative;
        font-family: var(--st-font);
    }

    #board {
        width: 100%;
        aspect-ratio: 1 / 1;
        display: grid;
        grid-template-columns: repeat(8, 1fr);
        border-radius: 12px;
        overflow: hidden;
        box-shadow:
            0 14px 40px rgba(0,0,0,.30);
        border: 2px solid rgba(255,255,255,.12);
    }

    .square {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        user-select: none;
        -webkit-user-select: none;
        transition:
            filter .12s ease,
            background .12s ease;
    }

    .square:hover {
        filter: brightness(1.08);
    }

    .light {
        background: #f0d9b5;
    }

    .dark {
        background: #b58863;
    }

    .selected {
        background: #f6f669 !important;
    }

    .legal {
        box-shadow:
            inset 0 0 0 5px
            rgba(40,180,80,.65);
    }

    .last-move {
        background:
            linear-gradient(
                rgba(246,246,105,.45),
                rgba(246,246,105,.45)
            );
    }

    .piece {
        font-size: clamp(
            30px,
            7vw,
            68px
        );
        line-height: 1;
        pointer-events: none;
        text-shadow:
            1px 2px 2px
            rgba(0,0,0,.28);
    }

    .white-piece {
        color: #fff;
    }

    .black-piece {
        color: #111;
    }

    .coordinate {
        position: absolute;
        font-size: 10px;
        right: 4px;
        bottom: 3px;
        opacity: .65;
        pointer-events: none;
    }

    .light .coordinate {
        color: #805d38;
    }

    .dark .coordinate {
        color: #f3dfc4;
    }

    .promotion-panel {
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        z-index: 20;

        display: flex;
        gap: 8px;

        padding: 12px;

        border-radius: 12px;

        background:
            var(--st-secondary-background-color);

        border:
            1px solid
            var(--st-border-color);

        box-shadow:
            0 12px 40px
            rgba(0,0,0,.35);
    }

    .promotion-panel.hidden {
        display: none;
    }

    .promotion-button {
        width: 58px;
        height: 58px;

        border: 0;
        border-radius: 8px;

        font-size: 38px;

        cursor: pointer;

        background:
            var(--st-background-color);

        color:
            var(--st-text-color);
    }

    .promotion-button:hover {
        background:
            var(--st-primary-color);
        color: white;
    }

    .board-message {
        min-height: 24px;
        margin-top: 6px;
        text-align: center;
        color: var(--st-secondary-text-color);
        font-size: 0.85rem;
    }

    """

    CHESSBOARD_JS = """

    export default function(component) {

        const {
            parentElement,
            data,
            setTriggerValue
        } = component;

        const boardElement =
            parentElement.querySelector("#board");

        const promotionPanel =
            parentElement.querySelector(
                "#promotion-panel"
            );

        const message =
            parentElement.querySelector(
                "#board-message"
            );

        const unicode = {
            "K": "♔",
            "Q": "♕",
            "R": "♖",
            "B": "♗",
            "N": "♘",
            "P": "♙",

            "k": "♚",
            "q": "♛",
            "r": "♜",
            "b": "♝",
            "n": "♞",
            "p": "♟"
        };

        const files =
            ["a","b","c","d","e","f","g","h"];

        const ranks =
            ["8","7","6","5","4","3","2","1"];

        const orientation =
            data?.orientation || "white";

        const pieces =
            data?.pieces || {};

        const legalMoves =
            data?.legal_moves || [];

        const turn =
            data?.turn || "white";

        const userColor =
            data?.user_color || "black";

        const lastMove =
            data?.last_move || null;

        let selected = null;

        let promotionBase = null;


        function orderedSquares() {

            const result = [];

            const fileOrder =
                orientation === "white"
                ? files
                : [...files].reverse();

            const rankOrder =
                orientation === "white"
                ? ranks
                : [...ranks].reverse();

            for (
                const rank of rankOrder
            ) {

                for (
                    const file of fileOrder
                ) {

                    result.push(
                        file + rank
                    );
                }
            }

            return result;
        }


        function clearBoard() {

            while (
                boardElement.firstChild
            ) {

                boardElement.removeChild(
                    boardElement.firstChild
                );
            }
        }


        function squareColor(
            square
        ) {

            const fileIndex =
                files.indexOf(
                    square[0]
                );

            const rankIndex =
                ranks.indexOf(
                    square[1]
                );

            return (
                (fileIndex + rankIndex) % 2
                === 0
            )
            ? "light"
            : "dark";
        }


        function isOwnPiece(
            square
        ) {

            const piece =
                pieces[square];

            if (!piece) {
                return false;
            }

            if (
                userColor === "white"
            ) {

                return (
                    piece ===
                    piece.toUpperCase()
                );
            }

            return (
                piece ===
                piece.toLowerCase()
            );
        }


        function movesFrom(
            square
        ) {

            return legalMoves.filter(
                move =>
                    move.startsWith(
                        square
                    )
            );
        }


        function clearPromotion() {

            promotionPanel.classList.add(
                "hidden"
            );

            while (
                promotionPanel.firstChild
            ) {

                promotionPanel.removeChild(
                    promotionPanel.firstChild
                );
            }

            promotionBase = null;
        }


        function showPromotion(
            baseMove,
            options
        ) {

            promotionBase =
                baseMove;

            while (
                promotionPanel.firstChild
            ) {

                promotionPanel.removeChild(
                    promotionPanel.firstChild
                );
            }

            const piecesForPromotion = {
                "q": "♕",
                "r": "♖",
                "b": "♗",
                "n": "♘"
            };

            for (
                const option of options
            ) {

                const button =
                    document.createElement(
                        "button"
                    );

                button.className =
                    "promotion-button";

                const promotionPiece =
                    option[4];

                button.textContent =
                    piecesForPromotion[
                        promotionPiece
                    ];

                button.title =
                    "Promote to " +
                    promotionPiece;

                button.onclick = () => {

                    setTriggerValue(
                        "move",
                        option
                    );

                    clearPromotion();
                };

                promotionPanel.appendChild(
                    button
                );
            }

            promotionPanel.classList.remove(
                "hidden"
            );
        }


        function handleClick(
            square
        ) {

            if (
                turn !== userColor
            ) {

                message.textContent =
                    "Jake is calculating.";

                return;
            }

            if (
                !selected
            ) {

                if (
                    !isOwnPiece(square)
                ) {

                    message.textContent =
                        "Select one of your pieces.";

                    return;
                }

                selected = square;

                render();

                message.textContent =
                    "Choose a destination.";

                return;
            }


            if (
                selected === square
            ) {

                selected = null;

                render();

                return;
            }


            const base =
                selected + square;


            const matching =
                legalMoves.filter(
                    move =>
                        move.startsWith(
                            base
                        )
                );


            if (
                matching.length === 0
            ) {

                if (
                    isOwnPiece(square)
                ) {

                    selected = square;

                    render();

                    return;
                }

                message.textContent =
                    "That move is not legal.";

                selected = null;

                render();

                return;
            }


            /*
             * Promotion.
             */

            if (
                matching.length > 1
            ) {

                showPromotion(
                    base,
                    matching
                );

                return;
            }


            setTriggerValue(
                "move",
                matching[0]
            );

            selected = null;

            message.textContent =
                "Move submitted.";
        }


        function render() {

            clearBoard();

            clearPromotion();

            const squares =
                orderedSquares();


            for (
                const square of squares
            ) {

                const element =
                    document.createElement(
                        "div"
                    );

                element.className =
                    "square " +
                    squareColor(square);


                if (
                    lastMove &&
                    (
                        square ===
                        lastMove.slice(0,2)
                        ||
                        square ===
                        lastMove.slice(2,4)
                    )
                ) {

                    element.classList.add(
                        "last-move"
                    );
                }


                if (
                    selected === square
                ) {

                    element.classList.add(
                        "selected"
                    );
                }


                if (
                    selected &&
                    legalMoves.some(
                        move =>
                            move.startsWith(
                                selected + square
                            )
                    )
                ) {

                    element.classList.add(
                        "legal"
                    );
                }


                const piece =
                    pieces[square];


                if (piece) {

                    const pieceElement =
                        document.createElement(
                            "div"
                        );

                    pieceElement.className =
                        "piece " +
                        (
                            piece ===
                            piece.toUpperCase()
                            ? "white-piece"
                            : "black-piece"
                        );

                    pieceElement.textContent =
                        unicode[piece];

                    element.appendChild(
                        pieceElement
                    );
                }


                const coordinate =
                    document.createElement(
                        "div"
                    );

                coordinate.className =
                    "coordinate";

                coordinate.textContent =
                    square;

                element.appendChild(
                    coordinate
                );


                element.onclick = () =>
                    handleClick(square);


                boardElement.appendChild(
                    element
                );
            }


            if (
                turn !== userColor
            ) {

                message.textContent =
                    "Jake is calculating...";

            } else {

                message.textContent =
                    "Your move — click a piece.";
            }
        }


        render();
    }
    """

    chessboard_component = (
        components_v2.component(
            name="jake_interactive_chessboard",
            html=CHESSBOARD_HTML,
            css=CHESSBOARD_CSS,
            js=CHESSBOARD_JS,
        )
    )

else:

    chessboard_component = None


# ============================================================
# 31. CHESSBOARD DATA
# ============================================================

def get_board_component_data(
    board,
):

    pieces = {}

    for square, piece in (
        board.piece_map().items()
    ):

        pieces[
            chess.square_name(square)
        ] = piece.symbol()

    legal_moves = [
        move.uci()
        for move in board.legal_moves
    ]

    last_move = None

    if board.move_stack:

        last_move = (
            board.move_stack[-1]
            .uci()
        )

    return {
        "pieces": pieces,
        "legal_moves": legal_moves,
        "turn": (
            "white"
            if board.turn == chess.WHITE
            else "black"
        ),
        "user_color": "black",
        "orientation": (
            "black"
            if st.session_state.board_flipped
            else "white"
        ),
        "last_move": last_move,
    }


# ============================================================
# 32. BOARD MOVE CALLBACK
# ============================================================

def on_board_move():

    component_state = (
        st.session_state.get(
            "jake_chessboard",
            {},
        )
    )

    move = None

    try:

        move = component_state.get(
            "move"
        )

    except Exception:

        try:

            move = component_state.move

        except Exception:

            move = None

    if move:

        st.session_state.pending_board_move = (
            move
        )


# ============================================================
# 33. PROCESS PENDING BOARD MOVE
# ============================================================

if (
    st.session_state.pending_board_move
):

    pending_move = (
        st.session_state.pending_board_move
    )

    st.session_state.pending_board_move = (
        None
    )

    if apply_user_move(
        pending_move
    ):

        if (
            st.session_state.board.turn
            == chess.WHITE
            and not st.session_state.board.is_game_over(
                claim_draw=True
            )
        ):

            play_jake_turn()


# ============================================================
# 34. INITIAL JAKE MOVE
# ============================================================

if (
    st.session_state.board.turn
    == chess.WHITE
    and not st.session_state.board.is_game_over(
        claim_draw=True
    )
    and not st.session_state.board.move_stack
):

    play_jake_turn()


# ============================================================
# 35. MAIN HEADER
# ============================================================

st.title(
    "🧠 Jake's Mind Terminal"
)

st.caption(
    "Chess • Ideas • Poetry • Philosophy • Voice"
)


# ============================================================
# 36. SIDEBAR
# ============================================================

with st.sidebar:

    st.header(
        "Jake Control Core"
    )

    profile = get_difficulty_profile()

    if groq_client:

        st.success(
            f"Groq online — `{GROQ_MODEL}`"
        )

    else:

        st.error(
            "Groq API not configured"
        )

    st.markdown("---")

    st.subheader(
        "♟ Chess Evolution"
    )

    st.metric(
        "Completed Games",
        profile["games"],
    )

    st.metric(
        "Jake Level",
        profile["name"],
    )

    st.progress(
        profile["skill"] / 20
    )

    st.caption(
        f"Skill: {profile['skill']}/20"
    )

    st.caption(
        f"Depth: {profile['depth']}"
    )

    st.markdown("---")

    st.subheader(
        "🎚 Difficulty"
    )

    difficulty_options = [
        "Adaptive",
        "Beginner",
        "Novice",
        "Club Player",
        "Advanced",
        "Expert",
        "Master Candidate",
        "Master",
    ]

    selected_difficulty = st.selectbox(
        "Jake's strength",
        difficulty_options,
        index=difficulty_options.index(
            st.session_state.difficulty_mode
        ),
        key="difficulty_selector",
    )

    st.session_state.difficulty_mode = (
        selected_difficulty
    )

    if selected_difficulty == "Adaptive":

        st.caption(
            "Jake's strength automatically grows "
            "with completed games."
        )

    else:

        st.caption(
            "Manual mode temporarily overrides "
            "the adaptive learning curve."
        )

    st.markdown("---")

    st.subheader(
        "🔊 Voice"
    )

    st.session_state.tts_enabled = (
        st.checkbox(
            "Enable Jake's voice",
            value=(
                st.session_state.tts_enabled
            ),
            key="tts_toggle",
        )
    )

    st.caption(
        "Voice output uses pyttsx3 on the machine "
        "running Streamlit."
    )

    st.markdown("---")

    if st.button(
        "🧹 Clear Persistent Chat",
        use_container_width=True,
    ):

        st.session_state.chat_history = []

        save_chat_history()

        st.rerun()

    if st.button(
        "🔄 New Chess Game",
        use_container_width=True,
    ):

        reset_game()

        st.rerun()


# ============================================================
# 37. TWO COLUMN MAIN TERMINAL
# ============================================================

left_column, right_column = st.columns(
    [1.05, 1],
    gap="large",
)


# ============================================================
# 38. LEFT — CHESS
# ============================================================

with left_column:

    st.header(
        "♟ Jake vs You"
    )

    profile = get_difficulty_profile()

    st.info(
        f"**{profile['name']}**  •  "
        f"{profile['games']} games  •  "
        f"Skill {profile['skill']}/20  •  "
        f"Depth {profile['depth']}"
    )

    board = (
        st.session_state.board
    )

    if (
        chessboard_component
        is not None
    ):

        chessboard_component(
            data=get_board_component_data(
                board
            ),
            key="jake_chessboard",
            on_move_change=on_board_move,
        )

    else:

        st.error(
            "Interactive chess requires "
            "Streamlit 1.52+."
        )

        st.info(
            "Upgrade Streamlit with: "
            "`pip install --upgrade streamlit`"
        )

    st.markdown(
        f"**Turn:** "
        f"{'Jake — White' if board.turn == chess.WHITE else 'You — Black'}"
    )

    if st.session_state.last_jake_move:

        st.success(
            f"Jake's last move: "
            f"**{st.session_state.last_jake_move}**"
        )

    if st.session_state.last_jake_reply:

        with st.expander(
            "🧠 Jake's Chess Analysis",
            expanded=True,
        ):

            st.markdown(
                st.session_state.last_jake_reply
            )

    # --------------------------------------------------------
    # Board controls
    # --------------------------------------------------------

    board_col1, board_col2, board_col3 = (
        st.columns(3)
    )

    with board_col1:

        if st.button(
            "↩️ Undo Turn",
            use_container_width=True,
            disabled=(
                not st.session_state.undo_stack
                or board.is_game_over(
                    claim_draw=True
                )
            ),
        ):

            if undo_last_turn():

                st.rerun()

    with board_col2:

        if st.button(
            "🔄 Reset",
            use_container_width=True,
        ):

            reset_game()

            st.rerun()

    with board_col3:

        if st.button(
            "🔃 Flip Board",
            use_container_width=True,
        ):

            st.session_state.board_flipped = (
                not st.session_state.board_flipped
            )

            st.rerun()

    # --------------------------------------------------------
    # Game status
    # --------------------------------------------------------

    if board.is_game_over(
        claim_draw=True
    ):

        outcome = board.outcome(
            claim_draw=True
        )

        if outcome:

            result = outcome.result()

            st.success(
                f"🏁 Game Over — **{result}**"
            )

            st.caption(
                "Termination: "
                + outcome.termination.name
                .replace(
                    "_",
                    " ",
                )
                .title()
            )

    # --------------------------------------------------------
    # Move history
    # --------------------------------------------------------

    with st.expander(
        "📜 Move History",
        expanded=False,
    ):

        if board.move_stack:

            history_board = (
                chess.Board()
            )

            move_rows = []

            for index, move in enumerate(
                board.move_stack
            ):

                move_number = (
                    history_board.fullmove_number
                )

                san = history_board.san(
                    move
                )

                history_board.push(
                    move
                )

                move_rows.append(
                    (
                        move_number,
                        "White"
                        if index % 2 == 0
                        else "Black",
                        san,
                    )
                )

            for row in move_rows:

                st.write(
                    f"**{row[0]}.** "
                    f"{row[1]} — `{row[2]}`"
                )

        else:

            st.caption(
                "No moves yet."
            )

    # --------------------------------------------------------
    # PGN export
    # --------------------------------------------------------

    pgn_text = export_current_pgn(
        board,
        (
            board.result(
                claim_draw=True
            )
            if board.is_game_over(
                claim_draw=True
            )
            else "*"
        ),
    )

    st.download_button(
        "⬇️ Download Current PGN",
        data=pgn_text,
        file_name="jake_chess_game.pgn",
        mime="application/x-chess-pgn",
        use_container_width=True,
        on_click="ignore",
    )


# ============================================================
# 39. RIGHT COLUMN — THREE ROWS
# ============================================================

with right_column:

    # ========================================================
    # ROW 1 — IDEAS
    # ========================================================

    st.header(
        "💡 Ideas & Jake"
    )

    current_ideas = (
        parse_ideas_file()
    )

    total_ideas = len(
        current_ideas
    )

    completed_ideas = sum(
        1
        for idea in current_ideas
        if idea["completed"]
    )

    pending_ideas = (
        total_ideas
        - completed_ideas
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Insights",
        total_ideas,
    )

    m2.metric(
        "Pending",
        pending_ideas,
    )

    m3.metric(
        "Complete",
        completed_ideas,
    )

    idea_text = st.text_area(
        "Capture an idea",
        placeholder=(
            "Give Jake a thought, concept, "
            "observation or problem..."
        ),
        height=110,
        key="idea_entry",
    )

    idea_col1, idea_col2 = st.columns(2)

    with idea_col1:

        if st.button(
            "💡 Index Idea",
            use_container_width=True,
        ):

            if idea_text.strip():

                process_and_save_idea(
                    idea_text
                )

                st.success(
                    "Idea indexed."
                )

                st.rerun()

            else:

                st.warning(
                    "Enter an idea first."
                )

    with idea_col2:

        audio_value = st.audio_input(
            "🎙 Voice idea",
            sample_rate=16000,
            key="idea_voice",
            label_visibility="collapsed",
        )

        if audio_value:

            audio_hash = hash(
                audio_value.getvalue()
            )

            if (
                audio_hash
                != st.session_state.last_voice_hash
            ):

                st.session_state.last_voice_hash = (
                    audio_hash
                )

                with st.spinner(
                    "Jake is transcribing..."
                ):

                    spoken_idea = (
                        transcribe_browser_audio(
                            audio_value
                        )
                    )

                if spoken_idea:

                    process_and_save_idea(
                        spoken_idea
                    )

                    st.success(
                        f"Indexed: {spoken_idea}"
                    )

                    st.rerun()

    with st.expander(
        "📚 Active Idea Vault",
        expanded=False,
    ):

        if current_ideas:

            changed = False

            for index, idea in enumerate(
                current_ideas
            ):

                checked = st.checkbox(
                    idea["title"],
                    value=idea["completed"],
                    key=f"idea_check_{index}",
                )

                if (
                    checked
                    != idea["completed"]
                ):

                    current_ideas[index][
                        "completed"
                    ] = checked

                    changed = True

            if changed:

                rewrite_ideas_file(
                    current_ideas
                )

                st.rerun()

        else:

            st.caption(
                "Your idea vault is empty."
            )


    st.markdown("---")


    # ========================================================
    # ROW 2 — POETRY
    # ========================================================

    st.header(
        "🖋 Poetry & Reflection"
    )

    poem = st.text_area(
        "Poetry line",
        placeholder=(
            "Write something worth remembering..."
        ),
        height=150,
        key="poetry_entry",
    )

    if st.button(
        "✨ Lock Verse Into Journal",
        use_container_width=True,
    ):

        if poem.strip():

            save_poetry_line(
                poem
            )

            st.success(
                "Verse captured."
            )

            st.rerun()

        else:

            st.warning(
                "Enter a verse first."
            )

    with st.expander(
        "📖 Poetry Journal",
        expanded=False,
    ):

        poetry_content = safe_read_text(
            POETRY_LOG_PATH
        )

        if poetry_content.strip():

            st.markdown(
                poetry_content
            )

        else:

            st.caption(
                "No poetry has been recorded yet."
            )


    st.markdown("---")


    # ========================================================
    # ROW 3 — CHAT HISTORY
    # ========================================================

    st.header(
        "💬 Conversation With Jake"
    )

    chat_container = st.container(
        height=420,
        border=True,
    )

    with chat_container:

        if (
            st.session_state.chat_history
        ):

            for message in (
                st.session_state.chat_history
            ):

                role = message.get(
                    "role",
                    "assistant",
                )

                content = message.get(
                    "content",
                    "",
                )

                with st.chat_message(
                    role
                ):

                    st.markdown(
                        content
                    )

        else:

            st.caption(
                "No conversation yet."
            )

    # --------------------------------------------------------
    # Chat input
    # --------------------------------------------------------

    chat_text = st.chat_input(
        "Speak with Jake..."
    )

    if chat_text:

        add_chat_message(
            "user",
            chat_text,
        )

        with st.spinner(
            "Jake is thinking..."
        ):

            response = (
                generate_chat_response(
                    chat_text
                )
            )

        add_chat_message(
            "assistant",
            response,
        )

        jake_speak(
            response
        )

        st.rerun()


# ============================================================
# 40. GLOBAL STYLING
# ============================================================

st.markdown(
    """
    <style>

    /*
    =========================================================
    General terminal styling
    =========================================================
    */

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 3rem;
    }


    /*
    =========================================================
    Sticky chess column
    =========================================================
    */

    @media (min-width: 901px) {

        [data-testid="stHorizontalBlock"]
        > [data-testid="column"]:first-child {

            position: sticky;
            top: 1rem;

            align-self: flex-start;

            height: fit-content;
        }

    }


    /*
    =========================================================
    Responsive fallback
    =========================================================
    */

    @media (max-width: 900px) {

        [data-testid="stHorizontalBlock"] {

            flex-direction: column;
        }

    }


    /*
    =========================================================
    Metrics
    =========================================================
    */

    [data-testid="stMetric"] {

        border-radius: 10px;

        padding: .5rem;

        background:
            rgba(128,128,128,.06);
    }


    /*
    =========================================================
    Buttons
    =========================================================
    */

    .stButton > button {

        border-radius: 8px;

        transition:
            transform .1s ease,
            box-shadow .1s ease;
    }

    .stButton > button:hover {

        transform:
            translateY(-1px);

        box-shadow:
            0 4px 12px
            rgba(0,0,0,.15);
    }


    /*
    =========================================================
    Chat container
    =========================================================
    */

    [data-testid="stVerticalBlockBorderWrapper"] {

        border-radius: 12px;
    }


    /*
    =========================================================
    Mobile chessboard
    =========================================================
    */

    @media (max-width: 600px) {

        .block-container {

            padding-left: .75rem;
            padding-right: .75rem;
        }

    }

    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# END OF APPLICATION
# ============================================================