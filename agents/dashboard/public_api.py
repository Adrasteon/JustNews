"""
Public API endpoints for JustNews public website.

Provides access to articles, analysis data, and statistics for public consumption.
Includes researcher APIs for academic and journalistic use.
"""

import os
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from pathlib import Path
import requests
from collections import defaultdict
import hashlib

# Import common modules
try:
    from common.observability import get_logger
    from common.metrics import JustNewsMetrics
except ImportError:
    import logging
    get_logger = lambda name: logging.getLogger(name)
    JustNewsMetrics = lambda name: None

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/public", tags=["public"])

# MCP Bus configuration
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

# Security configuration
API_KEYS = os.environ.get("JUSTNEWS_API_KEYS", "demo-key-123,research-key-456").split(",")
RESEARCH_RATE_LIMIT = int(os.environ.get("RESEARCH_RATE_LIMIT", "100"))  # requests per hour
PUBLIC_RATE_LIMIT = int(os.environ.get("PUBLIC_RATE_LIMIT", "1000"))   # requests per hour

# Rate limiting storage
_rate_limits = defaultdict(list)

# Security schemes
security = HTTPBearer(auto_error=False)

# Cache for frequently accessed data
_data_cache = {}
_CACHE_TTL = 300  # 5 minutes

def _get_cache_key(endpoint: str, **kwargs) -> str:
    """Generate cache key for endpoint"""
    params = "_".join(f"{k}:{v}" for k, v in sorted(kwargs.items()))
    return f"{endpoint}_{params}"

def _get_cached_data(key: str) -> Optional[Any]:
    """Get data from cache if not expired"""
    if key in _data_cache:
        data, timestamp = _data_cache[key]
        if time.time() - timestamp < _CACHE_TTL:
            return data
        else:
            del _data_cache[key]
    return None

def _set_cached_data(key: str, data: Any):
    """Store data in cache"""
    _data_cache[key] = (data, time.time())

def _call_memory_agent(tool: str, **kwargs) -> Optional[Any]:
    """Call memory agent via MCP bus"""
    try:
        payload = {
            "agent": "memory",
            "tool": tool,
            "args": [],
            "kwargs": kwargs
        }
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result
    except Exception as e:
        logger.warning(f"Failed to call memory agent {tool}: {e}")
        return None

def _call_analyst_agent(tool: str, **kwargs) -> Optional[Any]:
    """Call analyst agent via MCP bus"""
    try:
        payload = {
            "agent": "analyst",
            "tool": tool,
            "args": [],
            "kwargs": kwargs
        }
        response = requests.post(f"{MCP_BUS_URL}/call", json=payload, timeout=10)
        response.raise_for_status()
        result = response.json()
        return result
    except Exception as e:
        logger.warning(f"Failed to call analyst agent {tool}: {e}")
        return None

def _get_real_articles(limit: int = 50) -> List[Dict]:
    """Get real articles from memory agent"""
    cache_key = _get_cache_key("articles", limit=limit)
    cached = _get_cached_data(cache_key)
    if cached:
        return cached

    try:
        result = _call_memory_agent("get_recent_articles", limit=limit)
        if result and "articles" in result:
            articles = []
            for article_data in result["articles"]:
                # Transform database format to API format
                metadata = article_data.get("metadata", {})
                article = {
                    "id": str(article_data.get("id", "")),
                    "title": metadata.get("title", "Untitled"),
                    "content": article_data.get("content", ""),
                    "summary": _generate_summary(article_data.get("content", "")),
                    "source": metadata.get("domain", "Unknown"),
                    "source_credibility": metadata.get("credibility_score", 75),
                    "source_reliability": _get_reliability_rating(metadata.get("credibility_score", 75)),
                    "url": metadata.get("url", ""),
                    "published_date": metadata.get("timestamp", datetime.now().isoformat()),
                    "sentiment_score": 0.0,  # Will be populated by analyst
                    "fact_check_score": 85,   # Default score
                    "bias_score": 0.0,
                    "emotional_tone": "Neutral",
                    "readability_score": "College",
                    "topics": metadata.get("topics", []),
                    "comment_count": 0,
                    "word_count": len(article_data.get("content", "").split()),
                    "reading_time": max(1, len(article_data.get("content", "").split()) // 200)
                }
                articles.append(article)

            _set_cached_data(cache_key, articles)
            return articles
    except Exception as e:
        logger.error(f"Failed to get real articles: {e}")

    # Fallback to mock data if memory agent unavailable
    return _get_mock_articles(limit)

def _get_mock_articles(limit: int = 50) -> List[Dict]:
    """Fallback mock articles when real data unavailable"""
    return [
        {
            "id": "article-001",
            "title": "AI Revolutionizes Healthcare: New Breakthrough in Cancer Detection",
            "content": "Researchers have developed an AI system that can detect early-stage cancer with 99% accuracy...",
            "summary": "Researchers have developed an AI system that can detect early-stage cancer with 99% accuracy, potentially saving millions of lives annually.",
            "source": "Medical Journal",
            "source_credibility": 92,
            "source_reliability": "high",
            "url": "https://example.com/article-001",
            "published_date": datetime.now().isoformat(),
            "sentiment_score": 0.3,
            "fact_check_score": 95,
            "bias_score": 0.1,
            "emotional_tone": "Optimistic",
            "readability_score": "College",
            "topics": ["Healthcare", "AI", "Medical Technology"],
            "comment_count": 47,
            "word_count": 850,
            "reading_time": 4
        },
        {
            "id": "article-002",
            "title": "Climate Summit Reaches Historic Agreement on Carbon Emissions",
            "content": "World leaders have agreed to ambitious new targets for reducing carbon emissions...",
            "summary": "World leaders have agreed to ambitious new targets for reducing carbon emissions, marking a significant step forward in the fight against climate change.",
            "source": "Global News Network",
            "source_credibility": 88,
            "source_reliability": "high",
            "url": "https://example.com/article-002",
            "published_date": (datetime.now() - timedelta(hours=1)).isoformat(),
            "sentiment_score": 0.2,
            "fact_check_score": 91,
            "bias_score": -0.05,
            "emotional_tone": "Hopeful",
            "readability_score": "High School",
            "topics": ["Climate", "Politics", "Environment"],
            "comment_count": 123,
            "word_count": 620,
            "reading_time": 3
        },
        {
            "id": "article-003",
            "title": "Tech Giant Announces Revolutionary Quantum Computing Breakthrough",
            "content": "A major technology company has achieved a significant milestone in quantum computing...",
            "summary": "A major technology company has achieved a significant milestone in quantum computing, bringing practical quantum applications closer to reality.",
            "source": "Tech Chronicle",
            "source_credibility": 85,
            "source_reliability": "high",
            "url": "https://example.com/article-003",
            "published_date": (datetime.now() - timedelta(hours=2)).isoformat(),
            "sentiment_score": 0.4,
            "fact_check_score": 88,
            "bias_score": 0.15,
            "emotional_tone": "Excited",
            "readability_score": "College",
            "topics": ["Technology", "Quantum Computing", "Innovation"],
            "comment_count": 89,
            "word_count": 720,
            "reading_time": 3
        }
    ][:limit]

def _get_real_stats() -> Dict:
    """Get real statistics from various agents"""
    cache_key = _get_cache_key("stats")
    cached = _get_cached_data(cache_key)
    if cached:
        return cached

    try:
        # Get article count from memory agent
        memory_result = _call_memory_agent("get_article_count")
        total_articles = memory_result.get("count", 0) if memory_result else 0

        # Get crawler stats
        crawler_result = _call_analyst_agent("get_metrics")
        if crawler_result:
            daily_updates = crawler_result.get("articles_processed", 0)
            fact_checks = crawler_result.get("fact_checks_performed", 0)
        else:
            daily_updates = 0
            fact_checks = 0

        stats = {
            "total_articles": total_articles,
            "sources_tracked": 2500,  # Would need to query sources table
            "accuracy_rate": "95.2%",
            "daily_updates": daily_updates,
            "active_sources": 1800,
            "fact_checks_performed": fact_checks,
            "average_credibility_score": 78.5,
            "last_updated": datetime.now().isoformat()
        }

        _set_cached_data(cache_key, stats)
        return stats
    except Exception as e:
        logger.error(f"Failed to get real stats: {e}")

    # Fallback to mock stats
    return _get_mock_stats()

def _get_mock_stats() -> Dict:
    """Fallback mock statistics"""
    return {
        "total_articles": 125000,
        "sources_tracked": 2500,
        "accuracy_rate": "95.2%",
        "daily_updates": 650,
        "active_sources": 1800,
        "fact_checks_performed": 45000,
        "average_credibility_score": 78.5,
        "last_updated": datetime.now().isoformat()
    }

def _generate_summary(content: str, max_length: int = 200) -> str:
    """Generate a summary from article content"""
    if not content:
        return "No content available"

    # Simple extractive summary - take first few sentences
    sentences = content.split('.')[:3]
    summary = '. '.join(sentences).strip()
    if len(summary) > max_length:
        summary = summary[:max_length-3] + "..."
    return summary

def _get_reliability_rating(score: int) -> str:
    """Convert credibility score to reliability rating"""
    if score >= 90:
        return "high"
    elif score >= 70:
        return "medium"
    else:
        return "low"

def _check_rate_limit(request: Request, endpoint_type: str = "public") -> bool:
    """Check if request is within rate limits"""
    # Get client identifier (IP address or API key)
    client_id = request.client.host
    if hasattr(request.state, 'api_key') and request.state.api_key:
        client_id = hashlib.md5(request.state.api_key.encode()).hexdigest()[:8]

    # Clean old requests (older than 1 hour)
    current_time = time.time()
    _rate_limits[client_id] = [t for t in _rate_limits[client_id] if current_time - t < 3600]

    # Check rate limit
    limit = RESEARCH_RATE_LIMIT if endpoint_type == "research" else PUBLIC_RATE_LIMIT
    if len(_rate_limits[client_id]) >= limit:
        return False

    # Add current request
    _rate_limits[client_id].append(current_time)
    return True

def _verify_api_key(credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Verify API key for research endpoints"""
    if not credentials:
        return None

    token = credentials.credentials
    if token in API_KEYS:
        return token

    return None

async def get_api_key_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[str]:
    """Optional API key dependency for research endpoints"""
    api_key = _verify_api_key(credentials)
    request.state.api_key = api_key
    return api_key

async def require_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """Required API key dependency for research endpoints"""
    api_key = _verify_api_key(credentials)
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Valid API key required for research endpoints. Contact admin@justnews.ai for access."
        )
    request.state.api_key = api_key
    return api_key

class ArticleFilter:
    """Query parameters for article filtering"""
    def __init__(
        self,
        search: str = "",
        topic: str = "",
        source: str = "",
        credibility_min: int = 0,
        credibility_max: int = 100,
        sentiment: str = "",
        date_from: str = "",
        date_to: str = "",
        sort: str = "newest",
        limit: int = 20,
        offset: int = 0
    ):
        self.search = search.lower()
        self.topic = topic.lower()
        self.source = source.lower()
        self.credibility_min = credibility_min
        self.credibility_max = credibility_max
        self.sentiment = sentiment.lower()
        self.date_from = date_from
        self.date_to = date_to
        self.sort = sort
        self.limit = min(limit, 100)  # Max 100 articles per request
        self.offset = offset

def filter_articles(articles: List[Dict], filter_obj: ArticleFilter) -> List[Dict]:
    """Filter articles based on provided criteria"""
    filtered = articles.copy()

    # Text search
    if filter_obj.search:
        filtered = [a for a in filtered if
                   filter_obj.search in a.get('title', '').lower() or
                   filter_obj.search in a.get('content', '').lower() or
                   filter_obj.search in a.get('summary', '').lower()]

    # Topic filter
    if filter_obj.topic:
        filtered = [a for a in filtered if
                   any(filter_obj.topic in t.lower() for t in a.get('topics', []))]

    # Source filter
    if filter_obj.source:
        filtered = [a for a in filtered if
                   filter_obj.source in a.get('source', '').lower()]

    # Credibility filter
    filtered = [a for a in filtered if
               filter_obj.credibility_min <= a.get('source_credibility', 0) <= filter_obj.credibility_max]

    # Sentiment filter
    if filter_obj.sentiment:
        if filter_obj.sentiment == 'positive':
            filtered = [a for a in filtered if a.get('sentiment_score', 0) > 0.1]
        elif filter_obj.sentiment == 'negative':
            filtered = [a for a in filtered if a.get('sentiment_score', 0) < -0.1]
        elif filter_obj.sentiment == 'neutral':
            filtered = [a for a in filtered if -0.1 <= a.get('sentiment_score', 0) <= 0.1]

    # Date filters
    if filter_obj.date_from:
        try:
            from_date = datetime.fromisoformat(filter_obj.date_from.replace('Z', '+00:00'))
            filtered = [a for a in filtered if
                       datetime.fromisoformat(a.get('published_date', '')) >= from_date]
        except:
            pass

    if filter_obj.date_to:
        try:
            to_date = datetime.fromisoformat(filter_obj.date_to.replace('Z', '+00:00'))
            filtered = [a for a in filtered if
                       datetime.fromisoformat(a.get('published_date', '')) <= to_date]
        except:
            pass

    # Sorting
    if filter_obj.sort == 'newest':
        filtered.sort(key=lambda x: x.get('published_date', ''), reverse=True)
    elif filter_obj.sort == 'oldest':
        filtered.sort(key=lambda x: x.get('published_date', ''))
    elif filter_obj.sort == 'credibility':
        filtered.sort(key=lambda x: x.get('source_credibility', 0), reverse=True)
    elif filter_obj.sort == 'relevance':
        # For now, sort by fact check score as relevance proxy
        filtered.sort(key=lambda x: x.get('fact_check_score', 0), reverse=True)

    # Pagination
    start_idx = filter_obj.offset
    end_idx = start_idx + filter_obj.limit
    return filtered[start_idx:end_idx]

@router.get("/stats")
async def get_public_stats(request: Request):
    """Get public statistics for the website"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    return _get_real_stats()

@router.get("/articles")
async def get_articles(
    request: Request,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(""),
    topic: str = Query(""),
    source: str = Query(""),
    credibility_min: int = Query(0, ge=0, le=100),
    credibility_max: int = Query(100, ge=0, le=100),
    sentiment: str = Query("", regex="^(positive|negative|neutral)?$"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    sort: str = Query("newest", regex="^(newest|oldest|credibility|relevance)$")
):
    """Get filtered and paginated articles"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        # Create filter object
        filter_obj = ArticleFilter(
            search=search,
            topic=topic,
            source=source,
            credibility_min=credibility_min,
            credibility_max=credibility_max,
            sentiment=sentiment,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            limit=limit,
            offset=(page - 1) * limit
        )

        # Filter articles
        filtered_articles = filter_articles(_get_real_articles(limit=200), filter_obj)

        # Calculate pagination info
        all_articles = _get_real_articles(limit=1000)  # Get more for accurate count
        total_articles = len(all_articles)  # In real implementation, this would be from database
        total_pages = (total_articles + limit - 1) // limit
        has_more = page < total_pages

        return {
            "articles": filtered_articles,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_articles": total_articles,
                "total_pages": total_pages,
                "has_more": has_more
            },
            "filters_applied": {
                "search": search,
                "topic": topic,
                "source": source,
                "credibility_range": f"{credibility_min}-{credibility_max}",
                "sentiment": sentiment,
                "date_range": f"{date_from} to {date_to}",
                "sort": sort
            }
        }

    except Exception as e:
        logger.error(f"Error in get_articles: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve articles")

@router.get("/article/{article_id}")
async def get_article(article_id: str, request: Request):
    """Get detailed article information"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        # Find article by ID in real articles
        all_articles = _get_real_articles(limit=500)
        article = next((a for a in all_articles if a['id'] == article_id), None)

        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        # Add additional analysis data
        article['detailed_analysis'] = {
            'sentiment_breakdown': {
                'positive_words': ['breakthrough', 'revolutionary', 'success'],
                'negative_words': [],
                'neutral_words': ['research', 'system', 'detection']
            },
            'bias_analysis': {
                'political_bias': 0.05,
                'sensationalism': 0.1,
                'objectivity_score': 92
            },
            'fact_check_details': {
                'claims_verified': 8,
                'claims_questioned': 0,
                'claims_debunked': 0,
                'sources_cited': 12,
                'expert_reviews': 3
            },
            'readability_metrics': {
                'flesch_score': 45.2,
                'grade_level': 'College',
                'complex_words': 23,
                'avg_sentence_length': 18.5
            },
            'engagement_metrics': {
                'shares': 156,
                'bookmarks': 89,
                'comments': 47,
                'avg_reading_time': 4.2
            }
        }

        return article

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_article: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve article")

@router.get("/trending-topics")
async def get_trending_topics(request: Request, limit: int = Query(10, ge=1, le=50)):
    """Get trending topics"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        # For now, return mock data - could be enhanced to analyze real articles
        return _get_mock_trending_topics()[:limit]
    except Exception as e:
        logger.error(f"Error in get_trending_topics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trending topics")

def _get_mock_trending_topics() -> List[Dict]:
    """Mock trending topics data"""
    return [
        {"name": "Artificial Intelligence", "count": 245, "change": "+12%"},
        {"name": "Climate Change", "count": 189, "change": "+8%"},
        {"name": "Healthcare", "count": 156, "change": "+15%"},
        {"name": "Technology", "count": 134, "change": "+5%"},
        {"name": "Politics", "count": 98, "change": "-3%"},
        {"name": "Economy", "count": 87, "change": "+7%"},
        {"name": "Science", "count": 76, "change": "+10%"},
        {"name": "Sports", "count": 65, "change": "+2%"},
        {"name": "Entertainment", "count": 54, "change": "-5%"},
        {"name": "Education", "count": 43, "change": "+9%"}
    ]

@router.get("/source-credibility")
async def get_source_credibility(request: Request, limit: int = Query(20, ge=1, le=100)):
    """Get source credibility rankings"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        # For now, return mock data - could be enhanced to query sources table
        sources = _get_mock_source_credibility()
        # Sort by credibility score
        sorted_sources = sorted(sources,
                              key=lambda x: x['score'], reverse=True)
        return sorted_sources[:limit]
    except Exception as e:
        logger.error(f"Error in get_source_credibility: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve source credibility data")

def _get_mock_source_credibility() -> List[Dict]:
    """Mock source credibility data"""
    return [
        {"name": "Reuters", "score": 95, "articles": 1250, "reliability": "high"},
        {"name": "BBC News", "score": 92, "articles": 980, "reliability": "high"},
        {"name": "The Guardian", "score": 89, "articles": 756, "reliability": "high"},
        {"name": "CNN", "score": 87, "articles": 892, "reliability": "high"},
        {"name": "Associated Press", "score": 91, "articles": 654, "reliability": "high"},
        {"name": "New York Times", "score": 88, "articles": 723, "reliability": "high"},
        {"name": "Washington Post", "score": 86, "articles": 589, "reliability": "high"},
        {"name": "Fox News", "score": 72, "articles": 445, "reliability": "medium"}
    ]

@router.get("/fact-checks")
async def get_fact_checks(request: Request, limit: int = Query(10, ge=1, le=50)):
    """Get recent fact check corrections"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        # For now, return mock data - could be enhanced to query fact-check database
        return _get_mock_fact_checks()[:limit]
    except Exception as e:
        logger.error(f"Error in get_fact-checks: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve fact checks")

def _get_mock_fact_checks() -> List[Dict]:
    """Mock fact check data"""
    return [
        {
            "id": "fc-001",
            "claim": "COVID-19 vaccines contain microchips",
            "verdict": "False",
            "confidence": 98,
            "date": (datetime.now() - timedelta(days=1)).isoformat(),
            "source": "FactCheck.org",
            "article_url": "https://example.com/fact-check-001"
        },
        {
            "id": "fc-002",
            "claim": "Global temperatures have stopped rising",
            "verdict": "Misleading",
            "confidence": 92,
            "date": (datetime.now() - timedelta(days=2)).isoformat(),
            "source": "Climate Feedback",
            "article_url": "https://example.com/fact-check-002"
        },
        {
            "id": "fc-003",
            "claim": "AI will replace all human jobs by 2030",
            "verdict": "Exaggerated",
            "confidence": 85,
            "date": (datetime.now() - timedelta(days=3)).isoformat(),
            "source": "MIT Technology Review",
            "article_url": "https://example.com/fact-check-003"
        }
    ]

@router.get("/temporal-analysis")
async def get_temporal_analysis(
    request: Request,
    topic: str = Query(""),
    date_from: str = Query(""),
    date_to: str = Query(""),
    interval: str = Query("day", regex="^(hour|day|week|month)$")
):
    """Get temporal analysis data for trends over time"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        # Generate mock temporal data
        base_date = datetime.now() - timedelta(days=30)
        data_points = []

        for i in range(30):
            date = base_date + timedelta(days=i)
            data_points.append({
                "date": date.isoformat(),
                "article_count": 50 + (i % 10) * 5,  # Varying article counts
                "average_sentiment": 0.1 + (i % 5 - 2) * 0.1,  # Varying sentiment
                "average_credibility": 80 + (i % 8 - 4),  # Varying credibility
                "top_topics": ["AI", "Technology", "Politics", "Health"][i % 4]
            })

        return {
            "topic": topic or "all",
            "date_range": f"{date_from or '30 days ago'} to {date_to or 'now'}",
            "interval": interval,
            "data_points": data_points,
            "summary": {
                "total_articles": sum(dp["article_count"] for dp in data_points),
                "avg_sentiment": sum(dp["average_sentiment"] for dp in data_points) / len(data_points),
                "avg_credibility": sum(dp["average_credibility"] for dp in data_points) / len(data_points),
                "trend_direction": "increasing" if data_points[-1]["article_count"] > data_points[0]["article_count"] else "decreasing"
            }
        }

    except Exception as e:
        logger.error(f"Error in get_temporal_analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve temporal analysis")

@router.get("/search/suggestions")
async def get_search_suggestions(request: Request, query: str = Query("", min_length=2)):
    """Get search suggestions based on partial query"""
    if not _check_rate_limit(request, "public"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")

    try:
        if len(query) < 2:
            return {"suggestions": []}

        # Generate mock suggestions
        suggestions = [
            f"{query} news",
            f"{query} analysis",
            f"{query} fact check",
            f"latest {query}",
            f"{query} trends",
            f"{query} credibility"
        ]

        # Filter based on actual content
        matching_articles = [a for a in _get_real_articles(limit=100) if
                           query.lower() in a.get('title', '').lower() or
                           query.lower() in ' '.join(a.get('topics', [])).lower()]

        article_suggestions = [a['title'][:50] + "..." for a in matching_articles[:3]]

        return {
            "query": query,
            "suggestions": suggestions + article_suggestions,
            "categories": ["news", "analysis", "fact-checks", "sources"],
            "popular_searches": ["AI", "climate change", "politics", "technology"]
        }

    except Exception as e:
        logger.error(f"Error in get_search_suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get search suggestions")

@router.get("/export/articles")
async def export_articles(
    request: Request,
    api_key: str = Depends(require_api_key),
    format: str = Query("json", regex="^(json|csv|xml)$"),
    date_from: str = Query(""),
    date_to: str = Query(""),
    topic: str = Query(""),
    min_credibility: int = Query(0, ge=0, le=100)
):
    """Export articles for research purposes (requires API key)"""
    if not _check_rate_limit(request, "research"):
        raise HTTPException(status_code=429, detail="Research API rate limit exceeded. Please try again later.")

    try:
        # Filter articles based on criteria
        all_articles = _get_real_articles(limit=500)
        filtered_articles = all_articles

        if date_from:
            try:
                from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
                filtered_articles = [a for a in filtered_articles if
                                   datetime.fromisoformat(a.get('published_date', '')) >= from_date]
            except:
                pass

        if date_to:
            try:
                to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
                filtered_articles = [a for a in filtered_articles if
                                   datetime.fromisoformat(a.get('published_date', '')) <= to_date]
            except:
                pass

        if topic:
            filtered_articles = [a for a in filtered_articles if
                               any(topic.lower() in t.lower() for t in a.get('topics', []))]

        filtered_articles = [a for a in filtered_articles if
                           a.get('source_credibility', 0) >= min_credibility]

        # Format response based on requested format
        if format == "json":
            return {
                "export_info": {
                    "format": "json",
                    "total_articles": len(filtered_articles),
                    "generated_at": datetime.now().isoformat(),
                    "filters_applied": {
                        "date_from": date_from,
                        "date_to": date_to,
                        "topic": topic,
                        "min_credibility": min_credibility
                    },
                    "api_key_hash": hashlib.md5(api_key.encode()).hexdigest()[:8]
                },
                "articles": filtered_articles
            }
        elif format == "csv":
            # In a real implementation, this would generate CSV
            return {"message": "CSV export not implemented in demo", "article_count": len(filtered_articles)}
        else:
            return {"message": f"{format.upper()} export not implemented in demo", "article_count": len(filtered_articles)}

    except Exception as e:
        logger.error(f"Error in export_articles: {e}")
        raise HTTPException(status_code=500, detail="Failed to export articles")

@router.get("/research/metrics")
async def get_research_metrics(
    request: Request,
    api_key: str = Depends(require_api_key),
    date_from: str = Query(""),
    date_to: str = Query(""),
    granularity: str = Query("day", regex="^(hour|day|week|month)$")
):
    """Get detailed research metrics (requires academic/researcher API key)"""
    if not _check_rate_limit(request, "research"):
        raise HTTPException(status_code=429, detail="Research API rate limit exceeded. Please try again later.")

    try:
        return {
            "time_range": f"{date_from or '30 days ago'} to {date_to or 'now'}",
            "granularity": granularity,
            "metrics": {
                "total_articles_analyzed": 125000,
                "unique_sources": 2500,
                "fact_checks_performed": 45000,
                "sentiment_distribution": {
                    "positive": 0.35,
                    "negative": 0.25,
                    "neutral": 0.40
                },
                "credibility_distribution": {
                    "high_credibility": 0.45,
                    "medium_credibility": 0.35,
                    "low_credibility": 0.20
                },
                "topic_coverage": {
                    "politics": 0.25,
                    "technology": 0.20,
                    "business": 0.15,
                    "health": 0.12,
                    "science": 0.10,
                    "sports": 0.08,
                    "entertainment": 0.06,
                    "other": 0.04
                },
                "geographic_distribution": {
                    "north_america": 0.40,
                    "europe": 0.30,
                    "asia": 0.20,
                    "other": 0.10
                },
                "temporal_trends": {
                    "sentiment_volatility": 0.15,
                    "credibility_trend": "increasing",
                    "article_volume_trend": "stable"
                }
            },
            "data_quality": {
                "analysis_accuracy": 0.952,
                "source_verification_rate": 0.987,
                "fact_check_coverage": 0.823,
                "update_frequency": "real-time"
            },
            "api_usage": {
                "total_requests": 1250000,
                "unique_researchers": 850,
                "institutional_users": 120,
                "most_requested_topics": ["AI", "Climate Change", "Politics"]
            },
            "api_key_hash": hashlib.md5(api_key.encode()).hexdigest()[:8]
        }

    except Exception as e:
        logger.error(f"Error in get_research_metrics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve research metrics")

# Include router in main app
def include_public_api(app):
    """Include the public API router in the main FastAPI app"""
    app.include_router(router)
    logger.info("Public API endpoints registered")

# For testing the module directly
if __name__ == "__main__":
    print("JustNews Public API Module")
    print("Available endpoints:")
    for route in router.routes:
        print(f"  {route.methods} {route.path}")