"""
Balancer Agent V1 - News Article Neutralization and Integration
=============================================================

Architecture: Uses JustNews production models for sentiment, bias, fact-checking, summarization, and semantic embeddings. Integrates a new quote extraction model. MCP bus compatible.

Models:
- Sentiment: RoBERTa (Analyst Agent)
- Bias: martin-ha/toxic-comment-model (Scout Agent)
- Fact Checking: DistilBERT, RoBERTa, BERT-large, SentenceTransformers, spaCy NER (Fact Checker Agent)
- Summarization/Neutralization: BART, T5 (Synthesizer Agent)
- Embeddings: SentenceTransformers (Synthesizer/Memory)
- Quote Extraction: Jean-Baptiste/roberta-large-ner-quotations (new)

Status: V1 Prototype - MCP bus ready
"""

try:
    import structlog  # type: ignore[import]
except Exception:
    structlog = None

import importlib
import os
import time
from pathlib import Path
from typing import Any

import psutil
import torch
from transformers import pipeline

from common.observability import get_logger

try:
    SentenceTransformer = None
except Exception:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        SentenceTransformer = None
try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None
try:
    import requests
    import requests as mcp_requests
except Exception:
    requests = None
    mcp_requests = None

MCP_BUS_URL = "http://localhost:8000"  # Update as needed

# Fallback logger when structlog not available
if structlog is not None:
    logger = structlog.get_logger("balancer_agent")
else:


    logger = get_logger(__name__)

def get_device() -> int:
    return 0 if torch.cuda.is_available() else -1

# Lazy pipeline getters to avoid heavy model loads during import/pytest collection
_sentiment_pipeline = None
_bias_pipeline = None
_summarization_pipeline = None
_neutralization_pipeline = None
_quote_extraction_pipeline = None

def get_sentiment_pipeline():
    global _sentiment_pipeline
    if _sentiment_pipeline is not None:
        return _sentiment_pipeline
    try:
        _sentiment_pipeline = pipeline("sentiment-analysis", model="cardiffnlp/twitter-roberta-base-sentiment-latest", device=get_device())
        return _sentiment_pipeline
    except Exception as e:
        logger.error("model_load_error", model="sentiment", error=str(e), status="error")
        raise RuntimeError(f"Failed to load sentiment model: {e}")

def get_bias_pipeline():
    global _bias_pipeline
    if _bias_pipeline is not None:
        return _bias_pipeline
    try:
        _bias_pipeline = pipeline("text-classification", model="martin-ha/toxic-comment-model", device=get_device())
        return _bias_pipeline
    except Exception as e:
        logger.error("model_load_error", model="bias", error=str(e), status="error")
        raise RuntimeError(f"Failed to load bias model: {e}")

def get_fact_checker_pipelines():
    try:
        # Build sentence_transformer separately so we can handle fallbacks cleanly
        agent_cache = os.environ.get('BALANCER_MODEL_CACHE') or str(Path('./agents/balancer/models').resolve())
        sentence_transformer = None
        # Prefer a top-level imported helper if it exists (avoids importing inside function)
        helper = globals().get('get_shared_embedding_model')
        if helper is not None:
            try:
                sentence_transformer = helper("all-MiniLM-L6-v2", cache_folder=agent_cache, device=get_device())
            except Exception:
                sentence_transformer = None

        if sentence_transformer is None:
            # Try importing the helper module dynamically to avoid creating a local name
            try:
                emb = importlib.import_module('agents.common.embedding')
                ensure_agent_model_exists = getattr(emb, 'ensure_agent_model_exists', None)
                helper2 = getattr(emb, 'get_shared_embedding_model', None)
                if ensure_agent_model_exists:
                    try:
                        ensure_agent_model_exists('all-MiniLM-L6-v2', agent_cache)
                    except Exception:
                        pass
                if helper2 is not None:
                    sentence_transformer = helper2('all-MiniLM-L6-v2', cache_folder=agent_cache, device=get_device())
            except Exception:
                sentence_transformer = None

        if sentence_transformer is None:
            # Last resort: use SentenceTransformer class if available
            try:
                from agents.common.embedding import ensure_agent_model_exists
                model_dir = ensure_agent_model_exists('all-MiniLM-L6-v2', agent_cache)
                if SentenceTransformer is not None:
                    sentence_transformer = SentenceTransformer(str(model_dir), device=get_device())
                else:
                    sentence_transformer = None
            except Exception:
                if SentenceTransformer is not None:
                    try:
                        sentence_transformer = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=agent_cache, device=get_device())
                    except Exception:
                        sentence_transformer = None
                else:
                    sentence_transformer = None

        return {
            "distilbert": lambda: pipeline("text-classification", model="distilbert-base-uncased", device=get_device()),
            "roberta": lambda: pipeline("text-classification", model="roberta-base", device=get_device()),
            "bert_large": lambda: pipeline("text-classification", model="bert-large-uncased", device=get_device()),
            "sentence_transformer": sentence_transformer,
            # spaCy NER would be loaded separately if needed
        }
    except Exception as e:
        logger.error("model_load_error", model="fact_checker", error=str(e), status="error")
        raise RuntimeError(f"Failed to load fact checker models: {e}")

def get_summarization_pipeline():
    global _summarization_pipeline
    if _summarization_pipeline is not None:
        return _summarization_pipeline
    try:
        _summarization_pipeline = pipeline("summarization", model="facebook/bart-large-cnn", device=get_device())
        return _summarization_pipeline
    except Exception as e:
        logger.error("model_load_error", model="summarization", error=str(e), status="error")
        raise RuntimeError(f"Failed to load summarization model: {e}")

def get_neutralization_pipeline():
    global _neutralization_pipeline
    if _neutralization_pipeline is not None:
        return _neutralization_pipeline
    try:
        _neutralization_pipeline = pipeline("text2text-generation", model="google/flan-t5-base", device=get_device())
        return _neutralization_pipeline
    except Exception as e:
        logger.error("model_load_error", model="neutralization", error=str(e), status="error")
        raise RuntimeError(f"Failed to load neutralization model: {e}")

def get_quote_extraction_pipeline():
    global _quote_extraction_pipeline
    if _quote_extraction_pipeline is not None:
        return _quote_extraction_pipeline
    try:
        _quote_extraction_pipeline = pipeline("token-classification", model="Jean-Baptiste/roberta-large-ner-quotations", device=get_device())
        return _quote_extraction_pipeline
    except Exception as e:
        logger.error("model_load_error", model="quote_extraction", error=str(e), status="error")
        raise RuntimeError(f"Failed to load quote extraction model: {e}")

def fetch_article(url: str) -> str:
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = [p.get_text() for p in soup.find_all('p')]
        article = ' '.join(paragraphs)
        logger.info("article_fetched", url=url, status="success")
        return article
    except Exception as e:
        logger.error("article_fetch_error", url=url, error=str(e), status="error")
        return ""

def call_agent_tool(agent: str, tool: str, *args, **kwargs) -> Any:
    payload = {
        "agent": agent,
        "tool": tool,
        "args": list(args),
        "kwargs": kwargs
    }
    response = mcp_requests.post(f"{MCP_BUS_URL}/call", json=payload)
    response.raise_for_status()
    return response.json()


# --- Multi-Agent Delegation ---
def analyze_article(text: str) -> dict[str, Any]:
    """Delegate analysis to Analyst, Fact Checker, and Synthesizer agents via MCP bus."""
    try:
        sentiment = call_agent_tool("analyst", "score_sentiment", text)
    except Exception as e:
        logger.error("analyst_sentiment_error", error=str(e), status="error")
        sentiment = get_sentiment_pipeline()(text)
    try:
        bias = call_agent_tool("analyst", "score_bias", text)
    except Exception as e:
        logger.error("analyst_bias_error", error=str(e), status="error")
        bias = get_bias_pipeline()(text)
    try:
        fact_result = call_agent_tool("fact_checker", "verify_claims", text)
    except Exception as e:
        logger.error("fact_checker_error", error=str(e), status="error")
        fact_result = {"error": str(e)}
    try:
        summary = call_agent_tool("synthesizer", "summarize_content_bart", text)
    except Exception as e:
        logger.error("synthesizer_error", error=str(e), status="error")
        summary = summarize_article(text)
    logger.info("multi_agent_analysis_completed", status="success")
    return {"sentiment": sentiment, "bias": bias, "fact": fact_result, "summary": summary}

def extract_quotes(text: str) -> list[str]:
    quote_pipe = get_quote_extraction_pipeline()
    results = quote_pipe(text)
    quotes = [r['word'] for r in results if r['entity_group'] == 'QUOTE']
    logger.info("quotes_extracted", num_quotes=len(quotes), status="success")
    return quotes

def summarize_article(text: str) -> str:
    summarizer = get_summarization_pipeline()
    summary = summarizer(text, max_length=150, min_length=40, do_sample=False)
    return summary[0]['summary_text']

def neutralize_text(text: str) -> str:
    neutralizer = get_neutralization_pipeline()
    result = neutralizer(text)
    return result[0]['generated_text']


def log_gpu_usage(operation: str):
    """Log current GPU memory usage for operation."""
    try:
        if torch.cuda.is_available():
            memory_used = torch.cuda.memory_allocated() / 1024**3  # GB
            logger.info(f"GPU memory usage for {operation}: {memory_used:.2f} GB")
    except Exception as e:
        logger.warning(f"GPU usage logging failed: {e}")

def batch_fetch_articles(urls: list[str], batch_size: int = 4) -> list[str]:
    """Batch fetch articles with configurable batch size and GPU logging."""
    articles = []
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i+batch_size]
        batch_articles = [fetch_article(url) for url in batch]
        articles.extend(batch_articles)
        log_gpu_usage(f"batch_fetch_articles batch {i//batch_size+1}")
    return articles


def log_training_example(task: str, input: dict, output: dict, critique: str = ""):
    """Log balancing actions and outcomes for continuous learning."""
    try:
        # Example: send to training system via MCP bus
        payload = {
            "task": task,
            "input": input,
            "output": output,
            "critique": critique
        }
        response = mcp_requests.post(f"{MCP_BUS_URL}/training/log_example", json=payload)
        response.raise_for_status()
        logger.info(f"Logged training example for task: {task}")
    except Exception as e:
        logger.warning(f"Training log failed: {e}")

def generate_balanced_article(main_article: str, quotes: list[str], alt_statements: list[str]) -> str:
    summary = summarize_article(main_article)
    neutral = neutralize_text(summary)
    article = neutral + "\n\nCounter-balancing statements:\n"
    for q in quotes:
        article += f"- {q}\n"
    for s in alt_statements:
        article += f"- {s}\n"
    logger.info("balanced_article_generated", num_quotes=len(quotes), num_alt_statements=len(alt_statements), status="success")
    # Log for continuous learning
    log_training_example(
        task="balance_article",
        input={"main_article": main_article, "quotes": quotes, "alt_statements": alt_statements},
        output={"balanced_article": article},
        critique=""
    )
    return article

def main():
    main_url = "https://www.bbc.co.uk/news/articles/c36jkydpxx6o"
    alt_urls = [
        "https://www.cambridge-news.co.uk/news/local-news/saved-bus-routes-see-no-32258242",
        "https://www.elystandard.co.uk/news/25387266.cambridgeshire-mayor-gets-funding-village-bus-routes/"
    ]
    main_article = fetch_article(main_url)
    _ = analyze_article(main_article)
    alt_articles = batch_fetch_articles(alt_urls)
    quotes = []
    for alt in alt_articles:
        quotes.extend(extract_quotes(alt))
    balanced_article = generate_balanced_article(main_article, quotes, alt_articles)
    print(balanced_article)


# MCP Bus Registration and Health Check (JustNews V4 pattern)
try:
    import uvicorn
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except Exception:
    # Provide minimal fallbacks when FastAPI stack isn't installed
    FastAPI = None
    HTTPException = Exception
    Request = object
    JSONResponse = dict
    RequestValidationError = Exception
    BaseModel = object
    uvicorn = None

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore[import]
    from slowapi.errors import RateLimitExceeded  # type: ignore[import]
    from slowapi.util import get_remote_address  # type: ignore[import]
except Exception:
    # No-op rate limiter fallbacks
    def _rate_limit_exceeded_handler(request, exc):
        return JSONResponse({"error": "rate_limited"})
    def get_remote_address(request=None):
        return "127.0.0.1"
    class Limiter:
        def __init__(self, key_func=None):
            pass
    class RateLimitExceeded(Exception):
        pass

# FastAPI app initialization (must be before handlers and endpoints)

# FastAPI app initialization with slowapi rate limiter
limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Custom error handler for request validation
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logger.error("request_validation_error", error=str(exc), status="error")
    return JSONResponse(
        status_code=422,
        content={
            "error_code": "VALIDATION_ERROR",
            "detail": exc.errors(),
            "body": exc.body,
        },
    )

# Register shutdown endpoint
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for balancer")

# Custom error handler for HTTPException
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error("http_exception", error=str(exc.detail), status="error", code=exc.status_code)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": "HTTP_ERROR",
            "detail": exc.detail,
        },
    )

class AgentRegistration(BaseModel):
    agent_name: str
    description: str
    version: str
    endpoints: dict[str, str]

@app.post("/register")
def register_agent(reg: AgentRegistration) -> dict[str, Any]:
    """Register balancer agent with MCP bus."""
    logger.info(f"Agent registered: {reg.agent_name} v{reg.version}")
    return {"status": "success", "agent": reg.agent_name}

@app.get("/health")
def health_check() -> dict[str, str]:
    """Health check endpoint for MCP bus compliance."""
    return {"status": "ok", "agent": "balancer"}


@app.get("/ready")
def ready_check() -> dict[str, Any]:
    """Readiness endpoint for balancer."""
    # Balancer doesn't have heavy model warmup in this trimmed setup; report ready=true
    return {"ready": True}

def check_mcp_bus_health() -> dict[str, Any]:
    """Check MCP bus health by querying /health endpoint."""
    try:
        start = time.time()
        response = mcp_requests.get(f"{MCP_BUS_URL}/health", timeout=2)
        response.raise_for_status()
        latency = time.time() - start
        return {"status": "ok", "latency_sec": round(latency, 3)}
    except Exception as e:
        logger.error("mcp_bus_health_error", error=str(e), status="error")
        return {"status": "error", "detail": str(e)}

def get_model_status() -> dict[str, Any]:
    """Check if all models are loaded and available."""
    status = {}
    for name, loader in {
        "sentiment": get_sentiment_pipeline,
        "bias": get_bias_pipeline,
        "fact_checker": get_fact_checker_pipelines,
        "summarization": get_summarization_pipeline,
        "neutralization": get_neutralization_pipeline,
        "quote_extraction": get_quote_extraction_pipeline
    }.items():
        try:
            loader()
            status[name] = "ok"
        except Exception as e:
            status[name] = f"error: {e}"
    return status

@app.get("/status")
def status_endpoint() -> dict[str, Any]:
    """Report agent health, MCP bus connectivity, and model status."""
    mcp_status = check_mcp_bus_health()
    model_status = get_model_status()
    return {
        "agent": "balancer",
        "mcp_bus": mcp_status,
        "models": model_status
    }

# --- Resource Monitoring Endpoint ---

@app.get("/resource_status")
def resource_status() -> dict[str, Any]:
    """Report current CPU, memory, and GPU usage."""
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    memory_gb = mem.used / 1024**3
    gpu_available = torch.cuda.is_available()
    gpu_memory_gb = torch.cuda.memory_allocated() / 1024**3 if gpu_available else 0.0
    return {
        "cpu_percent": cpu_percent,
        "memory_gb": round(memory_gb, 2),
        "gpu_available": gpu_available,
        "gpu_memory_gb": round(gpu_memory_gb, 2)
    }

if __name__ == "__main__":
    # Start FastAPI app for MCP bus integration
    uvicorn.run(app, host="0.0.0.0", port=8010)
