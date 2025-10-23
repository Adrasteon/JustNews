CREATE TABLE training_examples (
    id SERIAL PRIMARY KEY,
    task TEXT NOT NULL,
    input JSONB NOT NULL,
    output JSONB NOT NULL,
    critique TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
