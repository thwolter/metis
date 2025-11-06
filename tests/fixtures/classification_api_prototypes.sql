-- =====================================================================
--  Classification API test prototypes
--  Schema: classification
--  Purpose: seed lightweight unit vectors for API threshold scenarios
-- =====================================================================

SET search_path TO classification, public;

-- Ensure two enabled classes exist with deterministic centroids.
INSERT INTO doc_classes ("class", enabled, created_at)
VALUES
    ('alpha', TRUE, timezone('utc', now())),
    ('beta', TRUE, timezone('utc', now()))
ON CONFLICT ("class") DO UPDATE
SET enabled = EXCLUDED.enabled;

INSERT INTO class_prototypes ("class", centroid, dispersion, n_docs, updated_at)
VALUES
    ('alpha', '[1, 0, 0]'::json, 0.05, 5, timezone('utc', now())),
    ('beta', '[0, 1, 0]'::json, 0.05, 5, timezone('utc', now()))
ON CONFLICT ("class") DO UPDATE
SET
    centroid = EXCLUDED.centroid,
    dispersion = EXCLUDED.dispersion,
    n_docs = EXCLUDED.n_docs,
    updated_at = EXCLUDED.updated_at;
