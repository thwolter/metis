-- =====================================================================
--  Classification prototypes test data
--  Schema: classification
--  Purpose: seed enabled and disabled doc classes with prototypes
-- =====================================================================

SET search_path TO classification, public;

-- Document classes with mixed enabled flags
INSERT INTO doc_classes ("class", enabled, created_at)
VALUES
    ('integration_enabled_class', TRUE, timezone('utc', now())),
    ('integration_disabled_class', FALSE, timezone('utc', now()))
ON CONFLICT ("class") DO NOTHING;

-- Matching prototypes (only enabled class should be picked up)
INSERT INTO class_prototypes ("class", centroid, dispersion, n_docs, updated_at)
VALUES
    ('integration_enabled_class', '[3, 4]'::json, 0.1, 5, timezone('utc', now())),
    ('integration_disabled_class', '[5, 12]'::json, 0.3, 8, timezone('utc', now()))
ON CONFLICT ("class") DO NOTHING;
