"""Lightweight knowledge graph utilities for the Archive agent."""

import asyncio
from pathlib import Path
from typing import Any

from common.observability import get_logger

logger = get_logger(__name__)


class KnowledgeGraphManager:
    """Minimal stub that records entity statistics on disk."""

    def __init__(self, kg_storage_path: str):
        self._storage_path = Path(kg_storage_path).expanduser().resolve()
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
        storage_key = article.get("url_hash")
        if not storage_key:
            return
        payload = {
            "storage_key": storage_key,
            "entities": entities,
            "relationships": relationships,
        }
        file_path = self._entity_dir / f"{storage_key}.json"
        await asyncio.to_thread(self._write_json, file_path, payload)

    def _write_json(self, file_path: Path, payload: dict[str, Any]) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as handle:
            import json

            json.dump(payload, handle, ensure_ascii=False, indent=2)

    def get_statistics(self) -> dict[str, Any]:
        files = list(self._entity_dir.glob("*.json"))
        return {
            "entities_indexed": len(files),
            "storage_path": str(self._storage_path),
        }

    async def get_article_entities(self, storage_key: str) -> dict[str, Any]:
        file_path = self._entity_dir / f"{storage_key}.json"
        if not file_path.exists():
            return {"storage_key": storage_key, "entities": [], "relationships": []}
        return await asyncio.to_thread(self._read_json, file_path)

    async def search_entities(self, query: str) -> list[dict[str, Any]]:
        query = (query or "").strip().lower()
        if not query:
            return []
        results: list[dict[str, Any]] = []
        for file_path in self._entity_dir.glob("*.json"):
            payload = await asyncio.to_thread(self._read_json, file_path)
            if any(query in entity for entity in payload.get("entities", [])):
                results.append(payload)
        return results

    async def health_check(self) -> dict[str, Any]:
        return {
            "status": "healthy",
            "storage_path": str(self._storage_path),
            "entity_count": len(list(self._entity_dir.glob("*.json"))),
        }

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        import json

        with file_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
