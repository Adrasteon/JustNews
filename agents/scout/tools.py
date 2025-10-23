# Model loading for Scout Agent (Llama-3-8B-Instruct)
import os
import re
import time
import traceback
from datetime import datetime, timezone

import requests

# Import security utilities
from agents.scout.security_utils import (
    log_security_event,
    rate_limit,
    sanitize_content,
    sanitize_filename,
    security_wrapper,
    validate_batch_urls,
    validate_content_size,
    validate_url,
)
from common.observability import get_logger

FEEDBACK_LOG = os.environ.get("SCOUT_FEEDBACK_LOG", "./feedback_scout.log")


logger = get_logger(__name__)

# Online Training Integration
try:
    from training_system import initialize_online_training
    ONLINE_TRAINING_AVAILABLE = True

    # Initialize online training for Scout with 40-example threshold
    initialize_online_training(update_threshold=40)  # Update after 40 examples for Scout
    logger.info("🎓 Online Training enabled for Scout V2")

except ImportError:
    ONLINE_TRAINING_AVAILABLE = False
    logger.warning("⚠️ Online Training not available for Scout V2")

# Import Crawl4AI components for advanced deep crawling
try:
    from crawl4ai import (  # noqa: F401
        AsyncWebCrawler,
        BestFirstCrawlingStrategy,
        CompositeScorer,
        ContentTypeFilter,
        DomainFilter,
        FilterChain,
        KeywordRelevanceScorer,
        PathDepthScorer,
    )
    from crawl4ai import LLMConfig  # type: ignore
    from crawl4ai.extraction_strategy import LLMExtractionStrategy  # type: ignore
    CRAWL4AI_NATIVE_AVAILABLE = True
    logger.info("✅ Native Crawl4AI components loaded for advanced deep crawling")
except ImportError as e:
    CRAWL4AI_NATIVE_AVAILABLE = False
    logger.warning(f"⚠️ Native Crawl4AI not available: {e}. Using Docker fallback.")

# Import for HTML text extraction

# Global Scout Intelligence Engine
scout_engine = None
intelligence_available = False

def initialize_scout_intelligence():
    """Initialize Next-Generation GPU-accelerated Scout intelligence engine with AI-first approach"""
    global scout_engine, intelligence_available
    
    if scout_engine is not None:
        return intelligence_available
    
    try:
        from agents.scout.gpu_scout_engine_v2 import NextGenGPUScoutEngine
        scout_engine = NextGenGPUScoutEngine(enable_training=True)
        intelligence_available = True

        model_info = scout_engine.get_model_info()
        logger.info("🚀 Next-Gen GPU Scout Intelligence Engine initialized")
        logger.info("📊 Model Status:")
        for task, info in model_info.items():
            status = "✅" if info["loaded"] else "❌"
            logger.info(f"   {status} {task}: {info['model_name']} ({'loaded' if info['loaded'] else 'failed'})")

        return True
    except Exception as e:
        logger.warning(f"⚠️ Next-Gen Scout Intelligence Engine initialization failed: {e}")
        logger.info("🔄 Running in web-crawling only mode")
        intelligence_available = False
        return False

# Initialize on module load - DISABLED to prevent startup hangs
# intelligence_available = initialize_scout_intelligence()

def get_scout_engine():
    """Get the Scout intelligence engine instance"""
    global scout_engine
    if scout_engine is None:
        initialize_scout_intelligence()
    return scout_engine

def extract_article_content(html_content: str) -> str:
    """
    Extract clean article content from Crawl4AI cleaned_html
    Based on analysis showing cleaned_html provides better article content than markdown
    """
    if not html_content:
        return ""

    # Security validation - validate content size
    if not validate_content_size(html_content):
        logger.warning("HTML content size validation failed in extract_article_content")
        log_security_event('content_size_exceeded', {'function': 'extract_article_content'})
        return ""

    # Sanitize HTML content before processing
    html_content = sanitize_content(html_content)

    # Remove HTML tags to get clean text
    clean_text = re.sub(r'<[^>]+>', ' ', html_content)

    # Clean up whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    # Split into sentences for better content filtering
    sentences = [s.strip() for s in clean_text.split('.') if len(s.strip()) > 20]

    # Filter out navigation/menu content from the beginning
    article_sentences = []
    content_started = False

    for sentence in sentences:
        sentence_lower = sentence.lower()

        # Skip common navigation elements
        if not content_started:
            skip_indicators = [
                'bbc homepage', 'skip to content', 'accessibility help',
                'your account', 'notifications', 'menu', 'search bbc',
                'cbbc', 'cbeebies', 'food', 'close menu', 'bbc news home',
                'home indepth', 'israel-gaza war', 'war in ukraine',
                'climate uk world business politics', 'newsbeat',
                'bbc verify', 'disability world africa', 'subscribe',
                'sign up', 'cookie', 'privacy policy', 'terms of use'
            ]

            if any(indicator in sentence_lower for indicator in skip_indicators):
                continue

            # Look for actual article content start
            article_indicators = [
                'employees', 'workers', 'commuters', 'people', 'residents',
                'officials', 'police', 'witnesses', 'sources', 'according to',
                'reported', 'announced', 'said', 'told'
            ]

            if any(indicator in sentence_lower for indicator in article_indicators) and len(sentence) > 50:
                content_started = True

        if content_started:
            article_sentences.append(sentence)

    # Join the filtered sentences back
    if article_sentences:
        clean_article = '. '.join(article_sentences)
        # Ensure it ends with proper punctuation
        if not clean_article.endswith('.'):
            clean_article += '.'
        return clean_article

    # Fallback: return cleaned text if no article pattern found
    return clean_text[:2000] if len(clean_text) > 2000 else clean_text

def log_feedback(event: str, details: dict):
    with open(FEEDBACK_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()}\t{event}\t{details}\n")

def intelligent_source_discovery(*args, **kwargs):
    """
    Enhanced source discovery with ML-based content pre-filtering.
    Combines web crawling with LLaMA-3-8B intelligence for quality assessment.
    """
    query = kwargs.get("query", args[0] if args else "")
    max_sources = kwargs.get("max_sources", 20)
    quality_threshold = kwargs.get("quality_threshold", 0.6)

    # Security validation
    if not query or not isinstance(query, str):
        logger.warning("Invalid query provided for source discovery")
        log_security_event('invalid_query', {'function': 'intelligent_source_discovery'})
        return []

    # Sanitize query
    query = sanitize_content(query)

    # Rate limiting
    if not rate_limit("intelligent_source_discovery"):
        log_security_event('rate_limit_exceeded', {'function': 'intelligent_source_discovery'})
        return []

    logger.info(f"[ScoutAgent] Intelligent source discovery for: '{query}'")

    try:
        # Step 1: Discover sources using web crawling
        crawl_response = requests.post(
            "http://localhost:32768/discover_sources",
            json={"args": [query], "kwargs": {"max_results": max_sources * 2}}
        )
        crawl_response.raise_for_status()
        raw_sources = crawl_response.json()

        logger.info(f"📡 Found {len(raw_sources)} raw sources")

        # Step 2: Apply ML intelligence if available
        if not intelligence_available:
            # Try to initialize intelligence engine
            initialize_scout_intelligence()
        
        if intelligence_available and scout_engine:
            filtered_sources = []

            for source in raw_sources[:max_sources * 2]:  # Process more than needed
                try:
                    # Get content preview for analysis
                    content_response = requests.post(
                        "http://localhost:32768/crawl_url",
                        json={"args": [source.get("url", "")], "kwargs": {"extract_text": True}}
                    )

                    if content_response.status_code == 200:
                        content_data = content_response.json()
                        content_text = content_data.get("content", "")[:2000]  # First 2K chars

                        # Analyze with Scout Intelligence
                        analysis = scout_engine.comprehensive_content_analysis(
                            content_text, source.get("url", "")
                        )

                        scout_score = analysis.get("scout_score", 0.0)

                        if scout_score >= quality_threshold:
                            source["scout_analysis"] = analysis
                            source["scout_score"] = scout_score
                            source["priority"] = "HIGH" if scout_score >= 0.8 else "MEDIUM"
                            filtered_sources.append(source)

                            if len(filtered_sources) >= max_sources:
                                break

                except Exception as e:
                    logger.warning(f"⚠️ Analysis failed for {source.get('url', 'unknown')}: {e}")
                    continue

            # Sort by Scout score (highest first)
            filtered_sources.sort(key=lambda x: x.get("scout_score", 0.0), reverse=True)

            log_feedback("intelligent_source_discovery", {
                "query": query,
                "raw_sources": len(raw_sources),
                "filtered_sources": len(filtered_sources),
                "avg_scout_score": sum(s.get("scout_score", 0.0) for s in filtered_sources) / len(filtered_sources) if filtered_sources else 0.0
            })

            logger.info(f"🧠 Intelligence filtering: {len(raw_sources)} → {len(filtered_sources)} sources")
            return filtered_sources

        else:
            # Fallback to basic web crawling
            logger.info("🔄 Using basic crawling (no intelligence available)")
            log_feedback("basic_source_discovery", {"query": query, "sources": len(raw_sources)})
            return raw_sources[:max_sources]

    except Exception as e:
        logger.error(f"❌ Intelligent source discovery failed: {e}")
        log_feedback("source_discovery_error", {"query": query, "error": str(e)})
        return []

def intelligent_content_crawl(*args, **kwargs):
    """
    Enhanced content crawling with ML-based quality assessment and classification.
    """
    # Debug input
    logger.debug(f"Args: {args}, Kwargs: {kwargs}")

    # Handle both URL-only and content data inputs
    if args and isinstance(args[0], dict):
        # Content data already provided
        content_item = args[0]
        url = content_item.get("url", "")
        content_text = content_item.get("content", "")
        query = content_item.get("query", "")
        logger.debug(f"Dict mode - URL: {url}, Content len: {len(content_text) if content_text else 0}")
    else:
        # URL-only mode
        url = kwargs.get("url", args[0] if args else "")
        content_text = ""
        query = kwargs.get("query", "")
        logger.debug(f"URL mode - URL: {url}")

    # Security validation
    if url and not validate_url(url):
        logger.warning(f"URL validation failed for content crawl: {url[:100]}")
        log_security_event('url_validation_failed', {'url': url[:100], 'function': 'intelligent_content_crawl'})
        return {"url": url[:100], "error": "Invalid or unsafe URL"}

    # Content size validation
    if content_text and not validate_content_size(content_text):
        logger.warning("Content size validation failed for intelligent content crawl")
        log_security_event('content_size_exceeded', {'function': 'intelligent_content_crawl'})
        return {"url": url[:100] if url else "", "error": "Content size exceeds maximum allowed limit"}

    # Rate limiting
    rate_limit_key = f"content_crawl_{hash(url or content_text[:100]) % 1000}"
    if not rate_limit(rate_limit_key):
        log_security_event('rate_limit_exceeded', {'function': 'intelligent_content_crawl'})
        return {"url": url[:100] if url else "", "error": "Rate limit exceeded"}

    analyze_content = kwargs.get("analyze_content", True)

    logger.info(f"[ScoutAgent] Intelligent content crawl for URL: {url}")
    logger.debug(f"Content provided: {bool(content_text)}, Content length: {len(content_text) if content_text else 0}")

    try:
        # If we don't have content, try to crawl it
        if not content_text and url:
            logger.info(f"🕷️ No content provided, attempting to crawl {url}")
            try:
                # Use native crawl_url function instead of external service
                content_data = crawl_url(url)
                if "error" in content_data:
                    logger.error(f"❌ Intelligent content crawl failed for {url}: {content_data['error']}")
                    return {"url": url, "error": f"Crawl failed: {content_data['error']}"}
                content_text = content_data.get("content", "")
            except Exception as crawl_error:
                logger.error(f"❌ Intelligent content crawl failed for {url}: {crawl_error}")
                return {"url": url, "error": f"Crawl failed: {str(crawl_error)}"}
        else:
            logger.info(f"✅ Content already provided, length: {len(content_text) if content_text else 0}")

        # Initialize result data
        content_data = {
            "url": url,
            "content": content_text,
            "query": query
        }

        # Apply ML intelligence if available
        if not intelligence_available:
            # Try to initialize intelligence engine
            initialize_scout_intelligence()
        
        if intelligence_available and scout_engine and analyze_content and content_text:
            # Comprehensive analysis
            analysis = scout_engine.comprehensive_content_analysis(content_text, url)

            # Enrich content data with Scout intelligence
            content_data["scout_analysis"] = analysis
            content_data["scout_score"] = analysis.get("scout_score", 0.0)
            content_data["recommendation"] = analysis.get("recommendation", "")
            content_data["is_news"] = analysis.get("news_classification", {}).get("is_news", False)
            content_data["quality_metrics"] = analysis.get("quality_assessment", {})
            content_data["bias_analysis"] = analysis.get("bias_analysis", {})

            logger.info(f"🧠 Content analysis complete. Scout Score: {analysis.get('scout_score', 0.0):.2f}")

            log_feedback("intelligent_content_crawl", {
                "url": url,
                "scout_score": analysis.get("scout_score", 0.0),
                "is_news": analysis.get("news_classification", {}).get("is_news", False),
                "content_length": len(content_text)
            })
        elif not content_text:
            logger.warning(f"⚠️ No content available for {url}")
        else:
            logger.info("🔄 Basic processing (no intelligence analysis)")
            log_feedback("basic_content_crawl", {"url": url})

        return content_data

    except Exception as e:
        logger.error(f"❌ Intelligent content crawl failed for {url}: {e}")
        log_feedback("content_crawl_error", {"url": url, "error": str(e)})
        return {"url": url, "error": str(e)}

def intelligent_batch_analysis(*args, **kwargs):
    """
    Batch process multiple URLs with Scout intelligence for maximum efficiency.
    """
    urls = kwargs.get("urls", args[0] if args else [])
    quality_threshold = kwargs.get("quality_threshold", 0.6)

    # Security validation
    if not urls or not isinstance(urls, list):
        logger.warning("Invalid URLs provided for batch analysis")
        log_security_event('invalid_batch_urls', {'function': 'intelligent_batch_analysis'})
        return {"error": "Invalid URLs provided"}

    # Validate and filter URLs
    valid_urls = validate_batch_urls(urls)
    if not valid_urls:
        logger.warning("No valid URLs provided for batch analysis")
        log_security_event('no_valid_urls', {'function': 'intelligent_batch_analysis', 'total_urls': len(urls)})
        return {"error": "No valid URLs provided"}

    # Rate limiting
    if not rate_limit("intelligent_batch_analysis"):
        log_security_event('rate_limit_exceeded', {'function': 'intelligent_batch_analysis'})
        return {"error": "Rate limit exceeded"}

    logger.info(f"[ScoutAgent] Intelligent batch analysis for {len(valid_urls)} URLs")

    if not intelligence_available or not scout_engine:
        logger.warning("⚠️ Intelligence engine not available for batch analysis")
        return {"error": "Intelligence engine not available"}

    try:
        # Step 1: Crawl all URLs
        content_items = []
        for url in urls:
            try:
                crawl_response = requests.post(
                    "http://localhost:32768/crawl_url",
                    json={"args": [url], "kwargs": {"extract_text": True}}
                )
                if crawl_response.status_code == 200:
                    content_data = crawl_response.json()
                    content_text = content_data.get("content", "")
                    if content_text:
                        content_items.append((content_text, url))
            except Exception as e:
                logger.warning(f"⚠️ Failed to crawl {url}: {e}")
                continue

        logger.info(f"📄 Successfully crawled {len(content_items)} out of {len(urls)} URLs")

        # Step 2: Batch analyze with Scout intelligence
        if content_items:
            batch_results = scout_engine.batch_analyze_content(content_items)

            # Filter by quality threshold
            high_quality_results = [
                result for result in batch_results
                if result.get("scout_score", 0.0) >= quality_threshold
            ]

            logger.info(f"🧠 Batch analysis complete: {len(content_items)} → {len(high_quality_results)} high-quality items")

            log_feedback("intelligent_batch_analysis", {
                "total_urls": len(urls),
                "crawled_successfully": len(content_items),
                "high_quality_results": len(high_quality_results),
                "avg_scout_score": sum(r.get("scout_score", 0.0) for r in batch_results) / len(batch_results) if batch_results else 0.0
            })

            return {
                "total_analyzed": len(batch_results),
                "high_quality_count": len(high_quality_results),
                "results": high_quality_results,
                "quality_threshold": quality_threshold
            }
        else:
            return {"error": "No content successfully crawled for analysis"}

    except Exception as e:
        logger.error(f"❌ Intelligent batch analysis failed: {e}")
        log_feedback("batch_analysis_error", {"urls_count": len(urls), "error": str(e)})
        return {"error": str(e)}

# Legacy wrappers removed; newer implementations exist earlier in this module.

async def enhanced_deep_crawl_site(*args, **kwargs):
    """
    Enhanced deep crawl using proven BestFirstCrawlingStrategy.
    Based on comprehensive testing that showed 13 pages + 542k chars for Hacker News.
    Integrates Scout intelligence for content quality assessment.
    
    Parameters:
    - url (str): Target website URL
    - max_depth (int): Maximum crawl depth (default: 4, user requested)
    - max_pages (int): Maximum pages to crawl (default: 100, user requested) 
    - word_count_threshold (int): Minimum words per page (default: 500, user requested)
    - quality_threshold (float): Scout intelligence quality threshold (default: 0.6)
    - analyze_content (bool): Apply Scout intelligence analysis (default: True)
    """

    # Extract parameters
    url = kwargs.get("url", args[0] if args else "")
    max_depth = kwargs.get("max_depth", 4)  # User requested depth
    max_pages = kwargs.get("max_pages", 100)  # User requested limit
    word_count_threshold = kwargs.get("word_count_threshold", 500)  # User requested threshold
    quality_threshold = kwargs.get("quality_threshold", 0.6)
    analyze_content = kwargs.get("analyze_content", True)

    # Security validation
    if not url:
        logger.error("No URL provided for deep crawl")
        log_security_event('missing_url', {'function': 'enhanced_deep_crawl_site'})
        return {"error": "No URL provided"}

    if not validate_url(url):
        logger.error(f"URL validation failed for deep crawl: {url[:100]}")
        log_security_event('url_validation_failed', {'url': url[:100], 'function': 'enhanced_deep_crawl_site'})
        return {"error": "Invalid or unsafe URL", "url": url[:100]}

    # Rate limiting
    if not rate_limit(f"deep_crawl_{hash(url) % 1000}"):
        log_security_event('rate_limit_exceeded', {'url': url[:100], 'function': 'enhanced_deep_crawl_site'})
        return {"error": "Rate limit exceeded", "url": url[:100]}

    logger.info(f"[ScoutAgent] Enhanced deep crawl for {url} (depth={max_depth}, pages={max_pages}, min_words={word_count_threshold})")

    if not CRAWL4AI_NATIVE_AVAILABLE:
        logger.warning("⚠️ Native Crawl4AI not available, falling back to Docker implementation")
        return deep_crawl_site(*args, **kwargs)

    start_time = time.time()
    crawl_results = []

    try:
        # Create optimized BestFirstCrawlingStrategy based on our successful tests
        deep_crawl_strategy = BestFirstCrawlingStrategy(
            max_depth=max_depth,
            max_pages=max_pages
        )

        logger.info(f"🧠 Using proven BestFirstCrawlingStrategy (max_depth={max_depth}, max_pages={max_pages})")

        async with AsyncWebCrawler(verbose=False) as crawler:
            # Execute optimized deep crawl
            result = await crawler.arun(
                url=url,
                deepcrawl=True,
                deepcrawl_strategy=deep_crawl_strategy,

                # Optimization parameters
                timeout=60,
                page_timeout=45,
                delay_between_requests=1.0,  # Be respectful

                # Content extraction optimization
                bypass_cache=True,
                remove_overlay_elements=True,
                simulate_user=True
            )

            duration = time.time() - start_time

            if result.success:
                total_content = 0

                # Process main page using cleaned_html with article extraction
                if result.cleaned_html:
                    clean_content = extract_article_content(result.cleaned_html)
                    word_count = len(clean_content.split())

                    if word_count >= word_count_threshold:
                        page_data = {
                            'url': url,
                            'title': result.metadata.get('title', 'Homepage'),
                            'content': clean_content,
                            'word_count': word_count,
                            'content_length': len(clean_content),
                            'depth': 0,
                            'source_method': 'enhanced_deepcrawl_main_cleaned_html',
                            'original_html_length': len(result.cleaned_html)
                        }
                        crawl_results.append(page_data)
                        total_content += len(clean_content)

                # Process additional crawled pages
                if hasattr(result, 'crawled_pages') and result.crawled_pages:
                    for i, page in enumerate(result.crawled_pages):
                        if hasattr(page, 'cleaned_html') and page.cleaned_html:
                            clean_content = extract_article_content(page.cleaned_html)
                            word_count = len(clean_content.split())
                            if word_count >= word_count_threshold:
                                page_data = {
                                    'url': page.url if hasattr(page, 'url') else f"page_{i}",
                                    'title': page.metadata.get('title', f'Page {i+1}') if hasattr(page, 'metadata') else f'Page {i+1}',
                                    'content': clean_content,
                                    'word_count': word_count,
                                    'content_length': len(clean_content),
                                    'depth': getattr(page, 'depth', i+1),
                                    'source_method': 'enhanced_deepcrawl_sub_cleaned_html',
                                    'original_html_length': len(page.cleaned_html)
                                }
                                crawl_results.append(page_data)
                                total_content += len(clean_content)
                                total_content += len(page.markdown)

                logger.info(f"✅ Enhanced deep crawl completed: {len(crawl_results)} pages, {total_content:,} chars in {duration:.2f}s")

                # Apply Scout intelligence analysis if available and requested
                if intelligence_available and scout_engine and analyze_content and crawl_results:
                    logger.info("🧠 Applying Scout intelligence analysis to crawled content...")

                    enhanced_results = []
                    analyzed_count = 0

                    for result in crawl_results:
                        try:
                            # Apply comprehensive Scout analysis
                            analysis = scout_engine.comprehensive_content_analysis(
                                result['content'], result['url']
                            )

                            scout_score = analysis.get("scout_score", 0.0)

                            # Only include high-quality content
                            if scout_score >= quality_threshold:
                                result["scout_analysis"] = analysis
                                result["scout_score"] = scout_score
                                result["recommendation"] = analysis.get("recommendation", "")
                                result["is_news"] = analysis.get("news_classification", {}).get("is_news", False)
                                result["quality_metrics"] = analysis.get("quality_assessment", {})
                                result["bias_analysis"] = analysis.get("bias_analysis", {})

                                enhanced_results.append(result)
                                analyzed_count += 1

                        except Exception as e:
                            logger.warning(f"⚠️ Scout analysis failed for {result.get('url', 'unknown')}: {e}")
                            # Keep original result without analysis
                            enhanced_results.append(result)

                    # Sort by Scout score (highest quality first)
                    enhanced_results.sort(key=lambda x: x.get("scout_score", 0.0), reverse=True)

                    logger.info(f"🧠 Scout intelligence applied: {analyzed_count}/{len(crawl_results)} pages analyzed")
                    logger.info(f"📊 Quality filtering: {len(crawl_results)} → {len(enhanced_results)} high-quality pages")

                    log_feedback("enhanced_deep_crawl_with_intelligence", {
                        "url": url,
                        "total_pages": len(crawl_results),
                        "high_quality_pages": len(enhanced_results),
                        "avg_scout_score": sum(r.get("scout_score", 0.0) for r in enhanced_results) / len(enhanced_results) if enhanced_results else 0.0,
                        "duration": duration
                    })

                    return enhanced_results
                else:
                    logger.info("🔄 Returning results without Scout intelligence analysis")
                    log_feedback("enhanced_deep_crawl_basic", {
                        "url": url,
                        "total_pages": len(crawl_results),
                        "duration": duration
                    })
                    return crawl_results

            else:
                logger.error(f"❌ Enhanced deep crawl failed: {result.error_message}")
                log_feedback("enhanced_deep_crawl_error", {
                    "url": url,
                    "error": result.error_message,
                    "duration": duration
                })

                # Fallback to Docker implementation
                logger.info("🔄 Falling back to Docker deep crawl implementation")
                return deep_crawl_site(*args, **kwargs)

    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"❌ Enhanced deep crawl exception for {url}: {e}")
        log_feedback("enhanced_deep_crawl_exception", {
            "url": url,
            "error": str(e),
            "duration": duration
        })

        # Fallback to Docker implementation
        logger.info("🔄 Falling back to Docker deep crawl implementation due to exception")
        return deep_crawl_site(*args, **kwargs)

def discover_sources(*args, **kwargs):
    """
    Discover sources for a given query using the crawl4ai Docker container.
    Includes security validation and rate limiting.
    """
    logger.info(f"[ScoutAgent] Discovering sources with args: {args}, kwargs: {kwargs}")

    # Rate limiting check
    if not rate_limit("discover_sources"):
        log_security_event('rate_limit_exceeded', {'function': 'discover_sources'})
        return {"error": "Rate limit exceeded", "sources": []}

    try:
        # Call the running crawl4ai container
        response = requests.post("http://localhost:32768/discover_sources", json={"args": args, "kwargs": kwargs})
        response.raise_for_status()
        links = response.json()
        log_feedback("discover_sources", {"args": args, "results": links})
        return links
    except Exception as e:
        logger.error(f"An error occurred during web search: {e}")
        log_feedback("discover_sources_error", {"args": args, "error": str(e)})
        return []

def crawl_url(*args, **kwargs):
    """
    Enhanced URL crawling with NewsReader screenshot and image interpretation.
    This combines Crawl4AI text extraction with LLaVA visual analysis for comprehensive content understanding.
    """
    logger.info(f"[ScoutAgent] Enhanced crawling URL with args: {args}, kwargs: {kwargs}")

    url = kwargs.get("url", args[0] if args else "")
    use_newsreader = kwargs.get("use_newsreader", True)  # Default to using NewsReader

    if not url:
        logger.error("No URL provided for crawling")
        return {"error": "No URL provided"}

    # Security validation
    if not validate_url(url):
        logger.error(f"URL validation failed for: {url[:100]}")
        log_security_event('url_validation_failed', {'url': url[:100], 'function': 'crawl_url'})
        return {"error": "Invalid or unsafe URL", "url": url[:100]}

    # Rate limiting
    if not rate_limit(f"crawl_url_{hash(url) % 1000}"):  # Simple hash-based identifier
        log_security_event('rate_limit_exceeded', {'url': url[:100], 'function': 'crawl_url'})
        return {"error": "Rate limit exceeded", "url": url[:100]}

    try:
        # Step 1: Get standard text content using native Crawl4AI
        text_content = None
        if CRAWL4AI_NATIVE_AVAILABLE:
            import asyncio

            async def native_crawl():
                # Configure for local Ollama LLM instead of cloud OpenAI
                llm_config = LLMConfig(
                    provider="ollama/llama2:7b",
                    base_url="http://localhost:11434"
                )
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(
                        url=url,
                        extraction_strategy=LLMExtractionStrategy(llm_config=llm_config),
                        css_selector="main, article, .content, .story-body, [role='main']",
                        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                    )

                    return {
                        "content": result.cleaned_html or result.markdown or result.extracted_content or "",
                        "extracted_content": result.extracted_content or "",
                        "markdown": result.markdown or "",
                        "title": getattr(result, 'title', ''),
                        "description": getattr(result, 'description', ''),
                        "method": "native_crawl4ai"
                    }

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            text_content = loop.run_until_complete(native_crawl())
            logger.info(f"✅ Text extraction successful for {url}")

        # Step 2: Enhanced analysis with NewsReader if enabled
        enhanced_analysis = None
        if use_newsreader and text_content:
            try:
                # Call NewsReader agent via MCP Bus for screenshot and visual analysis
                import requests

                newsreader_payload = {
                    "args": [url],
                    "kwargs": {"text_content": text_content.get("content", "")}
                }

                response = requests.post(
                    "http://localhost:8009/extract_news_from_url",
                    json=newsreader_payload,
                    timeout=30
                )

                if response.status_code == 200:
                    newsreader_result = response.json()
                    enhanced_analysis = newsreader_result
                    logger.info(f"✅ NewsReader visual analysis successful for {url}")
                else:
                    logger.warning(f"⚠️ NewsReader analysis failed with status {response.status_code}")

            except Exception as e:
                logger.warning(f"⚠️ NewsReader integration failed: {e}. Continuing with text-only analysis.")

        # Step 3: Combined result with both text and visual analysis
        combined_result = {
            "url": url,
            "content": text_content.get("content", "") if text_content else "",
            "extracted_content": text_content.get("extracted_content", "") if text_content else "",
            "markdown": text_content.get("markdown", "") if text_content else "",
            "metadata": {
                "title": text_content.get("title", "") if text_content else "",
                "description": text_content.get("description", "") if text_content else "",
                "status": "success",
                "method": "enhanced_crawl4ai_newsreader" if enhanced_analysis else text_content.get("method", "text_only")
            }
        }

        # Sanitize content before returning
        if combined_result["content"]:
            combined_result["content"] = sanitize_content(combined_result["content"])
        if combined_result["extracted_content"]:
            combined_result["extracted_content"] = sanitize_content(combined_result["extracted_content"])
        if combined_result["markdown"]:
            combined_result["markdown"] = sanitize_content(combined_result["markdown"])

        # Add NewsReader analysis if available
        if enhanced_analysis:
            combined_result["visual_analysis"] = enhanced_analysis
            combined_result["headline"] = enhanced_analysis.get("headline", "")
            combined_result["article"] = enhanced_analysis.get("article", "")
            combined_result["processing_method"] = enhanced_analysis.get("method", "unknown")

            # Enhance content with visual insights
            if enhanced_analysis.get("article") and len(enhanced_analysis["article"]) > len(combined_result["content"]):
                combined_result["content"] = enhanced_analysis["article"]
                combined_result["metadata"]["enhanced_by_vision"] = True

        return combined_result

    except Exception as e:
        logger.error(f"An error occurred during enhanced crawling: {e}")
        log_security_event('crawl_error', {'url': url[:100], 'error': str(e)})
        return {"url": url[:100], "error": str(e), "metadata": {"status": "error"}}

def enhanced_newsreader_crawl(*args, **kwargs):
    """
    Premium URL crawling with integrated NewsReader screenshot and LLaVA visual analysis.
    Combines Crawl4AI text extraction with visual interpretation for comprehensive content understanding.
    """
    logger.info(f"[ScoutAgent] Enhanced NewsReader crawling with args: {args}, kwargs: {kwargs}")

    url = kwargs.get("url", args[0] if args else "")
    # Force visual analysis parameter (reserved for future use)

    # Security validation
    if not url:
        logger.error("No URL provided for enhanced crawling")
        log_security_event('missing_url', {'function': 'enhanced_newsreader_crawl'})
        return {"error": "No URL provided"}

    if not validate_url(url):
        logger.error(f"URL validation failed for enhanced crawl: {url[:100]}")
        log_security_event('url_validation_failed', {'url': url[:100], 'function': 'enhanced_newsreader_crawl'})
        return {"error": "Invalid or unsafe URL", "url": url[:100]}

    # Rate limiting
    if not rate_limit(f"enhanced_crawl_{hash(url) % 1000}"):
        log_security_event('rate_limit_exceeded', {'url': url[:100], 'function': 'enhanced_newsreader_crawl'})
        return {"error": "Rate limit exceeded", "url": url[:100]}

    try:
        # Step 1: Standard text extraction using Crawl4AI
        logger.info(f"📝 Starting text extraction for {url}")
        text_result = {}

        if CRAWL4AI_NATIVE_AVAILABLE:
            import asyncio

            async def native_crawl():
                # Configure for local Ollama LLM instead of cloud OpenAI
                llm_config = LLMConfig(
                    provider="ollama/llama2:7b",
                    base_url="http://localhost:11434"
                )
                async with AsyncWebCrawler(verbose=False) as crawler:
                    result = await crawler.arun(
                        url=url,
                        extraction_strategy=LLMExtractionStrategy(llm_config=llm_config),
                        css_selector="main, article, .content, .story-body, [role='main']",
                        user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
                    )

                    return {
                        "content": result.cleaned_html or result.markdown or result.extracted_content or "",
                        "extracted_content": result.extracted_content or "",
                        "markdown": result.markdown or "",
                        "title": getattr(result, 'title', ''),
                        "description": getattr(result, 'description', ''),
                        "method": "native_crawl4ai"
                    }

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            text_result = loop.run_until_complete(native_crawl())
            logger.info(f"✅ Text extraction successful for {url}")

        # Step 2: NewsReader visual analysis via MCP Bus
        visual_analysis = None
        try:
            import requests

            newsreader_payload = {
                "args": [url],
                "kwargs": {
                    "text_fallback": text_result.get("content", ""),
                    "force_screenshot": True
                }
            }

            logger.info(f"🔍 Requesting NewsReader visual analysis for {url}")
            response = requests.post(
                "http://localhost:8009/extract_news_from_url",
                json=newsreader_payload,
                timeout=45  # Allow more time for screenshot + LLaVA analysis
            )

            if response.status_code == 200:
                visual_analysis = response.json()
                logger.info(f"✅ NewsReader visual analysis completed for {url}")
            else:
                logger.warning(f"⚠️ NewsReader returned status {response.status_code}")

        except Exception as e:
            logger.warning(f"⚠️ NewsReader visual analysis failed: {e}")

        # Step 3: Intelligent content fusion
        enhanced_result = {
            "url": url,
            "method": "enhanced_newsreader_crawl",
            "text_extraction": text_result,
            "visual_analysis": visual_analysis,
            "status": "success"
        }

        # Determine best content source
        text_content = text_result.get("content", "")
        visual_content = visual_analysis.get("article", "") if visual_analysis else ""
        visual_headline = visual_analysis.get("headline", "") if visual_analysis else ""

        # Use visual content if it's substantially better or if text failed
        if visual_content and (len(visual_content) > len(text_content) * 1.2 or len(text_content) < 100):
            enhanced_result["content"] = visual_content
            enhanced_result["primary_source"] = "visual_analysis"
            enhanced_result["headline"] = visual_headline
            logger.info(f"📸 Using visual analysis as primary content source for {url}")
        else:
            enhanced_result["content"] = text_content
            enhanced_result["primary_source"] = "text_extraction"
            enhanced_result["headline"] = text_result.get("title", "")
            logger.info(f"📝 Using text extraction as primary content source for {url}")

        # Add combined metadata
        enhanced_result["metadata"] = {
            "title": enhanced_result.get("headline", ""),
            "description": text_result.get("description", ""),
            "text_method": text_result.get("method", "unknown"),
            "visual_method": visual_analysis.get("method", "none") if visual_analysis else "none",
            "visual_success": visual_analysis.get("success", False) if visual_analysis else False,
            "processing_time": visual_analysis.get("processing_time", 0) if visual_analysis else 0,
            "content_source": enhanced_result.get("primary_source", "unknown")
        }

        return enhanced_result

    except Exception as e:
        logger.error(f"Enhanced NewsReader crawling failed: {e}")
        log_feedback("enhanced_newsreader_crawl_error", {"args": args, "error": str(e)})
        return {"url": url, "error": str(e), "metadata": {"status": "error"}}

def deep_crawl_site(*args, **kwargs):
    """
    Perform a deep crawl on a specific website for given keywords. Interacts with crawl4ai Docker container.
    """
    logger.info(f"[ScoutAgent] Deep crawling site with args: {args}, kwargs: {kwargs}")
    try:
        # Call the running crawl4ai container
        response = requests.post("http://localhost:32768/deep_crawl_site", json={"args": args, "kwargs": kwargs})
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"An error occurred during deep crawl: {e}")
        log_feedback("deep_crawl_site_error", {"args": args, "error": str(e)})
        return []

# =============================================================================
# PRODUCTION CRAWLERS - High-Speed News Gathering
# =============================================================================


# Initialize production crawlers with robust error handling - DISABLED for lazy loading
production_crawler = None
PRODUCTION_CRAWLERS_AVAILABLE = False

def initialize_production_crawlers():
    """Initialize production crawlers on demand"""
    global production_crawler, PRODUCTION_CRAWLERS_AVAILABLE
    
    if production_crawler is not None:
        return PRODUCTION_CRAWLERS_AVAILABLE
    
    try:
        from agents.scout.production_crawlers.orchestrator import ProductionCrawlerOrchestrator
        production_crawler = ProductionCrawlerOrchestrator()
        supported_sites = []
        try:
            # Use synchronous database call instead of async
            from agents.scout.production_crawlers.crawler_utils import get_active_sources
            sources = get_active_sources()
            supported_sites = [{
                'id': s['id'],
                'name': s['name'],
                'domain': s['domain'],
                'url': s['url'],
                'description': s['description'],
                'last_verified': s['last_verified'].isoformat() if s.get('last_verified') else None
            } for s in sources]
        except Exception as site_e:
            logger.error(f"❌ Exception calling get_active_sources: {site_e}")
            logger.error(traceback.format_exc())
            log_feedback("production_crawler_available_sites_error", {"error": str(site_e), "traceback": traceback.format_exc()})
        logger.info(f"[DIAG] ProductionCrawlerOrchestrator available_sites at startup: {len(supported_sites)} sources")
        log_feedback("production_crawler_available_sites", {"available_sites": len(supported_sites)})
        if production_crawler and supported_sites:
            PRODUCTION_CRAWLERS_AVAILABLE = True
            logger.info("✅ Production crawlers initialized successfully")
        else:
            logger.warning("⚠️ Production crawlers loaded but no supported sites detected.")
            PRODUCTION_CRAWLERS_AVAILABLE = False
    except ImportError as import_e:
        logger.error(f"❌ ImportError loading ProductionCrawlerOrchestrator: {import_e}")
        logger.error(traceback.format_exc())
        log_feedback("production_crawler_import_error", {"error": str(import_e), "traceback": traceback.format_exc()})
        production_crawler = None
        PRODUCTION_CRAWLERS_AVAILABLE = False
    except Exception as inst_e:
        logger.error(f"❌ Error initializing ProductionCrawlerOrchestrator: {inst_e}")
        logger.error(traceback.format_exc())
        log_feedback("production_crawler_init_error", {"error": str(inst_e), "traceback": traceback.format_exc()})
        production_crawler = None
        PRODUCTION_CRAWLERS_AVAILABLE = False
    
    return PRODUCTION_CRAWLERS_AVAILABLE

async def production_crawl_ultra_fast(site: str, target_articles: int = 100):
    """
    Ultra-fast production crawling for maximum throughput (8+ articles/second)
    Now calls the separate Crawler agent via MCP Bus.
    
    Args:
        site: News site identifier ('bbc', 'cnn', 'reuters', etc.)
        target_articles: Number of articles to crawl
        
    Returns:
        Dict with crawl results and performance metrics
    """
    logger.info(f"[ScoutAgent] Ultra-fast production crawl via Crawler agent: {site} ({target_articles} articles)")

    # Security validation
    if not site or not isinstance(site, str):
        logger.error("Invalid site identifier provided")
        log_security_event('invalid_site', {'function': 'production_crawl_ultra_fast'})
        return {"error": "Invalid site identifier", "articles": []}

    # Sanitize site identifier
    site = sanitize_filename(site)

    # Validate target_articles
    if not isinstance(target_articles, int) or target_articles < 1 or target_articles > 1000:
        logger.warning(f"Invalid target_articles: {target_articles}")
        log_security_event('invalid_target_articles', {'function': 'production_crawl_ultra_fast', 'target': target_articles})
        target_articles = min(max(target_articles, 1), 1000)  # Clamp to safe range

    # Rate limiting
    if not rate_limit("production_crawl_ultra_fast"):
        log_security_event('rate_limit_exceeded', {'function': 'production_crawl_ultra_fast'})
        return {"error": "Rate limit exceeded", "articles": []}

    try:
        # Call Crawler agent via MCP Bus
        import requests
        payload = {
            "args": [],
            "kwargs": {
                "domains": [site],
                "max_articles_per_site": target_articles,
                "concurrent_sites": 1,
                "max_total_articles": target_articles
            }
        }
        
        response = requests.post(
            "http://localhost:8015/unified_production_crawl",
            json=payload,
            timeout=300  # 5 minutes timeout for crawling
        )
        
        if response.status_code == 200:
            result = response.json()
            log_feedback("production_crawl_ultra_fast", {
                "site": site,
                "target": target_articles,
                "actual": result.get("total_articles", 0),
                "rate": result.get("articles_per_second", 0)
            })
            return result
        else:
            error_msg = f"Crawler agent returned status {response.status_code}: {response.text}"
            logger.error(f"Ultra-fast production crawl failed for {site}: {error_msg}")
            log_feedback("production_crawl_ultra_fast_error", {"site": site, "error": error_msg})
            return {"error": error_msg, "articles": []}
            
    except Exception as e:
        logger.error(f"Ultra-fast production crawl failed for {site}: {e}")
        log_feedback("production_crawl_ultra_fast_error", {"site": site, "error": str(e)})
        return {"error": str(e), "articles": []}

# === AI-ENHANCED PRODUCTION CRAWL ===
async def production_crawl_ai_enhanced(site: str, target_articles: int = 100):
    """
    AI-enhanced production crawling for full article extraction and NewsReader analysis.
    Now calls the separate Crawler agent via MCP Bus.
    
    Args:
        site: News site identifier (e.g., 'bbc')
        target_articles: Number of articles to crawl
    Returns:
        Dict with crawl results and performance metrics
    """
    logger.info(f"[ScoutAgent] AI-enhanced production crawl via Crawler agent: {site} ({target_articles} articles)")

    # Security validation
    if not site or not isinstance(site, str):
        logger.error("Invalid site identifier provided")
        log_security_event('invalid_site', {'function': 'production_crawl_ai_enhanced'})
        return {"error": "Invalid site identifier", "articles": []}

    # Sanitize site identifier
    site = sanitize_filename(site)

    # Validate target_articles
    if not isinstance(target_articles, int) or target_articles < 1 or target_articles > 1000:
        logger.warning(f"Invalid target_articles: {target_articles}")
        log_security_event('invalid_target_articles', {'function': 'production_crawl_ai_enhanced', 'target': target_articles})
        target_articles = min(max(target_articles, 1), 1000)  # Clamp to safe range

    # Rate limiting
    if not rate_limit("production_crawl_ai_enhanced"):
        log_security_event('rate_limit_exceeded', {'function': 'production_crawl_ai_enhanced'})
        return {"error": "Rate limit exceeded", "articles": []}

    try:
        # Call Crawler agent via MCP Bus
        import requests
        payload = {
            "args": [],
            "kwargs": {
                "domains": [site],
                "max_articles_per_site": target_articles,
                "concurrent_sites": 1,
                "max_total_articles": target_articles
            }
        }
        
        response = requests.post(
            "http://localhost:8015/unified_production_crawl",
            json=payload,
            timeout=600  # 10 minutes timeout for AI-enhanced crawling
        )
        
        if response.status_code == 200:
            result = response.json()
            log_feedback("production_crawl_ai_enhanced", {
                "site": site,
                "target": target_articles,
                "actual": result.get("total_articles", 0),
                "rate": result.get("articles_per_second", 0)
            })
            return result
        else:
            error_msg = f"Crawler agent returned status {response.status_code}: {response.text}"
            logger.error(f"AI-enhanced production crawl failed for {site}: {error_msg}")
            log_feedback("production_crawl_ai_enhanced_error", {"site": site, "error": error_msg})
            return {"error": error_msg, "articles": []}
            
    except Exception as e:
        logger.error(f"AI-enhanced production crawl failed for {site}: {e}")
        log_feedback("production_crawl_ai_enhanced_error", {"site": site, "error": str(e)})
        return {"error": str(e), "articles": []}

@security_wrapper
def get_production_crawler_info():
    """
    Get information about available production crawlers and supported sites
    Now calls the separate Crawler agent via MCP Bus.

    Returns:
        Dict with crawler capabilities and supported sites
    """
    logger.info("[ScoutAgent] Getting production crawler info via Crawler agent")

    # Rate limiting
    if not rate_limit("get_production_crawler_info"):
        log_security_event('rate_limit_exceeded', {'function': 'get_production_crawler_info'})
        return {
            "available": False,
            "error": "Rate limit exceeded",
            "supported_sites": []
        }

    try:
        # Call Crawler agent via MCP Bus
        import requests
        payload = {"args": [], "kwargs": {}}
        
        response = requests.post(
            "http://localhost:8015/get_crawler_info",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            # Add Scout agent context
            result["agent"] = "crawler"
            result["accessed_via"] = "scout_agent"
            log_feedback("get_production_crawler_info", {"sites_count": len(result.get("supported_sites", []))})
            return result
        else:
            error_msg = f"Crawler agent returned status {response.status_code}: {response.text}"
            logger.error(f"Failed to get production crawler info: {error_msg}")
            log_feedback("get_production_crawler_info_error", {"error": error_msg})
            return {"available": False, "error": error_msg, "supported_sites": []}
            
    except Exception as e:
        logger.error(f"Failed to get production crawler info: {e}")
        log_feedback("get_production_crawler_info_error", {"error": str(e)})
        return {"available": False, "error": str(e), "supported_sites": []}


# =============================================================================
# DYNAMIC MULTI-SITE PRODUCTION CRAWL (Generic domains via DB-driven config)
# =============================================================================
async def production_crawl_dynamic(domains: list[str] | None = None,
                                   articles_per_site: int = 25,
                                   concurrent_sites: int = 3,
                                   max_total_articles: int | None = None) -> dict:
    """Dynamic multi-site crawl using generic site crawler.
    Now calls the separate Crawler agent via MCP Bus.

    Args:
        domains: Optional explicit domain list. If None, all active sources.
        articles_per_site: Target articles per domain.
        concurrent_sites: Max concurrent domains processed.
        max_total_articles: Optional cap across all domains (defaults to len(domains)*articles_per_site)

    Returns:
        Dict with per-domain article lists and aggregated stats.
    """
    logger.info(f"[ScoutAgent] Dynamic multi-site crawl via Crawler agent: domains={domains} articles_per_site={articles_per_site} concurrent_sites={concurrent_sites}")

    # Rate limiting
    if not rate_limit("production_crawl_dynamic"):
        log_security_event('rate_limit_exceeded', {'function': 'production_crawl_dynamic'})
        return {"error": "Rate limit exceeded"}

    try:
        # Call Crawler agent via MCP Bus
        import requests
        payload = {
            "args": [],
            "kwargs": {
                "domains": domains,
                "max_articles_per_site": articles_per_site,
                "concurrent_sites": concurrent_sites,
                "max_total_articles": max_total_articles
            }
        }
        
        response = requests.post(
            "http://localhost:8015/unified_production_crawl",
            json=payload,
            timeout=900  # 15 minutes timeout for dynamic crawling
        )
        
        if response.status_code == 200:
            result = response.json()
            # Add Scout agent context
            result["accessed_via"] = "scout_agent"
            log_feedback("production_crawl_dynamic", {
                "domains": len(result.get("domain_breakdown", {})),
                "total_articles": result.get("total_articles", 0),
                "aps": result.get("articles_per_second", 0)
            })
            return result
        elif response.status_code == 202:
            # Async operation accepted
            result = response.json()
            result["accessed_via"] = "scout_agent"
            log_feedback("production_crawl_dynamic_async", {
                "job_id": result.get("job_id"),
                "status": "accepted"
            })
            return result
        else:
            error_msg = f"Crawler agent returned status {response.status_code}: {response.text}"
            logger.error(f"Dynamic multi-site crawl failed: {error_msg}")
            log_feedback("production_crawl_dynamic_error", {"error": error_msg})
            return {"error": error_msg}
            
    except Exception as e:
        logger.error(f"Dynamic multi-site crawl failed: {e}")
        log_feedback("production_crawl_dynamic_error", {"error": str(e)})
        return {"error": str(e)}

def _record_scout_performance(data: dict) -> None:
    """
    Stub for recording scout performance metrics.
    """
    # TODO: integrate with JustNewsMetrics
    pass
