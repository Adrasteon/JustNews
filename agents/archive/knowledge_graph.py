"""Lightweight knowledge graph utilities for the Archive agent."""

import asyncio
import os
from pathlib import Path
from typing import Any

from common.observability import get_logger

from database.utils.migrated_database_utils import (
    add_entity,
    link_entity_to_article,
    get_article_entities as db_get_article_entities,
    search_entities as db_search_entities,
)
from database.utils.migrated_database_utils import create_database_service

logger = get_logger(__name__)


class KnowledgeGraphManager:
    """Knowledge graph manager supporting both file-backed and DB-backed storage.

    Behavior is chosen by the `KG_BACKEND` environment variable ("db" or "file").
    Default: db (uses MariaDB `entities` and `article_entities` tables).
    """

    def __init__(self, kg_storage_path: str | None = None, backend: str | None = None):
        self.backend = (backend or os.environ.get('KG_BACKEND', 'db')).lower()

        if self.backend == 'db':
            # Create and cache a DB service for KG operations
            try:
                self.db_service = create_database_service()
                logger.info("KnowledgeGraphManager: using DB-backed backend")
            except Exception as e:
                logger.warning(f"Failed to initialize DB-backed KG; falling back to file-backed: {e}")
                self.backend = 'file'
                self.db_service = None

        if self.backend == 'file':
            self._storage_path = Path(kg_storage_path or './kg_storage').expanduser().resolve()
            self._storage_path.mkdir(parents=True, exist_ok=True)
            self._entity_dir = self._storage_path / "entities"
            self._entity_dir.mkdir(parents=True, exist_ok=True)

    async def extract_entities(self, article: dict[str, Any]) -> list[str]:
        text = f"{article.get('title', '')} {article.get('content', '')}"
        tokens = {token.strip().lower() for token in text.split() if token.isalpha()}
        return sorted(tokens)

    async def extract_relationships(self, article: dict[str, Any], entities: list[str]) -> list[dict[str, Any]]:
        return [
            {"source": entities[index], "target": entities[index + 1], "type": "cooccurs"}
            for index in range(len(entities) - 1)
        ]

    async def store_article_entities(self, article: dict[str, Any], entities: list[str], relationships: list[dict[str, Any]]) -> None:
        """Store entities and links for an article.

        If DB-backed, this will ensure each entity exists in `entities` and then
        link it in `article_entities` by resolving the article's url_hash to an
        article ID.
        """
        storage_key = article.get("url_hash") or article.get('url_hash')
        if not storage_key:
            return

        if self.backend == 'file':
            payload = {
                "storage_key": storage_key,
                "entities": entities,
                "relationships": relationships,
            }
            file_path = self._entity_dir / f"{storage_key}.json"
            await asyncio.to_thread(self._write_json, file_path, payload)
            return

        # DB-backed path
        try:
            service = self.db_service
            if not service:
                logger.warning('DB service not available for KG storage')
                return

            # Resolve article id from url_hash
            cursor = service.mb_conn.cursor()
            cursor.execute("SELECT id FROM articles WHERE url_hash = %s LIMIT 1", (storage_key,))
            row = cursor.fetchone()
            if not row:
                logger.debug(f"Article not found for url_hash {storage_key}; skipping KG storage")
                try:
                    cursor.close()
                except Exception:
                    pass
                return

            article_id = row[0]

            # Create or find entities and link them
            for ent in entities:
                name = ent
                entity_type = 'unknown'
                eid = add_entity(service, name, entity_type, confidence=None)
                if eid:
                    link_entity_to_article(service, article_id, eid, relevance=None)

            try:
                cursor.close()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"Error storing article entities to DB: {e}")

    def _write_json(self, file_path: Path, payload: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as handle:
            import json

            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def get_statistics(self) -> dict[str, Any]:
        if self.backend == 'file':
            files = list(self._entity_dir.glob("*.json"))
            return {"entities_indexed": len(files), "storage_path": str(self._storage_path)}
        # DB-backed stats
        try:
            svc = self.db_service
            cursor = svc.mb_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM entities")
            entities_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM article_entities")
            links_count = cursor.fetchone()[0]
            cursor.close()
            return {"entities_indexed": entities_count, "article_entity_links": links_count}
        except Exception as e:
            logger.warning(f"Failed to fetch KG stats from DB: {e}")
            return {"status": "unavailable"}

    async def get_article_entities(self, storage_key: str) -> dict[str, Any]:
        if self.backend == 'file':
            file_path = self._entity_dir / f"{storage_key}.json"
            if not file_path.exists():
                return {"storage_key": storage_key, "entities": [], "relationships": []}
            return await asyncio.to_thread(self._read_json, file_path)

        # DB-backed: find article id by url_hash and return entities
        try:
            svc = self.db_service
            cursor = svc.mb_conn.cursor()
            cursor.execute("SELECT id FROM articles WHERE url_hash = %s LIMIT 1", (storage_key,))
            row = cursor.fetchone()
            if not row:
                cursor.close()
                return {"storage_key": storage_key, "entities": [], "relationships": []}
            article_id = row[0]
            cursor.close()
            ents = db_get_article_entities(svc, article_id)
            # Derive simple cooccurrence relationships from entity list
            relationships = []
            for i in range(len(ents) - 1):
                relationships.append({"source": ents[i]["name"], "target": ents[i + 1]["name"], "type": "cooccurs"})

            return {"storage_key": storage_key, "entities": ents, "relationships": relationships}
        except Exception as e:
            logger.warning(f"get_article_entities (DB) failed: {e}")
            return {"storage_key": storage_key, "entities": [], "relationships": []}

    async def search_entities(self, query: str) -> list[dict[str, Any]]:
        query = (query or "").strip().lower()
        if not query:
            return []

        if self.backend == 'file':
            results: list[dict[str, Any]] = []
            for file_path in self._entity_dir.glob("*.json"):
                payload = await asyncio.to_thread(self._read_json, file_path)
                if any(query in entity for entity in payload.get("entities", [])):
                    results.append(payload)
            return results

        # DB-backed: search entities and return matching articles storage_keys
        try:
            svc = self.db_service
            ents = db_search_entities(svc, query)
            # For matched entities, find articles that reference them
            svc.ensure_conn()
            cursor = svc.mb_conn.cursor()
            results = []
            for e in ents:
                cursor.execute("SELECT a.url_hash FROM article_entities ae JOIN articles a ON a.id = ae.article_id WHERE ae.entity_id = %s LIMIT 10", (e['id'],))
                rows = cursor.fetchall()
                for r in rows:
                    results.append({"storage_key": r[0], "entity": e})

            cursor.close()
            return results
        except Exception as e:
            logger.warning(f"search_entities (DB) failed: {e}")
            return []

    async def health_check(self) -> dict[str, Any]:
        if self.backend == 'file':
            return {"status": "healthy", "storage_path": str(self._storage_path), "entity_count": len(list(self._entity_dir.glob("*.json")))}
        try:
            svc = self.db_service
            cursor = svc.mb_conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM entities")
            entities_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM article_entities")
            links_count = cursor.fetchone()[0]
            cursor.close()
            return {"status": "healthy", "entities": entities_count, "links": links_count}
        except Exception as e:
            logger.warning(f"KG health_check failed: {e}")
            return {"status": "unhealthy", "error": str(e)}

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        import json

        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
