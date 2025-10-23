-- PL/pgSQL stored procedure to select canonical source for an article and update articles.source_id
-- Note: adjust schema/table names to match your DB. This is a starting point.

CREATE OR REPLACE FUNCTION canonical_select_and_update(p_article_id INTEGER)
RETURNS TABLE(chosen_source_id INTEGER) AS $$
DECLARE
    rec RECORD;
    best_source INTEGER := NULL;
BEGIN
    -- Select candidates from article_source_map
    FOR rec IN
        SELECT id, source_url_hash, confidence, created_at, (metadata->>'matched_by')::text AS matched_by
        FROM public.article_source_map
        WHERE article_id = p_article_id
        ORDER BY confidence DESC, created_at DESC
    LOOP
        IF best_source IS NULL THEN
            best_source := (SELECT s.id FROM public.sources s WHERE s.url_hash = rec.source_url_hash LIMIT 1);
        END IF;
        EXIT; -- first row is the best by our ordering
    END LOOP;

    IF best_source IS NOT NULL THEN
        UPDATE public.articles SET source_id = best_source WHERE id = p_article_id;
    END IF;

    RETURN QUERY SELECT best_source;
END;
$$ LANGUAGE plpgsql VOLATILE;
