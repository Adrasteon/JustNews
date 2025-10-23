from common.observability import get_logger

#!/usr/bin/env python3
"""
Phase 3 Advanced Feature: Entity Linking with External Knowledge Bases

This module provides entity linking capabilities to connect JustNews entities
with external knowledge bases like Wikidata, enhancing entity information
with structured data and disambiguation.

Features:
- Wikidata integration for entity enrichment
- Entity disambiguation using external knowledge
- Confidence scoring for entity links
- Caching for performance optimization
- Fallback mechanisms for reliability
"""

import asyncio
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp

logger = get_logger(__name__)

class ExternalKnowledgeBaseLinker:
    """
    Links entities to external knowledge bases for enrichment and disambiguation

    Supports multiple knowledge bases:
    - Wikidata: Structured data and entity relationships
    - DBpedia: Linked data from Wikipedia
    - Custom knowledge bases via configurable endpoints
    """

    def __init__(self, cache_dir: str = "./entity_cache", enable_cache: bool = True):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.enable_cache = enable_cache

        # Knowledge base configurations
        self.kb_configs = {
            "wikidata": {
                "base_url": "https://www.wikidata.org/w/api.php",
                "sparql_url": "https://query.wikidata.org/sparql",
                "search_url": "https://www.wikidata.org/w/api.php",
                "enabled": True,
                "timeout": 10,
                "max_results": 5
            },
            "dbpedia": {
                "base_url": "http://dbpedia.org/sparql",
                "lookup_url": "http://lookup.dbpedia.org/api/search",
                "enabled": True,
                "timeout": 10,
                "max_results": 5
            }
        }

        # HTTP session for connection reuse
        self.session = None

        logger.info("🎯 External Knowledge Base Linker initialized")

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={
                'User-Agent': 'JustNewsAgent/3.0 (https://github.com/adrasteon/JustNewsAgent)'
            }
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    def _get_cache_key(self, entity_name: str, kb_name: str) -> str:
        """Generate cache key for entity lookup"""
        content = f"{entity_name}:{kb_name}"
        return hashlib.md5(content.encode()).hexdigest()

    def _load_cache(self, cache_key: str) -> dict[str, Any] | None:
        """Load cached entity data"""
        if not self.enable_cache:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, encoding='utf-8') as f:
                    cached_data = json.load(f)

                # Check if cache is still valid (24 hours)
                cached_time = datetime.fromisoformat(cached_data.get('cached_at', '2000-01-01'))
                if datetime.now() - cached_time < timedelta(hours=24):
                    return cached_data.get('data')

            except Exception as e:
                logger.debug(f"Cache load error for {cache_key}: {e}")

        return None

    def _save_cache(self, cache_key: str, data: dict[str, Any]):
        """Save entity data to cache"""
        if not self.enable_cache:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        cache_data = {
            'data': data,
            'cached_at': datetime.now().isoformat()
        }

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.debug(f"Cache save error for {cache_key}: {e}")

    async def link_entity_wikidata(self, entity_name: str, entity_type: str = None) -> list[dict[str, Any]]:
        """
        Link entity to Wikidata knowledge base

        Args:
            entity_name: Name of the entity to link
            entity_type: Optional entity type for better matching

        Returns:
            List of potential Wikidata matches with confidence scores
        """
        cache_key = self._get_cache_key(entity_name, "wikidata")
        cached_result = self._load_cache(cache_key)
        if cached_result:
            return cached_result

        config = self.kb_configs["wikidata"]
        if not config["enabled"]:
            return []

        results = []

        try:
            # Wikidata search API
            search_params = {
                'action': 'wbsearchentities',
                'format': 'json',
                'language': 'en',
                'search': entity_name,
                'limit': config["max_results"],
                'type': 'item'  # Wikidata items (not properties)
            }

            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(config["search_url"], params=search_params) as response:
                if response.status == 200:
                    data = await response.json()
                    search_results = data.get('search', [])

                    for result in search_results:
                        entity_id = result.get('id')
                        label = result.get('label', '')
                        description = result.get('description', '')

                        # Calculate confidence score based on match quality
                        confidence = self._calculate_match_confidence(
                            entity_name, label, description, entity_type
                        )

                        if confidence > 0.3:  # Only include reasonably confident matches
                            wikidata_entity = {
                                'entity_id': entity_id,
                                'name': label,
                                'description': description,
                                'knowledge_base': 'wikidata',
                                'url': f"https://www.wikidata.org/wiki/{entity_id}",
                                'confidence': confidence,
                                'aliases': result.get('aliases', []),
                                'metadata': {
                                    'match_type': result.get('match', {}).get('type', 'unknown'),
                                    'language': result.get('match', {}).get('language', 'en')
                                }
                            }
                            results.append(wikidata_entity)

                    # Sort by confidence
                    results.sort(key=lambda x: x['confidence'], reverse=True)

        except Exception as e:
            logger.error(f"Wikidata linking error for '{entity_name}': {e}")

        # Cache the results
        self._save_cache(cache_key, results)
        return results

    async def link_entity_dbpedia(self, entity_name: str, entity_type: str = None) -> list[dict[str, Any]]:
        """
        Link entity to DBpedia knowledge base

        Args:
            entity_name: Name of the entity to link
            entity_type: Optional entity type for better matching

        Returns:
            List of potential DBpedia matches with confidence scores
        """
        cache_key = self._get_cache_key(entity_name, "dbpedia")
        cached_result = self._load_cache(cache_key)
        if cached_result:
            return cached_result

        config = self.kb_configs["dbpedia"]
        if not config["enabled"]:
            return []

        results = []

        try:
            # DBpedia Lookup API
            lookup_params = {
                'QueryString': entity_name,
                'MaxHits': config["max_results"],
                'QueryClass': self._map_entity_type_to_dbpedia_class(entity_type),
                'format': 'json' # Add format=json to request JSON response
            }

            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(config["lookup_url"], params=lookup_params) as response:
                if response.status == 200:
                    data = await response.json()
                    docs = data.get('docs', [])

                    for doc in docs:
                        uri = doc.get('uri', [''])[0] if doc.get('uri') else ''
                        label = doc.get('label', [''])[0] if doc.get('label') else ''
                        description = doc.get('comment', [''])[0] if doc.get('comment') else ''
                        category = doc.get('category', [''])[0] if doc.get('category') else ''

                        # Calculate confidence score
                        confidence = self._calculate_match_confidence(
                            entity_name, label, description, entity_type
                        )

                        if confidence > 0.3:
                            dbpedia_entity = {
                                'entity_id': uri.split('/')[-1] if uri else '',
                                'name': label,
                                'description': description,
                                'knowledge_base': 'dbpedia',
                                'url': uri,
                                'confidence': confidence,
                                'category': category,
                                'metadata': {
                                    'classes': doc.get('classes', []),
                                    'categories': doc.get('category', [])
                                }
                            }
                            results.append(dbpedia_entity)

                    # Sort by confidence
                    results.sort(key=lambda x: x['confidence'], reverse=True)

        except Exception as e:
            logger.error(f"DBpedia linking error for '{entity_name}': {e}")

        # Cache the results
        self._save_cache(cache_key, results)
        return results

    def _calculate_match_confidence(self, query: str, label: str, description: str,
                                  entity_type: str = None) -> float:
        """
        Calculate confidence score for entity match

        Factors:
        - Exact name match
        - Partial name match
        - Description relevance
        - Entity type compatibility
        """
        query_lower = query.lower()
        label_lower = label.lower()
        desc_lower = description.lower() if description else ''

        confidence = 0.0

        # Exact match gets highest confidence
        if query_lower == label_lower:
            confidence += 1.0
        # Starts with query
        elif label_lower.startswith(query_lower):
            confidence += 0.8
        # Contains query
        elif query_lower in label_lower:
            confidence += 0.6
        # Query in description
        elif query_lower in desc_lower:
            confidence += 0.4

        # Boost for entity type matches (if available)
        if entity_type and description:
            type_keywords = self._get_entity_type_keywords(entity_type)
            if any(keyword in desc_lower for keyword in type_keywords):
                confidence += 0.2

        # Normalize to 0-1 range
        return min(confidence, 1.0)

    def _get_entity_type_keywords(self, entity_type: str) -> list[str]:
        """Get keywords associated with entity types for better matching"""
        type_keywords = {
            'PERSON': ['person', 'individual', 'human', 'politician', 'actor', 'artist', 'scientist'],
            'ORG': ['organization', 'company', 'corporation', 'agency', 'institution', 'university'],
            'GPE': ['country', 'city', 'state', 'province', 'nation', 'location', 'place'],
            'EVENT': ['event', 'conference', 'meeting', 'incident', 'disaster', 'celebration'],
            'MONEY': ['currency', 'dollar', 'euro', 'pound', 'yen', 'money', 'finance'],
            'DATE': ['date', 'time', 'period', 'era', 'century', 'year'],
            'PERCENT': ['percent', 'percentage', 'rate', 'ratio']
        }
        return type_keywords.get(entity_type.upper(), [])

    def _map_entity_type_to_dbpedia_class(self, entity_type: str) -> str:
        """Map internal entity types to DBpedia ontology classes"""
        type_mapping = {
            'PERSON': 'Person',
            'ORG': 'Organization',
            'GPE': 'Place',
            'EVENT': 'Event'
        }
        return type_mapping.get(entity_type.upper(), '')

    async def enrich_entity(self, entity_name: str, entity_type: str = None,
                          knowledge_bases: list[str] = None) -> dict[str, Any]:
        """
        Enrich entity with information from multiple knowledge bases

        Args:
            entity_name: Name of the entity to enrich
            entity_type: Optional entity type
            knowledge_bases: List of KBs to query (default: all enabled)

        Returns:
            Enriched entity data with external links and metadata
        """
        if knowledge_bases is None:
            knowledge_bases = [kb for kb, config in self.kb_configs.items() if config["enabled"]]

        enriched_data = {
            'original_name': entity_name,
            'entity_type': entity_type,
            'external_links': [],
            'best_match': None,
            'confidence_score': 0.0,
            'enriched_at': datetime.now().isoformat(),
            'knowledge_bases_queried': knowledge_bases
        }

        all_matches = []

        # Query each knowledge base
        for kb_name in knowledge_bases:
            if kb_name == 'wikidata':
                matches = await self.link_entity_wikidata(entity_name, entity_type)
            elif kb_name == 'dbpedia':
                matches = await self.link_entity_dbpedia(entity_name, entity_type)
            else:
                continue

            all_matches.extend(matches)

        if all_matches:
            # Sort all matches by confidence
            all_matches.sort(key=lambda x: x['confidence'], reverse=True)

            # Select best match (highest confidence)
            best_match = all_matches[0]
            enriched_data['best_match'] = best_match
            enriched_data['confidence_score'] = best_match['confidence']
            enriched_data['external_links'] = all_matches[:3]  # Top 3 matches

        return enriched_data

    async def batch_enrich_entities(self, entities: list[dict[str, Any]],
                                  knowledge_bases: list[str] = None) -> list[dict[str, Any]]:
        """
        Batch enrich multiple entities

        Args:
            entities: List of entity dictionaries with 'name' and optional 'type'
            knowledge_bases: Knowledge bases to query

        Returns:
            List of enriched entity data
        """
        enriched_entities = []

        # Process entities with concurrency control
        semaphore = asyncio.Semaphore(5)  # Limit concurrent requests

        async def enrich_single_entity(entity_data: dict[str, Any]):
            async with semaphore:
                entity_name = entity_data.get('name', '')
                entity_type = entity_data.get('entity_type')

                if entity_name:
                    enriched = await self.enrich_entity(entity_name, entity_type, knowledge_bases)
                    return {**entity_data, 'external_enrichment': enriched}

                return entity_data

        # Process all entities concurrently
        tasks = [enrich_single_entity(entity) for entity in entities]
        enriched_entities = await asyncio.gather(*tasks)

        return enriched_entities

class EntityLinkerManager:
    """
    High-level manager for entity linking operations

    Integrates with the knowledge graph to provide entity enrichment
    and disambiguation capabilities.
    """

    def __init__(self, kg_manager, cache_dir: str = "./entity_cache"):
        self.kg_manager = kg_manager
        self.linker = ExternalKnowledgeBaseLinker(cache_dir)
        self.enrichment_stats = {
            'total_entities_processed': 0,
            'entities_enriched': 0,
            'cache_hits': 0,
            'external_queries': 0,
            'average_confidence': 0.0
        }

        logger.info("🎯 Entity Linker Manager initialized")

    async def enrich_knowledge_graph_entities(self, limit: int = 100) -> dict[str, Any]:
        """
        Enrich entities in the knowledge graph with external knowledge

        Args:
            limit: Maximum number of entities to process

        Returns:
            Enrichment statistics and results
        """
        logger.info(f"🔗 Starting knowledge graph entity enrichment (limit: {limit})")

        # Get entities from knowledge graph
        entities = self.kg_manager.query_entities(limit=limit)

        if not entities:
            logger.warning("⚠️ No entities found in knowledge graph")
            return {"error": "No entities to enrich"}

        # Convert to format expected by linker
        entity_list = [
            {
                'node_id': entity['node_id'],
                'name': entity.get('name', ''),
                'entity_type': entity.get('entity_type', ''),
                'mention_count': entity.get('mention_count', 0)
            }
            for entity in entities
        ]

        # Enrich entities
        async with self.linker:
            enriched_entities = await self.linker.batch_enrich_entities(entity_list)

        # Update knowledge graph with enriched data
        updated_count = 0
        for enriched_entity in enriched_entities:
            enrichment = enriched_entity.get('external_enrichment', {})
            if enrichment.get('best_match'):
                # Update entity node with external links
                node_id = enriched_entity['node_id']
                external_data = {
                    'external_links': enrichment.get('external_links', []),
                    'best_match': enrichment.get('best_match'),
                    'enrichment_confidence': enrichment.get('confidence_score', 0.0),
                    'enriched_at': enrichment.get('enriched_at')
                }

                # Update node properties
                if node_id in self.kg_manager.graph.nodes:
                    self.kg_manager.graph.nodes[node_id]['properties'].update(external_data)
                    updated_count += 1

        # Update statistics
        self.enrichment_stats['total_entities_processed'] += len(enriched_entities)
        self.enrichment_stats['entities_enriched'] += updated_count

        result = {
            'entities_processed': len(enriched_entities),
            'entities_enriched': updated_count,
            'enrichment_rate': updated_count / len(enriched_entities) if enriched_entities else 0,
            'knowledge_bases_used': ['wikidata', 'dbpedia'],
            'processing_timestamp': datetime.now().isoformat()
        }

        logger.info(f"✅ Entity enrichment complete: {updated_count}/{len(enriched_entities)} entities enriched")
        return result

    async def get_entity_external_info(self, entity_name: str, entity_type: str = None) -> dict[str, Any]:
        """
        Get external information for a specific entity

        Args:
            entity_name: Name of the entity
            entity_type: Optional entity type

        Returns:
            External entity information
        """
        async with self.linker:
            return await self.linker.enrich_entity(entity_name, entity_type)

    def get_enrichment_statistics(self) -> dict[str, Any]:
        """Get entity enrichment statistics"""
        return {
            **self.enrichment_stats,
            'cache_hit_rate': (
                self.enrichment_stats['cache_hits'] /
                max(self.enrichment_stats['external_queries'], 1)
            ),
            'last_updated': datetime.now().isoformat()
        }

# Standalone functions for easy integration
async def enrich_entity_standalone(entity_name: str, entity_type: str = None,
                                 knowledge_bases: list[str] = None) -> dict[str, Any]:
    """
    Standalone function to enrich a single entity

    Useful for testing and one-off enrichment operations.
    """
    async with ExternalKnowledgeBaseLinker() as linker:
        return await linker.enrich_entity(entity_name, entity_type, knowledge_bases)

async def demo_entity_linking():
    """Demonstrate entity linking capabilities"""
    print("🎯 Phase 3 Advanced Feature: Entity Linking Demo")
    print("=" * 60)

    async with ExternalKnowledgeBaseLinker() as linker:
        # Test entities
        test_entities = [
            ("Barack Obama", "PERSON"),
            ("Microsoft Corporation", "ORG"),
            ("London", "GPE"),
            ("COVID-19", "EVENT")
        ]

        print("🔍 Testing entity linking with external knowledge bases...")
        print()

        for entity_name, entity_type in test_entities:
            print(f"📍 Enriching: {entity_name} ({entity_type})")

            enriched_data = await linker.enrich_entity(entity_name, entity_type)

            if enriched_data.get('best_match'):
                best_match = enriched_data['best_match']
                print(f"   ✅ Best match: {best_match['name']}")
                print(f"   📊 Confidence: {best_match['confidence']:.2f}")
                print(f"   🔗 Knowledge Base: {best_match['knowledge_base']}")
                print(f"   🌐 URL: {best_match['url']}")
                if best_match.get('description'):
                    print(f"   📝 Description: {best_match['description'][:100]}...")
            else:
                print("   ❌ No suitable matches found")

            print(f"   📊 External links found: {len(enriched_data.get('external_links', []))}")
            print()

    print("🎉 Entity Linking Demo Complete!")
    print("\n🚀 Key Features Demonstrated:")
    print("   ✅ Wikidata integration")
    print("   ✅ DBpedia integration")
    print("   ✅ Confidence scoring")
    print("   ✅ Entity type-aware matching")
    print("   ✅ Caching for performance")
    print("   ✅ Batch processing capabilities")

if __name__ == "__main__":
    asyncio.run(demo_entity_linking())
