-- =====================================================================
--  Classification seed data
--  Schema: metadata
--  Purpose: populate base document classes and header weighting patterns
-- =====================================================================

SET search_path TO classification, public;

-- ---------------------------------------------------------------------
-- 1. Document Classes
-- ---------------------------------------------------------------------

INSERT INTO doc_classes ("class", enabled, created_at)
VALUES
    ('annual_report', TRUE, timezone('utc', now())),
    ('company_register', TRUE, timezone('utc', now())),
    ('prospectus', TRUE, timezone('utc', now()))
ON CONFLICT ("class") DO NOTHING;

-- ---------------------------------------------------------------------
-- 2. Header Weights
-- ---------------------------------------------------------------------

-- Annual Report
INSERT INTO header_weights ("class", pattern, is_regex, weight)
VALUES
    ('annual_report', 'management report', FALSE, 1.2),
    ('annual_report', 'consolidated financial statements', FALSE, 1.6),
    ('annual_report', 'auditor''s report', FALSE, 1.8),
    ('annual_report', 'notes to the financial statements', FALSE, 1.4)
ON CONFLICT ("class", pattern) DO NOTHING;

-- Company Register
INSERT INTO header_weights ("class", pattern, is_regex, weight)
VALUES
    ('company_register', 'handelsregister', FALSE, 2.0),
    ('company_register', 'registergericht', FALSE, 1.8),
    ('company_register', 'hrb', FALSE, 1.6),
    ('company_register', 'amtsgericht', FALSE, 1.5)
ON CONFLICT ("class", pattern) DO NOTHING;

-- Prospectus
INSERT INTO header_weights ("class", pattern, is_regex, weight)
VALUES
    ('prospectus', 'risk factors', FALSE, 2.0),
    ('prospectus', 'offering memorandum', FALSE, 1.9),
    ('prospectus', 'base prospectus', FALSE, 1.7),
    ('prospectus', 'terms and conditions', FALSE, 1.4)
ON CONFLICT ("class", pattern) DO NOTHING;

-- ---------------------------------------------------------------------
-- 3. Verification Queries (optional)
-- ---------------------------------------------------------------------
-- \echo 'Seeded document classes:'
-- SELECT * FROM doc_classes ORDER BY "class";
--
-- \echo 'Seeded header weights:'
-- SELECT * FROM header_weights ORDER BY "class", pattern;
