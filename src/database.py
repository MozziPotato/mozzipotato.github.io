"""SQLite database connection and schema management."""

import logging
import sqlite3
from pathlib import Path

from src.config import get_config, get_project_root

logger = logging.getLogger(__name__)

_connection = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL UNIQUE,
    search_volume_hint TEXT,
    competition_hint TEXT,
    niche TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT DEFAULT 'discovered',
    naver_trend_score REAL,
    google_trend_score REAL,
    trend_direction TEXT,
    combined_trend_score REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    word_count INTEGER,
    status TEXT DEFAULT 'draft',
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    date DATE NOT NULL,
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    ctr REAL DEFAULT 0.0,
    avg_position REAL DEFAULT 0.0,
    UNIQUE(post_id, date)
);

CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS keyword_intents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    search_intent TEXT NOT NULL,
    intent_detail TEXT,
    target_audience TEXT,
    trend_context TEXT,
    content_angle TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(keyword_id)
);

CREATE TABLE IF NOT EXISTS post_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    seo_score INTEGER,
    adsense_score INTEGER,
    humanlike_score INTEGER,
    readability_score INTEGER,
    style_score INTEGER,
    audience_score INTEGER,
    overall_score INTEGER,
    issues TEXT,
    suggestions TEXT,
    passed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(post_id)
);
"""


def get_db() -> sqlite3.Connection:
    global _connection
    if _connection is not None:
        return _connection

    config = get_config()
    db_path = get_project_root() / config["database"]["path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _connection = sqlite3.connect(str(db_path))
    _connection.row_factory = sqlite3.Row
    _connection.execute("PRAGMA journal_mode=WAL")
    _connection.execute("PRAGMA foreign_keys=ON")

    return _connection


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    # Migrate existing DB: add trend columns if missing
    _migrate_trend_columns(db)
    db.commit()


def _migrate_trend_columns(db: sqlite3.Connection):
    """Add trend columns to keywords table if they don't exist (backward compat)."""
    cursor = db.execute("PRAGMA table_info(keywords)")
    existing = {row[1] for row in cursor.fetchall()}
    new_columns = [
        ("naver_trend_score", "REAL"),
        ("google_trend_score", "REAL"),
        ("trend_direction", "TEXT"),
        ("combined_trend_score", "REAL"),
    ]
    for col_name, col_type in new_columns:
        if col_name not in existing:
            db.execute(f"ALTER TABLE keywords ADD COLUMN {col_name} {col_type}")
            logger.info(f"Migrated: added {col_name} column to keywords table")


def close_db():
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


# --- Keyword operations ---

def add_keyword(keyword: str, niche: str, source: str,
                volume_hint: str = None, competition_hint: str = None,
                naver_trend_score: float = None, google_trend_score: float = None,
                trend_direction: str = None, combined_trend_score: float = None) -> int | None:
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO keywords (keyword, niche, source, search_volume_hint, competition_hint, "
            "naver_trend_score, google_trend_score, trend_direction, combined_trend_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (keyword, niche, source, volume_hint, competition_hint,
             naver_trend_score, google_trend_score, trend_direction, combined_trend_score)
        )
        db.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None


def get_approved_keywords(limit: int = 10) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM keywords WHERE status = 'approved' ORDER BY created_at LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def get_discovered_keywords(limit: int = 50) -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT * FROM keywords WHERE status = 'discovered' ORDER BY created_at LIMIT ?",
        (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def update_keyword_status(keyword_id: int, status: str):
    db = get_db()
    db.execute("UPDATE keywords SET status = ? WHERE id = ?", (status, keyword_id))
    db.commit()


def count_keywords_by_status(status: str) -> int:
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) as cnt FROM keywords WHERE status = ?", (status,)
    ).fetchone()
    return row["cnt"]


def update_keyword_trends(keyword_id: int, naver_trend_score: float = None,
                          google_trend_score: float = None,
                          trend_direction: str = None,
                          combined_trend_score: float = None):
    """Update trend data for an existing keyword."""
    db = get_db()
    db.execute(
        "UPDATE keywords SET naver_trend_score = ?, google_trend_score = ?, "
        "trend_direction = ?, combined_trend_score = ? WHERE id = ?",
        (naver_trend_score, google_trend_score, trend_direction,
         combined_trend_score, keyword_id)
    )
    db.commit()


# --- Post operations ---

def add_post(keyword_id: int, title: str, slug: str,
             file_path: str, word_count: int) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO posts (keyword_id, title, slug, file_path, word_count) "
        "VALUES (?, ?, ?, ?, ?)",
        (keyword_id, title, slug, file_path, word_count)
    )
    db.commit()
    return cursor.lastrowid


def update_post_status(post_id: int, status: str):
    db = get_db()
    if status == "published":
        db.execute(
            "UPDATE posts SET status = ?, published_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, post_id)
        )
    else:
        db.execute("UPDATE posts SET status = ? WHERE id = ?", (status, post_id))
    db.commit()


def get_published_posts() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT p.*, k.keyword FROM posts p "
        "JOIN keywords k ON p.keyword_id = k.id "
        "WHERE p.status = 'published' ORDER BY p.published_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_used_keywords() -> set[str]:
    db = get_db()
    rows = db.execute(
        "SELECT k.keyword FROM keywords k WHERE k.status = 'used'"
    ).fetchall()
    return {r["keyword"] for r in rows}


# --- LLM usage operations ---

def log_llm_usage(module: str, model: str, input_tokens: int,
                  output_tokens: int, cost_usd: float):
    db = get_db()
    db.execute(
        "INSERT INTO llm_usage (module, model, input_tokens, output_tokens, cost_usd) "
        "VALUES (?, ?, ?, ?, ?)",
        (module, model, input_tokens, output_tokens, cost_usd)
    )
    db.commit()


def get_monthly_cost() -> float:
    db = get_db()
    row = db.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) as total FROM llm_usage "
        "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
    ).fetchone()
    return row["total"]


def get_cost_breakdown() -> list[dict]:
    db = get_db()
    rows = db.execute(
        "SELECT module, model, COUNT(*) as calls, "
        "SUM(input_tokens) as total_input, SUM(output_tokens) as total_output, "
        "SUM(cost_usd) as total_cost "
        "FROM llm_usage "
        "WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now') "
        "GROUP BY module, model ORDER BY total_cost DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# --- Keyword intent operations ---

def add_keyword_intent(keyword_id: int, search_intent: str,
                       intent_detail: str = None, target_audience: str = None,
                       trend_context: str = None, content_angle: str = None) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT OR REPLACE INTO keyword_intents "
        "(keyword_id, search_intent, intent_detail, target_audience, trend_context, content_angle) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (keyword_id, search_intent, intent_detail, target_audience, trend_context, content_angle)
    )
    db.commit()
    return cursor.lastrowid


def get_keyword_intent(keyword_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        "SELECT * FROM keyword_intents WHERE keyword_id = ?", (keyword_id,)
    ).fetchone()
    return dict(row) if row else None


# --- Post review operations ---

def add_post_review(post_id: int, seo_score: int, adsense_score: int,
                    humanlike_score: int, readability_score: int,
                    style_score: int, audience_score: int,
                    overall_score: int, issues: str, suggestions: str,
                    passed: int) -> int:
    db = get_db()
    cursor = db.execute(
        "INSERT OR REPLACE INTO post_reviews "
        "(post_id, seo_score, adsense_score, humanlike_score, readability_score, "
        "style_score, audience_score, overall_score, issues, suggestions, passed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (post_id, seo_score, adsense_score, humanlike_score, readability_score,
         style_score, audience_score, overall_score, issues, suggestions, passed)
    )
    db.commit()
    return cursor.lastrowid


def get_post_review(post_id: int) -> dict | None:
    db = get_db()
    row = db.execute(
        "SELECT * FROM post_reviews WHERE post_id = ?", (post_id,)
    ).fetchone()
    return dict(row) if row else None
