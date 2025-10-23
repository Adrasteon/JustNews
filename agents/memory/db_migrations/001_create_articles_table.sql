-- Drop dependent objects and the articles table
DROP TABLE IF EXISTS article_vectors CASCADE;
DROP TABLE IF EXISTS articles CASCADE;

-- Recreate the articles table without SERIAL (no sequence dependency)
CREATE TABLE articles (
    id INTEGER PRIMARY KEY DEFAULT 1,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    embedding NUMERIC[]
);

-- Recreate the article_vectors table with a foreign key to articles
CREATE TABLE article_vectors (
    id SERIAL PRIMARY KEY,
    article_id INT REFERENCES articles(id) ON DELETE CASCADE,
    vector NUMERIC[] NOT NULL
);
