"""
Worker Engine - Background Processing and Queue Management
========================================================

Responsibilities:
- Async queue management for article storage
- Background worker threads for processing
- Graceful shutdown and cleanup
- Performance monitoring and metrics

Architecture:
- Asyncio queue for task coordination
- ThreadPoolExecutor for CPU-bound operations
- Lifecycle management with proper cleanup
- Error handling and recovery
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from common.observability import get_logger

# Import tools
from agents.memory.tools import save_article

# Configure centralized logging
logger = get_logger(__name__)


class WorkerEngine:
    """Worker engine for background processing and queue management"""

    def __init__(self):
        self.storage_queue: Optional[asyncio.Queue] = None
        self.storage_executor: Optional[ThreadPoolExecutor] = None
        self.storage_consumer_task: Optional[asyncio.Task] = None
        self.memory_engine = None
        self.vector_engine = None
        self.running = False

    async def initialize(self, memory_engine, vector_engine):
        """Initialize the worker engine"""
        try:
            self.memory_engine = memory_engine
            self.vector_engine = vector_engine

            # Initialize async queue and background worker
            self.storage_queue = asyncio.Queue()
            self.storage_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory_worker")
            self.running = True

            # Start background consumer
            self.storage_consumer_task = asyncio.create_task(self._storage_consumer())
            logger.info("Worker engine initialized with background processing")

        except Exception as e:
            logger.error(f"Failed to initialize worker engine: {e}")
            raise

    async def shutdown(self):
        """Shutdown the worker engine"""
        try:
            self.running = False

            # Cancel consumer task
            if self.storage_consumer_task:
                self.storage_consumer_task.cancel()
                try:
                    await self.storage_consumer_task
                except asyncio.CancelledError:
                    pass

            # Drain remaining queue items with timeout
            if self.storage_queue:
                await self._drain_queue()

            # Shutdown thread pool
            if self.storage_executor:
                self.storage_executor.shutdown(wait=False)

            logger.info("Worker engine shutdown completed")

        except Exception as e:
            logger.error(f"Error during worker engine shutdown: {e}")

    async def _storage_consumer(self):
        """Background consumer to process storage tasks from the queue."""
        logger.info("Storage consumer started")

        while self.running:
            try:
                # Wait for task from queue
                task = await self.storage_queue.get()

                # Process the task in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    self.storage_executor,
                    lambda: self._process_storage_task(task)
                )

                # Mark task as done
                try:
                    self.storage_queue.task_done()
                except Exception:
                    pass

            except asyncio.CancelledError:
                logger.info("Storage consumer cancelled")
                break
            except Exception as e:
                logger.error(f"Error in storage consumer: {e}")
                # Continue processing other tasks
                try:
                    self.storage_queue.task_done()
                except Exception:
                    pass

        logger.info("Storage consumer stopped")

    def _process_storage_task(self, task: dict):
        """Process a single storage task"""
        try:
            # Extract task data
            content = task.get('content')
            metadata = task.get('metadata', {})

            if not content:
                logger.warning("Storage task missing content, skipping")
                return

            # Use embedding model from vector engine if available
            embedding_model = None
            if self.vector_engine and self.vector_engine.embedding_model:
                embedding_model = self.vector_engine.embedding_model

            # Save the article
            result = save_article(content, metadata, embedding_model=embedding_model)

            if result.get("status") == "success":
                logger.debug(f"Background storage completed for article ID: {result.get('article_id')}")
            else:
                logger.warning(f"Background storage failed: {result}")

        except Exception as e:
            logger.error(f"Error processing storage task: {e}")

    async def _drain_queue(self):
        """Drain remaining items from the storage queue"""
        try:
            timeout = 10.0  # seconds
            start_time = asyncio.get_event_loop().time()

            while not self.storage_queue.empty() and (asyncio.get_event_loop().time() - start_time) < timeout:
                logger.info(f"Draining storage queue; remaining={self.storage_queue.qsize()}")
                await asyncio.sleep(0.5)

            remaining = self.storage_queue.qsize()
            if remaining > 0:
                logger.warning(f"Queue drain timeout reached with {remaining} items remaining")

        except Exception as e:
            logger.error(f"Error draining queue: {e}")

    async def enqueue_storage_task(self, content: str, metadata: dict) -> bool:
        """Enqueue an article for background storage"""
        try:
            if not self.running or not self.storage_queue:
                logger.warning("Worker engine not running, cannot enqueue storage task")
                return False

            # Create task
            task = {
                'content': content,
                'metadata': metadata,
            }

            # Add to queue
            await self.storage_queue.put(task)
            logger.debug("Storage task enqueued for background processing")

            return True

        except Exception as e:
            logger.error(f"Error enqueueing storage task: {e}")
            return False

    def get_stats(self) -> dict:
        """Get worker engine statistics"""
        try:
            stats = {
                "engine": "worker",
                "running": self.running,
                "queue_size": self.storage_queue.qsize() if self.storage_queue else 0,
                "executor_active": self.storage_executor._threads if self.storage_executor else 0,
                "consumer_task_active": not self.storage_consumer_task.done() if self.storage_consumer_task else False,
            }

            return stats

        except Exception as e:
            logger.error(f"Error getting worker engine stats: {e}")
            return {"engine": "worker", "error": str(e)}