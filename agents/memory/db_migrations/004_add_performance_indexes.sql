-- Vector search performance improvements
-- Add indexes and optimizations for better vector search performance

-- Create vector extension if not exists (for pgvector if available)
CREATE EXTENSION IF NOT EXISTS vector;

-- Add GIN index on metadata for faster JSON queries
CREATE INDEX IF NOT EXISTS idx_articles_metadata ON articles USING GIN (metadata);

-- Add index on embedding for faster vector operations
-- Note: For production, consider using pgvector extension with proper vector indexes
CREATE INDEX IF NOT EXISTS idx_articles_embedding ON articles USING GIN (embedding);

-- Add index on content for text search operations
CREATE INDEX IF NOT EXISTS idx_articles_content ON articles USING GIN (to_tsvector('english', content));

-- Add indexes for training_examples table
CREATE INDEX IF NOT EXISTS idx_training_examples_agent_task ON training_examples (agent_name, task_type);
CREATE INDEX IF NOT EXISTS idx_training_examples_timestamp ON training_examples (timestamp);
CREATE INDEX IF NOT EXISTS idx_training_examples_importance ON training_examples (importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_training_examples_priority ON training_examples (correction_priority DESC);

-- Add composite index for common query patterns
CREATE INDEX IF NOT EXISTS idx_articles_content_metadata ON articles (id, content, metadata);

-- Performance optimization: Add partial index for articles with embeddings
CREATE INDEX IF NOT EXISTS idx_articles_with_embedding ON articles (id, embedding) WHERE embedding IS NOT NULL;

-- Add index for crawled_urls table (if exists)
CREATE INDEX IF NOT EXISTS idx_crawled_urls_url ON crawled_urls (url);
CREATE INDEX IF NOT EXISTS idx_crawled_urls_timestamp ON crawled_urls (created_at);

-- Add indexes for sources and source_scores tables (if exist)
CREATE INDEX IF NOT EXISTS idx_sources_name ON sources (name);
CREATE INDEX IF NOT EXISTS idx_source_scores_source_id ON source_scores (source_id);
CREATE INDEX IF NOT EXISTS idx_source_scores_score ON source_scores (score DESC);