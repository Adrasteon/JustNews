-- Fix PostgreSQL btree index row size limit issue
-- The idx_articles_content_metadata composite index exceeds 2704-byte limit due to large JSONB metadata

-- Drop the problematic composite index
DROP INDEX IF EXISTS idx_articles_content_metadata;

-- Create separate indexes that are more appropriate for the data types
-- Btree index for id and content (both small data types)
CREATE INDEX IF NOT EXISTS idx_articles_id_content ON articles (id, content);

-- GIN index for metadata JSONB queries (handles large JSON efficiently)
CREATE INDEX IF NOT EXISTS idx_articles_metadata_gin ON articles USING GIN (metadata);