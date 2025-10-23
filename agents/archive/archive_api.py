from common.observability import get_logger

#!/usr/bin/env python3
"""
Phase 3 Sprint 3-4: RESTful Archive API

FastAPI-based REST API for knowledge graph and archive access.
Provides endpoints for querying articles, entities, relationships, and search functionality.

API Endpoints:
- GET /articles - List articles with filtering and pagination
- GET /articles/{id} - Get specific article details
- GET /entities - List entities with filtering
- GET /entities/{id} - Get entity details and relationships
- GET /relationships - Query relationships between entities
- POST /search - Advanced search across articles and entities
- GET /graph/statistics - Get knowledge graph statistics
- GET /health - API health check
"""

import hashlib
import json
import os
import requests
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from agents.archive.archive_manager import ArchiveManager
from agents.archive.knowledge_graph import KnowledgeGraphManager
from agents.common.auth_api import router as auth_router

logger = get_logger(__name__)

# Rate Limiting Configuration
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Pydantic models for request/response
class ArticleFilter(BaseModel):
    """Filter parameters for article queries"""
    domain: str | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    news_score_min: float | None = Field(None, ge=0.0, le=1.0)
    news_score_max: float | None = Field(None, ge=0.0, le=1.0)
    has_entities: bool | None = None
    entity_type: str | None = None
    search_query: str | None = None

class EntityFilter(BaseModel):
    """Filter parameters for entity queries"""
    entity_type: str | None = None
    mention_count_min: int | None = Field(None, ge=0)
    mention_count_max: int | None = Field(None, ge=0)
    first_seen_after: datetime | None = None
    last_seen_before: datetime | None = None
    search_query: str | None = None

class RelationshipFilter(BaseModel):
    """Filter parameters for relationship queries"""
    source_entity: str | None = None
    target_entity: str | None = None
    relationship_type: str | None = None
    strength_min: float | None = Field(None, ge=0.0, le=1.0)
    confidence_min: float | None = Field(None, ge=0.0, le=1.0)
    time_window: str | None = None

class SearchRequest(BaseModel):
    """Advanced search request"""
    query: str = Field(..., min_length=1, max_length=500)
    search_type: str = Field("articles", pattern="^(articles|entities|both)$")
    filters: dict[str, Any] | None = None
    limit: int = Field(50, ge=1, le=1000)
    offset: int = Field(0, ge=0)

class ArticleResponse(BaseModel):
    """Article response model"""
    article_id: str
    url: str
    title: str
    domain: str
    published_date: str | None
    entities: dict[str, list[str]]
    news_score: float
    extraction_method: str
    total_entities: int
    relationships_count: int

class EntityResponse(BaseModel):
    """Entity response model"""
    entity_id: str
    name: str
    entity_type: str
    mention_count: int
    first_seen: str
    last_seen: str
    aliases: list[str]
    cluster_size: int
    confidence_score: float

class RelationshipResponse(BaseModel):
    """Relationship response model"""
    source_entity: str
    target_entity: str
    relationship_type: str
    strength: float
    confidence: float
    context: str
    timestamp: str
    co_occurrence_count: int
    proximity_score: float

class SearchResult(BaseModel):
    """Search result model"""
    type: str
    id: str
    title: str
    content: str
    score: float
    metadata: dict[str, Any]

class PaginatedResponse(BaseModel):
    """Paginated response wrapper"""
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool

class APIResponse(BaseModel):
    """Generic API response"""
    success: bool
    data: Any
    message: str | None = None
    timestamp: str

class ToolCall(BaseModel):
    """Generic tool invocation payload (MCP-style)"""
    args: list[Any] | None = None
    kwargs: dict[str, Any] | None = None

# Lifespan context manager for startup/shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events"""
    global kg_manager, archive_manager

    logger.info("🚀 Starting JustNews Archive API...")

    try:
        # Initialize knowledge graph manager
        kg_manager = KnowledgeGraphManager()
        logger.info("✅ Knowledge Graph Manager initialized")

        # Initialize archive manager
        archive_manager = ArchiveManager()
        logger.info("✅ Archive Manager initialized")

        # Attempt MCP Bus registration (non-fatal if bus not running)
        try:
            mcp_bus_url = os.getenv("MCP_BUS_URL", "http://localhost:8000")
            registration_payload = {"name": "archive_api", "address": "http://localhost:8021"}
            resp = requests.post(f"{mcp_bus_url}/register", json=registration_payload, timeout=(2,5))
            if resp.status_code in (200, 201):
                logger.info("🔌 Registered archive_api with MCP Bus")
            else:
                logger.warning(f"⚠️ MCP Bus registration failed status={resp.status_code}")
        except Exception as e:
            logger.warning(f"⚠️ MCP Bus registration exception: {e}")

        logger.info("🎉 Archive API startup complete")

        yield

    except Exception as e:
        logger.error(f"❌ Error during startup: {e}")
        raise
    finally:
        logger.info("🛑 Shutting down Archive API...")
        # Cleanup resources if needed
        kg_manager = None
        archive_manager = None
        logger.info("✅ Archive API shutdown complete")

# FastAPI application
app = FastAPI(
    title="JustNews Agent - Archive API",
    description="RESTful API for accessing knowledge graph and archived news data",
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

# Include authentication router
app.include_router(auth_router)

# Global instances (would be dependency injection in production)
kg_manager = None
archive_manager = None

async def get_kg_manager() -> KnowledgeGraphManager:
    """Dependency for knowledge graph manager"""
    return kg_manager

async def get_archive_manager() -> ArchiveManager:
    """Dependency for archive manager"""
    return archive_manager

@app.get("/health")
@limiter.limit("30/minute")  # Health checks can be more frequent
async def health_check(request: Request):
    """API health check endpoint"""
    return APIResponse(
        success=True,
        data={
            "status": "healthy",
            "services": {
                "knowledge_graph": kg_manager is not None,
                "archive": archive_manager is not None
            },
            "version": "3.0.0"
        },
        message="API is operational",
        timestamp=datetime.now().isoformat()
    )

@app.post("/archive_from_crawler")
@limiter.limit("10/minute")
async def archive_from_crawler_endpoint(request: Request, call: ToolCall, archive_manager: ArchiveManager = Depends(get_archive_manager)):
    """Archive crawler results batch and run Knowledge Graph processing.

    Expected body: {"args": [], "kwargs": {"crawler_results": {...}}}
    """
    try:
        if archive_manager is None:
            raise HTTPException(status_code=503, detail="Archive manager not initialized")
        crawler_results = None
        if call.kwargs and isinstance(call.kwargs, dict):
            crawler_results = call.kwargs.get("crawler_results")
        if not crawler_results:
            raise HTTPException(status_code=400, detail="crawler_results missing in kwargs")
        summary = await archive_manager.archive_from_crawler(crawler_results)
        if isinstance(summary, dict) and summary.get("error"):
            return APIResponse(success=False, data=summary, message=summary.get("error"), timestamp=datetime.now().isoformat())
        return APIResponse(success=True, data=summary, message="Archive and KG processing complete", timestamp=datetime.now().isoformat())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"archive_from_crawler endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/articles", response_model=PaginatedResponse)
@limiter.limit("20/minute")  # List operations are resource intensive
async def list_articles(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    domain: str | None = Query(None, description="Filter by domain"),
    published_after: datetime | None = Query(None, description="Published after date"),
    published_before: datetime | None = Query(None, description="Published before date"),
    news_score_min: float | None = Query(None, ge=0.0, le=1.0, description="Minimum news score"),
    entity_type: str | None = Query(None, description="Filter by entity type presence"),
    search_query: str | None = Query(None, description="Search in title/content"),
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """
    List articles with filtering and pagination

    Query parameters:
    - page: Page number (default: 1)
    - page_size: Items per page (default: 20, max: 100)
    - domain: Filter by news domain
    - published_after: Filter articles published after this date
    - published_before: Filter articles published before this date
    - news_score_min: Minimum news score (0.0-1.0)
    - entity_type: Filter articles containing specific entity type
    - search_query: Search term in title or content
    """
    try:
        # Get all articles from knowledge graph
        all_articles = []
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

                if news_score_min and article_data.get("news_score", 0) < news_score_min:
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

                # Create response object
                entities = article_data.get("entities", {})
                total_entities = sum(len(entity_list) for entity_list in entities.values())

                article_response = ArticleResponse(
                    article_id=node_id,
                    url=article_data.get("url", ""),
                    title=article_data.get("title", ""),
                    domain=article_data.get("domain", ""),
                    published_date=article_data.get("published_date"),
                    entities=entities,
                    news_score=article_data.get("news_score", 0.0),
                    extraction_method=article_data.get("extraction_method", ""),
                    total_entities=total_entities,
                    relationships_count=0  # Would need to calculate from graph
                )

                all_articles.append(article_response)

        # Sort by published date (newest first)
        all_articles.sort(key=lambda x: x.published_date or "", reverse=True)

        # Pagination
        total_items = len(all_articles)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = all_articles[start_idx:end_idx]

        return PaginatedResponse(
            items=paginated_items,
            total=total_items,
            page=page,
            page_size=page_size,
            has_next=end_idx < total_items,
            has_prev=page > 1
        )

    except Exception as e:
        logger.error(f"Error listing articles: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/articles/{article_id}")
@limiter.limit("60/minute")  # Individual item retrieval can be more frequent
async def get_article(
    request: Request,
    article_id: str,
    include_relationships: bool = Query(False, description="Include relationship details"),
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Get detailed information about a specific article"""
    try:
        if article_id not in kg_manager.kg.graph.nodes:
            raise HTTPException(status_code=404, detail="Article not found")

        node_data = kg_manager.kg.graph.nodes[article_id]
        if node_data.get("node_type") != "article":
            raise HTTPException(status_code=404, detail="Not an article node")

        article_data = node_data["properties"]

        # Get relationships if requested
        relationships = None
        if include_relationships:
            relationships = kg_manager.kg.query_article_relationships(article_id)

        response = {
            "article_id": article_id,
            "url": article_data.get("url", ""),
            "title": article_data.get("title", ""),
            "domain": article_data.get("domain", ""),
            "published_date": article_data.get("published_date"),
            "content": article_data.get("content", ""),
            "entities": article_data.get("entities", {}),
            "news_score": article_data.get("news_score", 0.0),
            "extraction_method": article_data.get("extraction_method", ""),
            "publisher": article_data.get("publisher", ""),
            "canonical_url": article_data.get("canonical_url", ""),
            "relationships": relationships
        }

        return APIResponse(
            success=True,
            data=response,
            message="Article retrieved successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting article {article_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/entities", response_model=PaginatedResponse)
@limiter.limit("20/minute")  # Entity listing is resource intensive
async def list_entities(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    mention_count_min: int | None = Query(None, ge=0, description="Minimum mention count"),
    search_query: str | None = Query(None, description="Search in entity name"),
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """List entities with filtering and pagination"""
    try:
        # Get entities from knowledge graph
        all_entities = kg_manager.kg.query_entities(entity_type, limit=10000)  # Large limit for now

        # Apply additional filters
        filtered_entities = []
        for entity in all_entities:
            if mention_count_min and entity.get("mention_count", 0) < mention_count_min:
                continue

            if search_query:
                name_lower = entity.get("name", "").lower()
                query_lower = search_query.lower()
                if query_lower not in name_lower:
                    continue

            # Create response object
            entity_response = EntityResponse(
                entity_id=entity["node_id"],
                name=entity.get("name", ""),
                entity_type=entity.get("entity_type", ""),
                mention_count=entity.get("mention_count", 0),
                first_seen=entity.get("first_seen", ""),
                last_seen=entity.get("last_seen", ""),
                aliases=entity.get("aliases", []),
                cluster_size=entity.get("cluster_size", 1),
                confidence_score=entity.get("confidence", 0.8)
            )

            filtered_entities.append(entity_response)

        # Sort by mention count (most mentioned first)
        filtered_entities.sort(key=lambda x: x.mention_count, reverse=True)

        # Pagination
        total_items = len(filtered_entities)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_items = filtered_entities[start_idx:end_idx]

        return PaginatedResponse(
            items=paginated_items,
            total=total_items,
            page=page,
            page_size=page_size,
            has_next=end_idx < total_items,
            has_prev=page > 1
        )

    except Exception as e:
        logger.error(f"Error listing entities: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/entities/{entity_id}")
@limiter.limit("60/minute")  # Individual entity retrieval
async def get_entity(
    request: Request,
    entity_id: str,
    include_relationships: bool = Query(True, description="Include relationship details"),
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Get detailed information about a specific entity"""
    try:
        if entity_id not in kg_manager.kg.graph.nodes:
            raise HTTPException(status_code=404, detail="Entity not found")

        node_data = kg_manager.kg.graph.nodes[entity_id]
        if node_data.get("node_type") != "entity":
            raise HTTPException(status_code=404, detail="Not an entity node")

        entity_data = node_data["properties"]

        # Get relationships
        relationships = []
        if include_relationships:
            # Get incoming and outgoing edges
            for source, target, edge_type, edge_data in kg_manager.kg.graph.edges(entity_id, keys=True, data=True):
                relationships.append({
                    "source_entity": source,
                    "target_entity": target,
                    "relationship_type": edge_type,
                    "strength": edge_data.get("strength", 0),
                    "confidence": edge_data.get("confidence", 0),
                    "context": edge_data.get("context", ""),
                    "timestamp": edge_data.get("timestamp", ""),
                    "co_occurrence_count": edge_data.get("co_occurrence_count", 0),
                    "proximity_score": edge_data.get("proximity_score", 0)
                })

        response = {
            "entity_id": entity_id,
            "name": entity_data.get("name", ""),
            "entity_type": entity_data.get("entity_type", ""),
            "mention_count": entity_data.get("mention_count", 0),
            "first_seen": entity_data.get("first_seen", ""),
            "last_seen": entity_data.get("last_seen", ""),
            "aliases": entity_data.get("aliases", []),
            "cluster_size": entity_data.get("cluster_size", 1),
            "confidence_score": entity_data.get("confidence", 0.8),
            "relationships": relationships if include_relationships else None
        }

        return APIResponse(
            success=True,
            data=response,
            message="Entity retrieved successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting entity {entity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/search")
@limiter.limit("10/minute")  # Search is computationally expensive, more restrictive
async def search_content(
    request: Request,
    search_request: SearchRequest,
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Advanced search across articles and entities"""
    try:
        results = []
        query = search_request.query.lower()

        # Search articles
        if search_request.search_type in ["articles", "both"]:
            for node_id, node_data in kg_manager.kg.graph.nodes(data=True):
                if node_data.get("node_type") == "article":
                    article_data = node_data["properties"]
                    title = article_data.get("title", "").lower()
                    content = article_data.get("content", "").lower()

                    # Calculate relevance score
                    score = 0
                    if query in title:
                        score += 1.0  # Title match gets highest score
                    if query in content:
                        score += 0.5  # Content match gets medium score

                    if score > 0:
                        # Apply additional filters
                        if search_request.filters:
                            if "domain" in search_request.filters:
                                if article_data.get("domain") != search_request.filters["domain"]:
                                    continue
                            if "news_score_min" in search_request.filters:
                                if article_data.get("news_score", 0) < search_request.filters["news_score_min"]:
                                    continue

                        result = SearchResult(
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
        if search_request.search_type in ["entities", "both"]:
            entities = kg_manager.kg.query_entities(limit=1000)
            for entity in entities:
                name = entity.get("name", "").lower()
                if query in name:
                    score = 1.0 if query == name else 0.7  # Exact match vs partial

                    result = SearchResult(
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
        start_idx = search_request.offset
        end_idx = start_idx + search_request.limit
        paginated_results = results[start_idx:end_idx]

        return APIResponse(
            success=True,
            data={
                "results": paginated_results,
                "total": len(results),
                "returned": len(paginated_results),
                "query": search_request.query,
                "search_type": search_request.search_type
            },
            message=f"Found {len(results)} results for query: {search_request.query}",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error performing search: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/graph/statistics")
@limiter.limit("30/minute")  # Statistics can be moderately frequent
async def get_graph_statistics(request: Request, kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)):
    """Get comprehensive knowledge graph statistics"""
    try:
        stats = kg_manager.kg.get_graph_statistics()
        clustering_stats = kg_manager.kg.get_clustering_statistics()

        # Combine statistics
        combined_stats = {
            **stats,
            "clustering": clustering_stats,
            "last_updated": datetime.now().isoformat()
        }

        return APIResponse(
            success=True,
            data=combined_stats,
            message="Knowledge graph statistics retrieved successfully",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting graph statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/relationships")
@limiter.limit("15/minute")  # Relationship queries are complex
async def get_relationships(
    request: Request,
    source_entity: str | None = Query(None, description="Source entity name"),
    target_entity: str | None = Query(None, description="Target entity name"),
    relationship_type: str | None = Query(None, description="Relationship type"),
    strength_min: float | None = Query(None, ge=0.0, le=1.0, description="Minimum relationship strength"),
    confidence_min: float | None = Query(None, ge=0.0, le=1.0, description="Minimum confidence score"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of relationships"),
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Query relationships between entities"""
    try:
        relationships = []

        # Iterate through all edges
        for source, target, edge_type, edge_data in kg_manager.kg.graph.edges(keys=True, data=True):
            # Apply filters
            if relationship_type and edge_type != relationship_type:
                continue

            if strength_min and edge_data.get("strength", 0) < strength_min:
                continue

            if confidence_min and edge_data.get("confidence", 0) < confidence_min:
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

            relationship = RelationshipResponse(
                source_entity=source_name,
                target_entity=target_name,
                relationship_type=edge_type,
                strength=edge_data.get("strength", 0),
                confidence=edge_data.get("confidence", 0),
                context=edge_data.get("context", ""),
                timestamp=edge_data.get("timestamp", ""),
                co_occurrence_count=edge_data.get("co_occurrence_count", 0),
                proximity_score=edge_data.get("proximity_score", 0)
            )

            relationships.append(relationship)

            if len(relationships) >= limit:
                break

        # Sort by strength (strongest first)
        relationships.sort(key=lambda x: x.strength, reverse=True)

        return APIResponse(
            success=True,
            data={
                "relationships": relationships,
                "total": len(relationships),
                "filters_applied": {
                    "source_entity": source_entity,
                    "target_entity": target_entity,
                    "relationship_type": relationship_type,
                    "strength_min": strength_min,
                    "confidence_min": confidence_min
                }
            },
            message=f"Retrieved {len(relationships)} relationships",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting relationships: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/entities/{entity_id}/external-info")
@limiter.limit("30/minute")  # External info queries
async def get_entity_external_info(
    request: Request,
    entity_id: str,
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Get external knowledge base information for a specific entity"""
    try:
        # Get entity details first
        if entity_id not in kg_manager.kg.graph.nodes:
            raise HTTPException(status_code=404, detail="Entity not found")

        node_data = kg_manager.kg.graph.nodes[entity_id]
        if node_data.get("node_type") != "entity":
            raise HTTPException(status_code=404, detail="Not an entity node")

        entity_data = node_data["properties"]
        entity_name = entity_data.get("name", "")
        entity_type = entity_data.get("entity_type")

        # Get external information
        external_info = await kg_manager.get_entity_external_info(entity_name, entity_type)

        response = {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "external_enrichment": external_info,
            "enrichment_timestamp": datetime.now().isoformat()
        }

        return APIResponse(
            success=True,
            data=response,
            message="Entity external information retrieved successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting external info for entity {entity_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/entities/enrich")
@limiter.limit("5/minute")  # Enrichment is computationally expensive
async def enrich_entities(
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Maximum number of entities to enrich"),
    background_tasks: BackgroundTasks = None,
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Trigger entity enrichment with external knowledge bases"""
    try:
        # Start enrichment as background task
        if background_tasks:
            background_tasks.add_task(kg_manager.enrich_entities_with_external_knowledge, limit)

            return APIResponse(
                success=True,
                data={
                    "enrichment_started": True,
                    "entities_to_process": limit,
                    "status": "running_in_background"
                },
                message="Entity enrichment started in background",
                timestamp=datetime.now().isoformat()
            )
        else:
            # Run synchronously (for testing)
            result = await kg_manager.enrich_entities_with_external_knowledge(limit)

            return APIResponse(
                success=True,
                data=result,
                message="Entity enrichment completed",
                timestamp=datetime.now().isoformat()
            )

    except Exception as e:
        logger.error(f"Error starting entity enrichment: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/entities/enrichment-statistics")
@limiter.limit("20/minute")  # Statistics queries
async def get_entity_enrichment_statistics(request: Request, kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)):
    """Get statistics about entity enrichment operations"""
    try:
        stats = kg_manager.get_entity_linking_statistics()

        return APIResponse(
            success=True,
            data=stats,
            message="Entity enrichment statistics retrieved successfully",
            timestamp=datetime.now().isoformat()
        )

    except Exception as e:
        logger.error(f"Error getting enrichment statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Export endpoints
@app.post("/export/articles")
@limiter.limit("3/minute")  # Bulk exports are resource intensive
async def export_articles(
    request: Request,
    export_request: dict[str, Any],
    background_tasks: BackgroundTasks,
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Export articles in bulk with filtering and format options"""
    try:
        # Extract export parameters
        filters = export_request.get("filters", {})
        format_type = export_request.get("format", "json")
        limit = min(export_request.get("limit", 1000), 10000)  # Cap at 10K for safety
        include_content = export_request.get("include_content", True)
        include_entities = export_request.get("include_entities", True)

        # Validate format
        supported_formats = ["json", "csv", "jsonl"]
        if format_type not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {format_type}. Supported: {supported_formats}"
            )

        # Generate export job ID
        job_id = f"export_articles_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(export_request).encode()).hexdigest()[:8]}"

        # Start export as background task
        background_tasks.add_task(
            _perform_articles_export,
            job_id,
            filters,
            format_type,
            limit,
            include_content,
            include_entities,
            kg_manager
        )

        return APIResponse(
            success=True,
            data={
                "job_id": job_id,
                "status": "queued",
                "estimated_items": limit,
                "format": format_type,
                "filters": filters
            },
            message="Article export job queued successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing article export: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/export/entities")
@limiter.limit("3/minute")  # Bulk exports are resource intensive
async def export_entities(
    request: Request,
    export_request: dict[str, Any],
    background_tasks: BackgroundTasks,
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Export entities in bulk with filtering and format options"""
    try:
        # Extract export parameters
        filters = export_request.get("filters", {})
        format_type = export_request.get("format", "json")
        limit = min(export_request.get("limit", 5000), 50000)  # Cap at 50K for safety
        include_relationships = export_request.get("include_relationships", False)
        include_external_info = export_request.get("include_external_info", False)

        # Validate format
        supported_formats = ["json", "csv", "jsonl"]
        if format_type not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {format_type}. Supported: {supported_formats}"
            )

        # Generate export job ID
        job_id = f"export_entities_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(export_request).encode()).hexdigest()[:8]}"

        # Start export as background task
        background_tasks.add_task(
            _perform_entities_export,
            job_id,
            filters,
            format_type,
            limit,
            include_relationships,
            include_external_info,
            kg_manager
        )

        return APIResponse(
            success=True,
            data={
                "job_id": job_id,
                "status": "queued",
                "estimated_items": limit,
                "format": format_type,
                "filters": filters
            },
            message="Entity export job queued successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing entity export: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/export/relationships")
@limiter.limit("3/minute")  # Bulk exports are resource intensive
async def export_relationships(
    request: Request,
    export_request: dict[str, Any],
    background_tasks: BackgroundTasks,
    kg_manager: KnowledgeGraphManager = Depends(get_kg_manager)
):
    """Export relationships in bulk with filtering and format options"""
    try:
        # Extract export parameters
        filters = export_request.get("filters", {})
        format_type = export_request.get("format", "json")
        limit = min(export_request.get("limit", 10000), 100000)  # Cap at 100K for safety

        # Validate format
        supported_formats = ["json", "csv", "jsonl", "graphml"]
        if format_type not in supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported format: {format_type}. Supported: {supported_formats}"
            )

        # Generate export job ID
        job_id = f"export_relationships_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hashlib.md5(str(export_request).encode()).hexdigest()[:8]}"

        # Start export as background task
        background_tasks.add_task(
            _perform_relationships_export,
            job_id,
            filters,
            format_type,
            limit,
            kg_manager
        )

        return APIResponse(
            success=True,
            data={
                "job_id": job_id,
                "status": "queued",
                "estimated_items": limit,
                "format": format_type,
                "filters": filters
            },
            message="Relationship export job queued successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queuing relationship export: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/export/status/{job_id}")
@limiter.limit("20/minute")  # Status checks can be frequent
async def get_export_status(request: Request, job_id: str):
    """Get status of an export job"""
    try:
        # Check if export job exists and get status
        export_status = _get_export_job_status(job_id)

        if not export_status:
            raise HTTPException(status_code=404, detail="Export job not found")

        return APIResponse(
            success=True,
            data=export_status,
            message="Export job status retrieved successfully",
            timestamp=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting export status for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/export/download/{job_id}")
@limiter.limit("10/minute")  # Downloads are bandwidth intensive
async def download_export(request: Request, job_id: str):
    """Download completed export file"""
    try:
        # Get export file path
        file_path = _get_export_file_path(job_id)

        if not file_path or not file_path.exists():
            raise HTTPException(status_code=404, detail="Export file not found or not ready")

        # Return file
        return FileResponse(
            path=file_path,
            filename=f"{job_id}.{_get_export_format(job_id)}",
            media_type="application/octet-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading export for job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

# Background export functions
async def _perform_articles_export(job_id: str, filters: dict[str, Any], format_type: str,
                                 limit: int, include_content: bool, include_entities: bool,
                                 kg_manager: KnowledgeGraphManager):
    """Perform articles export in background"""
    try:
        _update_export_status(job_id, "running", 0)

        # Collect articles based on filters
        articles = []
        processed = 0

        for node_id, node_data in kg_manager.kg.graph.nodes(data=True):
            if node_data.get("node_type") == "article":
                article_data = node_data["properties"]

                # Apply filters
                if _matches_article_filters(article_data, filters):
                    # Prepare export data
                    export_data = {
                        "article_id": node_id,
                        "url": article_data.get("url", ""),
                        "title": article_data.get("title", ""),
                        "domain": article_data.get("domain", ""),
                        "published_date": article_data.get("published_date"),
                        "news_score": article_data.get("news_score", 0.0),
                        "extraction_method": article_data.get("extraction_method", ""),
                        "publisher": article_data.get("publisher", "")
                    }

                    if include_content:
                        export_data["content"] = article_data.get("content", "")

                    if include_entities:
                        export_data["entities"] = article_data.get("entities", {})

                    articles.append(export_data)
                    processed += 1

                    # Update progress
                    if processed % 100 == 0:
                        _update_export_status(job_id, "running", processed / limit)

                    if processed >= limit:
                        break

        # Export to file
        await _export_to_file(job_id, articles, format_type, "articles")

        _update_export_status(job_id, "completed", 1.0, processed)

        logger.info(f"✅ Articles export completed: {job_id} ({processed} articles)")

    except Exception as e:
        logger.error(f"Articles export failed for job {job_id}: {e}")
        _update_export_status(job_id, "failed", 0, error=str(e))

async def _perform_entities_export(job_id: str, filters: dict[str, Any], format_type: str,
                                 limit: int, include_relationships: bool, include_external_info: bool,
                                 kg_manager: KnowledgeGraphManager):
    """Perform entities export in background"""
    try:
        _update_export_status(job_id, "running", 0)

        # Collect entities
        entities = []
        processed = 0

        all_entities = kg_manager.kg.query_entities(limit=limit * 2)  # Get more to filter

        for entity in all_entities:
            if _matches_entity_filters(entity, filters):
                # Prepare export data
                export_data = {
                    "entity_id": entity["node_id"],
                    "name": entity.get("name", ""),
                    "entity_type": entity.get("entity_type", ""),
                    "mention_count": entity.get("mention_count", 0),
                    "first_seen": entity.get("first_seen", ""),
                    "last_seen": entity.get("last_seen", ""),
                    "aliases": entity.get("aliases", []),
                    "cluster_size": entity.get("cluster_size", 1),
                    "confidence_score": entity.get("confidence", 0.8)
                }

                if include_relationships:
                    # Get relationships for this entity
                    relationships = []
                    for source, target, edge_type, edge_data in kg_manager.kg.graph.edges(entity["node_id"], keys=True, data=True):
                        relationships.append({
                            "target_entity": target,
                            "relationship_type": edge_type,
                            "strength": edge_data.get("strength", 0),
                            "confidence": edge_data.get("confidence", 0),
                            "timestamp": edge_data.get("timestamp", "")
                        })
                    export_data["relationships"] = relationships

                if include_external_info:
                    # Get external enrichment data
                    external_info = await kg_manager.get_entity_external_info(
                        entity.get("name", ""), entity.get("entity_type")
                    )
                    export_data["external_enrichment"] = external_info

                entities.append(export_data)
                processed += 1

                # Update progress
                if processed % 50 == 0:
                    _update_export_status(job_id, "running", processed / limit)

                if processed >= limit:
                    break

        # Export to file
        await _export_to_file(job_id, entities, format_type, "entities")

        _update_export_status(job_id, "completed", 1.0, processed)

        logger.info(f"✅ Entities export completed: {job_id} ({processed} entities)")

    except Exception as e:
        logger.error(f"Entities export failed for job {job_id}: {e}")
        _update_export_status(job_id, "failed", 0, error=str(e))

async def _perform_relationships_export(job_id: str, filters: dict[str, Any], format_type: str,
                                      limit: int, kg_manager: KnowledgeGraphManager):
    """Perform relationships export in background"""
    try:
        _update_export_status(job_id, "running", 0)

        # Collect relationships
        relationships = []
        processed = 0

        for source, target, edge_type, edge_data in kg_manager.kg.graph.edges(keys=True, data=True):
            # Apply filters
            if _matches_relationship_filters(edge_data, filters):
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

                relationship_data = {
                    "source_entity_id": source,
                    "source_entity_name": source_name,
                    "target_entity_id": target,
                    "target_entity_name": target_name,
                    "relationship_type": edge_type,
                    "strength": edge_data.get("strength", 0),
                    "confidence": edge_data.get("confidence", 0),
                    "context": edge_data.get("context", ""),
                    "timestamp": edge_data.get("timestamp", ""),
                    "co_occurrence_count": edge_data.get("co_occurrence_count", 0),
                    "proximity_score": edge_data.get("proximity_score", 0)
                }

                relationships.append(relationship_data)
                processed += 1

                # Update progress
                if processed % 200 == 0:
                    _update_export_status(job_id, "running", processed / limit)

                if processed >= limit:
                    break

        # Export to file
        await _export_to_file(job_id, relationships, format_type, "relationships")

        _update_export_status(job_id, "completed", 1.0, processed)

        logger.info(f"✅ Relationships export completed: {job_id} ({processed} relationships)")

    except Exception as e:
        logger.error(f"Relationships export failed for job {job_id}: {e}")
        _update_export_status(job_id, "failed", 0, error=str(e))

# Helper functions for export operations
def _matches_article_filters(article_data: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Check if article matches export filters"""
    # Domain filter
    if "domain" in filters and article_data.get("domain") != filters["domain"]:
        return False

    # Date range filter
    if "published_after" in filters:
        pub_date = article_data.get("published_date")
        if pub_date:
            try:
                article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                if article_date < datetime.fromisoformat(filters["published_after"]):
                    return False
            except (ValueError, TypeError):
                pass

    if "published_before" in filters:
        pub_date = article_data.get("published_date")
        if pub_date:
            try:
                article_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                if article_date > datetime.fromisoformat(filters["published_before"]):
                    return False
            except (ValueError, TypeError):
                pass

    # News score filter
    if "news_score_min" in filters and article_data.get("news_score", 0) < filters["news_score_min"]:
        return False

    return True

def _matches_entity_filters(entity: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Check if entity matches export filters"""
    # Entity type filter
    if "entity_type" in filters and entity.get("entity_type") != filters["entity_type"]:
        return False

    # Mention count filter
    if "mention_count_min" in filters and entity.get("mention_count", 0) < filters["mention_count_min"]:
        return False

    # Confidence filter
    if "confidence_min" in filters and entity.get("confidence", 0) < filters["confidence_min"]:
        return False

    return True

def _matches_relationship_filters(edge_data: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Check if relationship matches export filters"""
    # Relationship type filter
    if "relationship_type" in filters and edge_data.get("relationship_type") != filters["relationship_type"]:
        return False

    # Strength filter
    if "strength_min" in filters and edge_data.get("strength", 0) < filters["strength_min"]:
        return False

    # Confidence filter
    if "confidence_min" in filters and edge_data.get("confidence", 0) < filters["confidence_min"]:
        return False

    return True

async def _export_to_file(job_id: str, data: list[dict[str, Any]], format_type: str, data_type: str):
    """Export data to file in specified format"""
    export_dir = Path("./exports")
    export_dir.mkdir(exist_ok=True)

    file_path = export_dir / f"{job_id}.{format_type}"

    try:
        if format_type == "json":
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "export_type": data_type,
                    "export_timestamp": datetime.now().isoformat(),
                    "total_items": len(data),
                    "data": data
                }, f, indent=2, ensure_ascii=False, default=str)

        elif format_type == "jsonl":
            with open(file_path, 'w', encoding='utf-8') as f:
                for item in data:
                    f.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')

        elif format_type == "csv":
            if data:
                import csv
                fieldnames = list(data[0].keys())
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    for item in data:
                        # Flatten nested structures for CSV
                        flat_item = {}
                        for key, value in item.items():
                            if isinstance(value, (list, dict)):
                                flat_item[key] = json.dumps(value, ensure_ascii=False, default=str)
                            else:
                                flat_item[key] = value
                        writer.writerow(flat_item)

        elif format_type == "graphml":
            # For relationships, export as GraphML
            import networkx as nx
            G = nx.MultiDiGraph()

            for item in data:
                source = item.get("source_entity_id", "")
                target = item.get("target_entity_id", "")
                if source and target:
                    G.add_edge(source, target,
                             relationship_type=item.get("relationship_type", ""),
                             strength=item.get("strength", 0),
                             confidence=item.get("confidence", 0))

            nx.write_graphml(G, file_path)

        logger.info(f"📄 Exported {len(data)} {data_type} to {file_path}")

    except Exception as e:
        logger.error(f"Failed to export {data_type} to file: {e}")
        raise

# Export job tracking (in-memory for now, could be moved to database)
_export_jobs = {}

def _update_export_status(job_id: str, status: str, progress: float, items_processed: int = 0, error: str = None):
    """Update export job status"""
    _export_jobs[job_id] = {
        "status": status,
        "progress": progress,
        "items_processed": items_processed,
        "error": error,
        "updated_at": datetime.now().isoformat()
    }

def _get_export_job_status(job_id: str) -> dict[str, Any] | None:
    """Get export job status"""
    return _export_jobs.get(job_id)

def _get_export_file_path(job_id: str) -> Path | None:
    """Get export file path"""
    export_dir = Path("./exports")
    # Try different formats
    for fmt in ["json", "jsonl", "csv", "graphml"]:
        file_path = export_dir / f"{job_id}.{fmt}"
        if file_path.exists():
            return file_path
    return None

def _get_export_format(job_id: str) -> str:
    """Get export format for job"""
    file_path = _get_export_file_path(job_id)
    if file_path:
        return file_path.suffix[1:]  # Remove leading dot
    return "json"

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
    # Run the API server
    uvicorn.run(
        "archive_api:app",
        host="0.0.0.0",
        port=8021,  # REST API port (different from GraphQL on 8020)
        reload=True,
        log_level="info"
    )
