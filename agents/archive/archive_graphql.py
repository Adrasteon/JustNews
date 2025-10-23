from common.observability import get_logger

#!/usr/bin/env python3
"""
Phase 3 Sprint 3-4: GraphQL Query Interface

GraphQL interface for complex knowledge graph queries and flexible data access.
Provides advanced querying capabilities with nested relationships, filtering, and aggregation.

GraphQL Schema:
- Query: Root query operations
- Article: Article node with relationships
- Entity: Entity node with relationships
- Relationship: Relationship between entities
- GraphStatistics: Knowledge graph statistics
- SearchResult: Search results with metadata
"""


import contextlib
import hashlib
from datetime import datetime

import graphene
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from graphene import Field, Float, Int, ObjectType, Schema, String
from graphene import List as GraphQLList
from graphene.types.datetime import DateTime

# Import graphql function
from graphql import graphql
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from agents.archive.archive_manager import ArchiveManager
from agents.archive.knowledge_graph import KnowledgeGraphManager

logger = get_logger(__name__)

# Rate Limiting Configuration
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# GraphQL Types
class EntityTypeEnum(graphene.Enum):
    PERSON = "PERSON"
    ORG = "ORG"
    GPE = "GPE"
    EVENT = "EVENT"
    MONEY = "MONEY"
    DATE = "DATE"
    TIME = "TIME"
    PERCENT = "PERCENT"
    QUANTITY = "QUANTITY"

class RelationshipType(graphene.ObjectType):
    """GraphQL type for entity relationships"""
    source_entity_id = String(required=True)
    target_entity_id = String(required=True)
    relationship_type = String(required=True)
    strength = Float(required=True)
    confidence = Float(required=True)
    context = String()
    timestamp = DateTime()
    co_occurrence_count = Int()
    proximity_score = Float()

class EntityType(graphene.ObjectType):
    """GraphQL type for entities"""
    entity_id = String(required=True)
    name = String(required=True)
    entity_type = EntityTypeEnum(required=True)
    mention_count = Int(required=True)
    first_seen = DateTime()
    last_seen = DateTime()
    aliases = GraphQLList(String)
    cluster_size = Int()
    confidence_score = Float()

    # Relationships
    relationships = GraphQLList(RelationshipType,
        limit=Int(default_value=50),
        offset=Int(default_value=0),
        relationship_type=String(),
        min_strength=Float(default_value=0.0),
        min_confidence=Float(default_value=0.0)
    )

    def resolve_relationships(self, info, limit=50, offset=0, relationship_type=None,
                            min_strength=0.0, min_confidence=0.0):
        """Resolve entity relationships"""
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return []

        relationships = []

        # Get outgoing relationships
        for source, target, edge_type, edge_data in kg_manager.kg.graph.edges(self.entity_id, keys=True, data=True):
            if relationship_type and edge_type != relationship_type:
                continue
            if edge_data.get("strength", 0) < min_strength:
                continue
            if edge_data.get("confidence", 0) < min_confidence:
                continue

            # Get target entity info
            if target in kg_manager.kg.graph.nodes:
                target_node = kg_manager.kg.graph.nodes[target]
                if target_node.get("node_type") == "entity":
                    pass

            relationship = RelationshipType(
                source_entity_id=self.entity_id,
                target_entity_id=target,
                relationship_type=edge_type,
                strength=edge_data.get("strength", 0),
                confidence=edge_data.get("confidence", 0),
                context=edge_data.get("context", ""),
                timestamp=edge_data.get("timestamp"),
                co_occurrence_count=edge_data.get("co_occurrence_count", 0),
                proximity_score=edge_data.get("proximity_score", 0)
            )
            relationships.append(relationship)

        # Apply pagination
        return relationships[offset:offset + limit]

class ArticleType(graphene.ObjectType):
    """GraphQL type for articles"""
    article_id = String(required=True)
    url = String(required=True)
    title = String(required=True)
    domain = String()
    published_date = DateTime()
    content = String()
    entities = graphene.JSONString()  # JSON object of entity types to lists
    news_score = Float()
    extraction_method = String()
    publisher = String()
    canonical_url = String()

    # Related entities
    related_entities = GraphQLList(EntityType,
        limit=Int(default_value=20),
        offset=Int(default_value=0),
        entity_type=EntityTypeEnum(),
        min_confidence=Float(default_value=0.0)
    )

    def resolve_related_entities(self, info, limit=20, offset=0, entity_type=None, min_confidence=0.0):
        """Resolve entities related to this article"""
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return []

        entities = []
        article_entities = self.entities or {}

        for entity_type_key, entity_list in article_entities.items():
            if entity_type and entity_type_key != entity_type:
                continue

            for entity_name in entity_list:
                # Find entity node by name
                for node_id, node_data in kg_manager.kg.graph.nodes(data=True):
                    if (node_data.get("node_type") == "entity" and
                        node_data["properties"].get("name") == entity_name and
                        node_data["properties"].get("confidence", 0) >= min_confidence):

                        entity = EntityType(
                            entity_id=node_id,
                            name=node_data["properties"].get("name", ""),
                            entity_type=node_data["properties"].get("entity_type", ""),
                            mention_count=node_data["properties"].get("mention_count", 0),
                            first_seen=node_data["properties"].get("first_seen"),
                            last_seen=node_data["properties"].get("last_seen"),
                            aliases=node_data["properties"].get("aliases", []),
                            cluster_size=node_data["properties"].get("cluster_size", 1),
                            confidence_score=node_data["properties"].get("confidence", 0.8)
                        )
                        entities.append(entity)
                        break

        return entities[offset:offset + limit]

class GraphStatisticsType(graphene.ObjectType):
    """GraphQL type for knowledge graph statistics"""
    total_nodes = Int()
    total_edges = Int()
    node_types = graphene.JSONString()
    edge_types = graphene.JSONString()
    entity_types = graphene.JSONString()
    temporal_coverage = graphene.JSONString()
    clustering_stats = graphene.JSONString()
    last_updated = DateTime()

class SearchResultType(graphene.ObjectType):
    """GraphQL type for search results"""
    type = String(required=True)  # "article" or "entity"
    id = String(required=True)
    title = String(required=True)
    content = String()
    score = Float(required=True)
    metadata = graphene.JSONString()

class ExportArticles(graphene.Mutation):
    """Export articles in bulk"""
    class Arguments:
        filters = graphene.JSONString()
        format = graphene.String(default_value="json")
        limit = graphene.Int(default_value=1000)
        include_content = graphene.Boolean(default_value=True)
        include_entities = graphene.Boolean(default_value=True)

    success = graphene.Boolean()
    job_id = graphene.String()
    message = graphene.String()
    estimated_items = graphene.Int()

    async def mutate(self, info, filters=None, format="json", limit=1000,
                    include_content=True, include_entities=True):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return ExportArticles(success=False, message="Knowledge graph manager not available")

        try:
            # Validate format
            supported_formats = ["json", "csv", "jsonl"]
            if format not in supported_formats:
                return ExportArticles(
                    success=False,
                    message=f"Unsupported format: {format}. Supported: {supported_formats}"
                )

            # Cap limits for safety
            limit = min(limit, 10000)

            # Generate export job ID
            job_id = f"export_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(filters or {}).encode()).hexdigest()[:8]}"

            # Start export as background task (would need to be implemented)
            # For now, return job queued status
            return ExportArticles(
                success=True,
                job_id=job_id,
                message="Article export job queued successfully",
                estimated_items=limit
            )

        except Exception as e:
            return ExportArticles(success=False, message=f"Export failed: {str(e)}")

class ExportEntities(graphene.Mutation):
    """Export entities in bulk"""
    class Arguments:
        filters = graphene.JSONString()
        format = graphene.String(default_value="json")
        limit = graphene.Int(default_value=5000)
        include_relationships = graphene.Boolean(default_value=False)
        include_external_info = graphene.Boolean(default_value=False)

    success = graphene.Boolean()
    job_id = graphene.String()
    message = graphene.String()
    estimated_items = graphene.Int()

    async def mutate(self, info, filters=None, format="json", limit=5000,
                    include_relationships=False, include_external_info=False):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return ExportEntities(success=False, message="Knowledge graph manager not available")

        try:
            # Validate format
            supported_formats = ["json", "csv", "jsonl"]
            if format not in supported_formats:
                return ExportEntities(
                    success=False,
                    message=f"Unsupported format: {format}. Supported: {supported_formats}"
                )

            # Cap limits for safety
            limit = min(limit, 50000)

            # Generate export job ID
            job_id = f"export_entities_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(filters or {}).encode()).hexdigest()[:8]}"

            # Start export as background task (would need to be implemented)
            return ExportEntities(
                success=True,
                job_id=job_id,
                message="Entity export job queued successfully",
                estimated_items=limit
            )

        except Exception as e:
            return ExportEntities(success=False, message=f"Export failed: {str(e)}")

class ExportRelationships(graphene.Mutation):
    """Export relationships in bulk"""
    class Arguments:
        filters = graphene.JSONString()
        format = graphene.String(default_value="json")
        limit = graphene.Int(default_value=10000)

    success = graphene.Boolean()
    job_id = graphene.String()
    message = graphene.String()
    estimated_items = graphene.Int()

    async def mutate(self, info, filters=None, format="json", limit=10000):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return ExportRelationships(success=False, message="Knowledge graph manager not available")

        try:
            # Validate format
            supported_formats = ["json", "csv", "jsonl", "graphml"]
            if format not in supported_formats:
                return ExportRelationships(
                    success=False,
                    message=f"Unsupported format: {format}. Supported: {supported_formats}"
                )

            # Cap limits for safety
            limit = min(limit, 100000)

            # Generate export job ID
            job_id = f"export_relationships_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(filters or {}).encode()).hexdigest()[:8]}"

            # Start export as background task (would need to be implemented)
            return ExportRelationships(
                success=True,
                job_id=job_id,
                message="Relationship export job queued successfully",
                estimated_items=limit
            )

        except Exception as e:
            return ExportRelationships(success=False, message=f"Export failed: {str(e)}")

class ExportStatusType(graphene.ObjectType):
    """Export job status"""
    job_id = graphene.String()
    status = graphene.String()
    progress = graphene.Float()
    items_processed = graphene.Int()
    error = graphene.String()
    updated_at = graphene.String()

class Query(ObjectType):
    """Root GraphQL query"""

    # Health check
    health = String()

    def resolve_health(self, info):
        return "GraphQL API is operational"

    # Single article
    article = Field(ArticleType, id=String(required=True))

    def resolve_article(self, info, id):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager or id not in kg_manager.kg.graph.nodes:
            return None

        node_data = kg_manager.kg.graph.nodes[id]
        if node_data.get("node_type") != "article":
            return None

        article_data = node_data["properties"]

        # Format published_date properly for GraphQL
        published_date = article_data.get("published_date")
        if published_date:
            try:
                if isinstance(published_date, str):
                    if 'T' in published_date:
                        # Parse ISO format
                        dt_str = published_date.replace('Z', '+00:00')
                        published_date = datetime.fromisoformat(dt_str)
                    else:
                        # Parse other formats
                        published_date = datetime.fromisoformat(published_date)
            except (ValueError, TypeError):
                published_date = None

        return ArticleType(
            article_id=id,
            url=article_data.get("url", ""),
            title=article_data.get("title", ""),
            domain=article_data.get("domain", ""),
            published_date=published_date,
            content=article_data.get("content", ""),
            entities=article_data.get("entities", {}),
            news_score=article_data.get("news_score", 0.0),
            extraction_method=article_data.get("extraction_method", ""),
            publisher=article_data.get("publisher", ""),
            canonical_url=article_data.get("canonical_url", "")
        )

    # Single entity
    entity = Field(EntityType, id=String(required=True))

    def resolve_entity(self, info, id):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager or id not in kg_manager.kg.graph.nodes:
            return None

        node_data = kg_manager.kg.graph.nodes[id]
        if node_data.get("node_type") != "entity":
            return None

        entity_data = node_data["properties"]
        return EntityType(
            entity_id=id,
            name=entity_data.get("name", ""),
            entity_type=entity_data.get("entity_type", ""),
            mention_count=entity_data.get("mention_count", 0),
            first_seen=entity_data.get("first_seen"),
            last_seen=entity_data.get("last_seen"),
            aliases=entity_data.get("aliases", []),
            cluster_size=entity_data.get("cluster_size", 1),
            confidence_score=entity_data.get("confidence", 0.8)
        )

    # List articles with filtering
    articles = GraphQLList(ArticleType,
        limit=Int(default_value=20),
        offset=Int(default_value=0),
        domain=String(),
        published_after=DateTime(),
        published_before=DateTime(),
        news_score_min=Float(default_value=0.0),
        news_score_max=Float(default_value=1.0),
        entity_type=EntityTypeEnum(),
        search_query=String(),
        sort_by=String(default_value="published_date"),
        sort_order=String(default_value="desc")
    )

    def resolve_articles(self, info, limit=20, offset=0, domain=None, published_after=None,
                        published_before=None, news_score_min=0.0, news_score_max=1.0,
                        entity_type=None, search_query=None, sort_by="published_date",
                        sort_order="desc"):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return []

        articles = []

        for node_id, node_data in kg_manager.kg.graph.nodes(data=True):
            if node_data.get("node_type") == "article":
                article_data = node_data["properties"]

                # Apply filters
                if domain and article_data.get("domain") != domain:
                    continue

                if published_after:
                    pub_date = article_data.get("published_date")
                    if pub_date:
                        try:
                            article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                            if article_date < published_after:
                                continue
                        except (ValueError, TypeError):
                            pass

                if published_before:
                    pub_date = article_data.get("published_date")
                    if pub_date:
                        try:
                            article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                            if article_date > published_before:
                                continue
                        except (ValueError, TypeError):
                            pass

                if article_data.get("news_score", 0) < news_score_min or article_data.get("news_score", 0) > news_score_max:
                    continue

                if entity_type:
                    entities = article_data.get("entities", {})
                    if entity_type not in entities or not entities[entity_type]:
                        continue

                if search_query:
                    title = article_data.get("title", "").lower()
                    content = article_data.get("content", "").lower()
                    query_lower = search_query.lower()
                    if query_lower not in title and query_lower not in content:
                        continue

                # Format published_date properly for GraphQL
                published_date = article_data.get("published_date")
                if published_date:
                    try:
                        if isinstance(published_date, str):
                            if 'T' in published_date:
                                # Parse ISO format
                                dt_str = published_date.replace('Z', '+00:00')
                                published_date = datetime.fromisoformat(dt_str)
                            else:
                                # Parse other formats
                                published_date = datetime.fromisoformat(published_date)
                    except (ValueError, TypeError):
                        published_date = None

                article = ArticleType(
                    article_id=node_id,
                    url=article_data.get("url", ""),
                    title=article_data.get("title", ""),
                    domain=article_data.get("domain", ""),
                    published_date=published_date,
                    content=article_data.get("content", ""),
                    entities=article_data.get("entities", {}),
                    news_score=article_data.get("news_score", 0.0),
                    extraction_method=article_data.get("extraction_method", ""),
                    publisher=article_data.get("publisher", ""),
                    canonical_url=article_data.get("canonical_url", "")
                )
                articles.append(article)

        # Sort articles
        reverse = sort_order.lower() == "desc"
        if sort_by == "published_date":
            articles.sort(key=lambda x: x.published_date or "", reverse=reverse)
        elif sort_by == "news_score":
            articles.sort(key=lambda x: x.news_score or 0, reverse=reverse)
        elif sort_by == "title":
            articles.sort(key=lambda x: x.title or "", reverse=reverse)

        return articles[offset:offset + limit]

    # List entities with filtering
    entities = GraphQLList(EntityType,
        limit=Int(default_value=20),
        offset=Int(default_value=0),
        entity_type=EntityTypeEnum(),
        mention_count_min=Int(default_value=0),
        mention_count_max=Int(default_value=1000),
        first_seen_after=DateTime(),
        last_seen_before=DateTime(),
        search_query=String(),
        sort_by=String(default_value="mention_count"),
        sort_order=String(default_value="desc")
    )

    def resolve_entities(self, info, limit=20, offset=0, entity_type=None, mention_count_min=0,
                        mention_count_max=1000, first_seen_after=None, last_seen_before=None,
                        search_query=None, sort_by="mention_count", sort_order="desc"):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return []

        entities = kg_manager.kg.query_entities(entity_type, limit=10000)  # Large limit for filtering

        # Apply additional filters
        filtered_entities = []
        for entity in entities:
            if entity.get("mention_count", 0) < mention_count_min or entity.get("mention_count", 0) > mention_count_max:
                continue

            if first_seen_after:
                first_seen = entity.get("first_seen")
                if first_seen:
                    try:
                        entity_date = datetime.fromisoformat(first_seen.replace('Z', '+00:00'))
                        if entity_date < first_seen_after:
                            continue
                    except (ValueError, TypeError):
                        pass

            if last_seen_before:
                last_seen = entity.get("last_seen")
                if last_seen:
                    try:
                        entity_date = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                        if entity_date > last_seen_before:
                            continue
                    except (ValueError, TypeError):
                        pass

            if search_query:
                name_lower = entity.get("name", "").lower()
                query_lower = search_query.lower()
                if query_lower not in name_lower:
                    continue

            entity_obj = EntityType(
                entity_id=entity["node_id"],
                name=entity.get("name", ""),
                entity_type=entity.get("entity_type", ""),
                mention_count=entity.get("mention_count", 0),
                first_seen=entity.get("first_seen"),
                last_seen=entity.get("last_seen"),
                aliases=entity.get("aliases", []),
                cluster_size=entity.get("cluster_size", 1),
                confidence_score=entity.get("confidence", 0.8)
            )
            filtered_entities.append(entity_obj)

        # Sort entities
        reverse = sort_order.lower() == "desc"
        if sort_by == "mention_count":
            filtered_entities.sort(key=lambda x: x.mention_count, reverse=reverse)
        elif sort_by == "name":
            filtered_entities.sort(key=lambda x: x.name or "", reverse=reverse)
        elif sort_by == "confidence_score":
            filtered_entities.sort(key=lambda x: x.confidence_score, reverse=reverse)

        return filtered_entities[offset:offset + limit]

    # List relationships
    relationships = GraphQLList(RelationshipType,
        limit=Int(default_value=50),
        offset=Int(default_value=0),
        source_entity=String(),
        target_entity=String(),
        relationship_type=String(),
        strength_min=Float(default_value=0.0),
        confidence_min=Float(default_value=0.0),
        sort_by=String(default_value="strength"),
        sort_order=String(default_value="desc")
    )

    def resolve_relationships(self, info, limit=50, offset=0, source_entity=None, target_entity=None,
                            relationship_type=None, strength_min=0.0, confidence_min=0.0,
                            sort_by="strength", sort_order="desc"):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return []

        relationships = []

        for source, target, edge_type, edge_data in kg_manager.kg.graph.edges(keys=True, data=True):
            if relationship_type and edge_type != relationship_type:
                continue
            if edge_data.get("strength", 0) < strength_min:
                continue
            if edge_data.get("confidence", 0) < confidence_min:
                continue

            # Get entity names
            source_name = ""
            target_name = ""

            if source in kg_manager.kg.graph.nodes:
                source_node = kg_manager.kg.graph.nodes[source]
                if source_node.get("node_type") == "entity":
                    source_name = source_node["properties"].get("name", "")

            if target in kg_manager.kg.graph.nodes:
                target_node = kg_manager.kg.graph.nodes[target]
                if target_node.get("node_type") == "entity":
                    target_name = target_node["properties"].get("name", "")

            if source_entity and source_name != source_entity:
                continue
            if target_entity and target_name != target_entity:
                continue

            relationship = RelationshipType(
                source_entity_id=source,
                target_entity_id=target,
                relationship_type=edge_type,
                strength=edge_data.get("strength", 0),
                confidence=edge_data.get("confidence", 0),
                context=edge_data.get("context", ""),
                timestamp=edge_data.get("timestamp"),
                co_occurrence_count=edge_data.get("co_occurrence_count", 0),
                proximity_score=edge_data.get("proximity_score", 0)
            )
            relationships.append(relationship)

        # Sort relationships
        reverse = sort_order.lower() == "desc"
        if sort_by == "strength":
            relationships.sort(key=lambda x: x.strength, reverse=reverse)
        elif sort_by == "confidence":
            relationships.sort(key=lambda x: x.confidence, reverse=reverse)
        elif sort_by == "co_occurrence_count":
            relationships.sort(key=lambda x: x.co_occurrence_count, reverse=reverse)

        return relationships[offset:offset + limit]

    # Advanced search
    search = GraphQLList(SearchResultType,
        query=String(required=True),
        search_type=String(default_value="both"),  # "articles", "entities", "both"
        limit=Int(default_value=50),
        offset=Int(default_value=0),
        filters=graphene.JSONString()
    )

    def resolve_search(self, info, query, search_type="both", limit=50, offset=0, filters=None):
        kg_manager = info.context.get('kg_manager')
        if not kg_manager:
            return []

        results = []
        query_lower = query.lower()

        # Search articles
        if search_type in ["articles", "both"]:
            for node_id, node_data in kg_manager.kg.graph.nodes(data=True):
                if node_data.get("node_type") == "article":
                    article_data = node_data["properties"]
                    title = article_data.get("title", "").lower()
                    content = article_data.get("content", "").lower()

                    score = 0
                    if query_lower in title:
                        score += 1.0
                    if query_lower in content:
                        score += 0.5

                    if score > 0:
                        # Apply filters
                        if filters:
                            if "domain" in filters and article_data.get("domain") != filters["domain"]:
                                continue
                            if "news_score_min" in filters and article_data.get("news_score", 0) < filters["news_score_min"]:
                                continue

                        result = SearchResultType(
                            type="article",
                            id=node_id,
                            title=article_data.get("title", ""),
                            content=article_data.get("content", "")[:200] + "..." if len(article_data.get("content", "")) > 200 else article_data.get("content", ""),
                            score=score,
                            metadata={
                                "url": article_data.get("url", ""),
                                "domain": article_data.get("domain", ""),
                                "published_date": article_data.get("published_date"),
                                "news_score": article_data.get("news_score", 0),
                                "entity_count": sum(len(entities) for entities in article_data.get("entities", {}).values())
                            }
                        )
                        results.append(result)

        # Search entities
        if search_type in ["entities", "both"]:
            entities = kg_manager.kg.query_entities(limit=1000)
            for entity in entities:
                name = entity.get("name", "").lower()
                if query_lower in name:
                    score = 1.0 if query_lower == name else 0.7

                    result = SearchResultType(
                        type="entity",
                        id=entity["node_id"],
                        title=entity.get("name", ""),
                        content=f"Entity of type {entity.get('entity_type', 'unknown')} mentioned {entity.get('mention_count', 0)} times",
                        score=score,
                        metadata={
                            "entity_type": entity.get("entity_type", ""),
                            "mention_count": entity.get("mention_count", 0),
                            "first_seen": entity.get("first_seen", ""),
                            "last_seen": entity.get("last_seen", ""),
                            "aliases": entity.get("aliases", [])
                        }
                    )
                    results.append(result)

        # Sort by score and apply pagination
        results.sort(key=lambda x: x.score, reverse=True)
        return results[offset:offset + limit]

    # Export status query
    export_status = Field(ExportStatusType, job_id=String(required=True))

    def resolve_export_status(self, info, job_id):
        # This would need to be implemented to check actual export status
        # For now, return a placeholder
        return ExportStatusType(
            job_id=job_id,
            status="unknown",
            progress=0.0,
            items_processed=0,
            error=None,
            updated_at=datetime.now().isoformat()
        )

# Mutation class for exports
class Mutation(ObjectType):
    """Root GraphQL mutation"""

    # Export mutations
    export_articles = ExportArticles.Field()
    export_entities = ExportEntities.Field()
    export_relationships = ExportRelationships.Field()

# Create GraphQL schema with mutations
schema = Schema(query=Query, mutation=Mutation)

# Global instances (would be dependency injection in production)
kg_manager = None
archive_manager = None

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager"""
    global kg_manager, archive_manager

    try:
        # Initialize knowledge graph manager
        kg_manager = KnowledgeGraphManager()
        logger.info("✅ Knowledge Graph Manager initialized")

        # Initialize archive manager
        archive_manager = ArchiveManager()
        logger.info("✅ Archive Manager initialized")

        logger.info("🎉 GraphQL API startup complete")

        yield

    except Exception as e:
        logger.error(f"❌ Error during startup: {e}")
        raise
    finally:
        # Cleanup on shutdown
        logger.info("🛑 Shutting down GraphQL API...")
        kg_manager = None
        archive_manager = None
        logger.info("✅ GraphQL API shutdown complete")

# FastAPI application
app = FastAPI(
    title="JustNews Agent - GraphQL Archive API",
    description="GraphQL interface for complex knowledge graph queries and flexible data access",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_kg_manager():
    """Dependency for knowledge graph manager"""
    return kg_manager

async def get_archive_manager():
    """Dependency for archive manager"""
    return archive_manager

# GraphQL endpoint with context
@app.post("/graphql")
async def graphql_endpoint(request: Request):
    """GraphQL endpoint"""
    # Get the query from request
    data = await request.json()
    query = data.get("query", "")
    variables = data.get("variables", {})

    # Execute query with context
    context = {
        'kg_manager': kg_manager,
        'archive_manager': archive_manager,
        'request': request
    }

    result = await graphql(
        schema,
        query,
        variable_values=variables,
        context_value=context
    )

    if result.errors:
        return JSONResponse(
            status_code=400,
            content={"errors": [str(error) for error in result.errors]}
        )

    return JSONResponse(content={"data": result.data})

# Health check endpoint
@app.get("/health")
async def health_check(request: Request):
    """API health check endpoint"""
    return {
        "status": "healthy",
        "service": "GraphQL Archive API",
        "version": "3.0.0",
        "services": {
            "knowledge_graph": kg_manager is not None,
            "archive": archive_manager is not None
        }
    }

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "timestamp": datetime.now().isoformat()
        }
    )

if __name__ == "__main__":
    # Run the GraphQL API server
    uvicorn.run(
        "archive_graphql:app",
        host="0.0.0.0",
        port=8020,  # GraphQL API port (REST API uses 8021)
        reload=True,
        log_level="info"
    )
