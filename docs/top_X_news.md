The primary goal of this system is to ingest the top X most relevant, current news articles globally, prioritizing international and then national coverage, while ensuring minimal data redundancy.

A. System Architecture

    Language & Frameworks: Python (for Scrapy, NLP/AI tools) and PostgreSQL (for data storage).

    Core Crawler: Scrapy for its robustness, extensibility, and asynchronous capability, or a custom wrapper around specialized tools like Trafilatura for high-accuracy text extraction.

    Database: MariaDB for structured metadata and ChromaDB for vector embeddings (replacing PostgreSQL/pg_vector).

B. Collection Logic and Process Flow

    Seed URL Management:

        Maintain a prioritized list of high-authority global news sources (e.g., Reuters, AP, BBC, Al Jazeera) and major national news outlets.

        Initial crawl targets focus on major sections: World/International News, then National News.

    The "Run" (Execution Cycle):

        The system executes on a predefined schedule (e.g., hourly).

        Goal: Find and process the top X most recent articles (e.g., X=500).

    Data Acquisition and Extraction:

        Crawling: Use crawl4ai to fetch and parse sitemaps and index pages from seed URLs.

        Article Extraction: Employ a high-precision extraction library (e.g., Trafilatura or newspaper4k) to isolate and clean the core article text, discarding boilerplate and advertisements.

        Metadata Extraction: Collect and normalize the following required fields:

            url (Primary Key, unique)

            title

            publication_date (ISO 8601 format)

            author(s)

            source_name (e.g., New York Times)

            language

            raw_html (optional, for forensics)

            collection_timestamp

    De-Duplication and Omission:

        Omission Check (Exact URL): Before processing, check the incoming article url against the database to omit exact duplicates.

        Semantic De-Duplication: After text extraction, generate a dense vector embedding for the article content (e.g., using Sentence-BERT). Compare this vector with existing vectors in the PostgreSQL vector store (pg_vector):

            If the cosine similarity with an existing article exceeds a threshold (e.g., 0.95), the article is considered a duplicate of a previously collected story and is omitted.

            This ensures that different URLs reporting the exact same wire story are only collected once.

    Data Storage:

        Store all unique articles and their metadata in the MariaDB relational tables.

        Store the article's vector embedding in the vector store (ChromaDB) for fast vector search and de-duplication.

Part 2: Fact-Checking and Grounded Truth Analysis

This part of the system focuses on using the collected articles to identify key facts and entities, then externally validating them to establish a Grounded Truth score.

C. Entity and Fact Extraction

    NLP Pipeline:

        Apply Named Entity Recognition (NER) to extract all People, Organizations, and Locations.

        Apply Relation Extraction (RE) to identify factual statements and claims (the 'facts' to be checked).

    Fact and Entity Table:

        Store extracted claims in a separate facts_to_check table with fields:

            fact_id (Primary Key)

            article_id (Foreign Key to original news article)

            fact_text (e.g., "The official was seen at the airport.")

            extracted_entity (e.g., "Official Name", "Location Name")

D. Corroborative Evidence Search

The system iterates through the facts_to_check table and initiates external web searches for validation.

    Text Search (Corroboration):

        Generate targeted queries from the fact_text (e.g., "Official Name" + "seen at airport" + "date").

        Perform a high-volume search using a web search API (or a custom search crawler).

        Validation: Process the top search snippets to count the number of high-authority sources (not including the original source) that confirm or deny the claim.

    Media Analysis (Evidence):

        Image/Video Search: If the fact references a visual element (e.g., "photo of the document," "video of the event"), use image-to-text tools or specific media search APIs to search for the corresponding media.

        Verification:

            Reverse Image Search to find the original publication date and context of the image/video to detect potential re-use or misleading framing.

            Deepfake/Manipulation Detection (using specialized open-source tools or APIs) to check for basic tampering of images/videos.

        Audio/Transcription: If audio/video is involved, use a transcription service to verify spoken words match the reported quotes.

E. Grounded Truth Value Calculation

    Scoring Model: A final scoring engine combines all corroborative evidence to assign a numerical Grounded Truth Value (GTV) between 0.0 (False) and 1.0 (True).

    GTV Calculation Factors (Weighted):

        Source Authority (Weight W1​): Score from high-authority sources (e.g., government, reputable think tanks, tier-1 news) confirming the claim.

        Conflicting Evidence (Weight W2​): Penalty for high-authority sources that contradict the claim.

        Media Integrity (Weight W3​): Score based on the outcome of image/video/audio checks (no manipulation found).

        Initial Trust (Weight W4​): A base score derived from the historical reputation/fact-check score of the original news source.

    Output: Store the final GTV alongside the fact in the facts_to_check table.

GTV=(W1​⋅Authority Score)−(W2​⋅Conflict Penalty)+(W3​⋅Media Score)+(W4​⋅Source Trust)

F. API and Analysis Output

    The final system provides an API layer where researchers and AI tools can query the database for:

        "Top X News Articles (Current Run)"

        "All Facts and Entities for Article ID"

        "Fact ID and its calculated Grounded Truth Value"
