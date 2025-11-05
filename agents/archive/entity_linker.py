"""Entity linker utilities used by the Archive agent."""

from typing import Any, Dict, List

from common.observability import get_logger

from .knowledge_graph import KnowledgeGraphManager

logger = get_logger(__name__)


class EntityLinkerManager:
    """Simplified entity linker that defers to the knowledge graph manager."""

    def __init__(self, knowledge_graph: KnowledgeGraphManager, cache_dir: str):
        self._knowledge_graph = knowledge_graph
        self._cache_dir = cache_dir

    async def link_entities(self, article: Dict[str, Any]) -> Dict[str, Any]:
        entities = await self._knowledge_graph.extract_entities(article)
        relationships = await self._knowledge_graph.extract_relationships(article, entities)
        await self._knowledge_graph.store_article_entities(article, entities, relationships)
        return {
            "entities": entities,
            "relationships": relationships,
        }

    async def resolve_entities(self, entities: List[str]) -> List[Dict[str, Any]]:
        return [{"entity": entity, "confidence": 1.0} for entity in entities]

    async def health_check(self) -> Dict[str, Any]:
        stats = self._knowledge_graph.get_statistics()
        stats.update({"cache_dir": self._cache_dir})
        return stats

    def get_statistics(self) -> Dict[str, Any]:
        return {
            "cache_dir": self._cache_dir,
            "entities_indexed": self._knowledge_graph.get_statistics().get("entities_indexed", 0),
        }
