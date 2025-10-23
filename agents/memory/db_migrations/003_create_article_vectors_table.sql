CREATE TABLE article_vectors (
    article_id INTEGER PRIMARY KEY REFERENCES articles(id),
    vector VECTOR(768) -- Adjust dimension as needed for your embedding model
);
