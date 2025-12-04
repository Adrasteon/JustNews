from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Optional

from agents.common.agent_chain_harness import NormalizedArticle


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    if not slug:
        slug = "article"
    return slug


def _publisher_db_path() -> Path:
    # project root -> agents/publisher/db.sqlite3
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / 'agents' / 'publisher' / 'db.sqlite3'


def publish_normalized_article(article: NormalizedArticle, *, author: Optional[str] = None, score: float = 0.0, evidence: str = "", is_featured: bool = False, category: str = 'world') -> bool:
    """Publish a normalized article into the lightweight publisher DB.

    Returns True on insertion or update, False on failure.
    """
    db_path = _publisher_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"Publisher DB not found at {db_path}")

    slug = _slugify(article.title or article.article_id or 'article')
    summary = (article.text or '')[:400]
    body = article.text or ''
    author = author or 'Editorial Harness'

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO news_article (slug, title, summary, body, author, score, evidence, is_featured, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (slug, article.title, summary, body, author, float(score), evidence, 1 if is_featured else 0, category),
        )
        conn.commit()
        # If ignored because exists, we still treat as success
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
