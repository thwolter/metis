"""Seed DocClass & HeaderWeight for finance documents (idempotent)

Revision ID: 2c1f3e2c3f1a
Revises: 0004_classification_models
Create Date: 2025-11-06 10:12:00

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = '2c1f3e2c3f1a'
down_revision = '0004_classification_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
BEGIN;

-- Seed DocClass (idempotent)
INSERT INTO classification.doc_classes ("class", enabled, created_at) VALUES
    ('annual_report', TRUE, timezone('utc', now())),
    ('interim_report', TRUE, timezone('utc', now())),
    ('auditor_report', TRUE, timezone('utc', now())),
    ('financial_statements', TRUE, timezone('utc', now())),
    ('notes_financials', TRUE, timezone('utc', now())),
    ('management_report', TRUE, timezone('utc', now())),
    ('company_register_extract', TRUE, timezone('utc', now())),
    ('articles_of_association', TRUE, timezone('utc', now())),
    ('investor_presentation', TRUE, timezone('utc', now())),
    ('press_release_financial', TRUE, timezone('utc', now())),
    ('bond_prospectus', TRUE, timezone('utc', now())),
    ('equity_prospectus', TRUE, timezone('utc', now())),
    ('rating_report', TRUE, timezone('utc', now())),
    ('credit_agreement', TRUE, timezone('utc', now())),
    ('invoice', TRUE, timezone('utc', now())),
    ('bank_statement', TRUE, timezone('utc', now())),
    ('tax_assessment', TRUE, timezone('utc', now())),
    ('esg_report', TRUE, timezone('utc', now())),
    ('remuneration_report', TRUE, timezone('utc', now()))
ON CONFLICT ("class") DO UPDATE
SET enabled = EXCLUDED.enabled;

-- Seed HeaderWeight (idempotent ON CONFLICT upserts)

-- annual_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('annual_report', '^(Annual\\s+Report|Geschäftsbericht|Jahresbericht)\\b', TRUE, 0.75),
    ('annual_report', '^(Konzern)?(lage|Lage)bericht\\b', TRUE, 0.55),
    ('annual_report', '^(Management\\s+Report|Bericht\\s+des\\s+Geschäftsführung)\\b', TRUE, 0.40),
    ('annual_report', '^(Report\\s+of\\s+the\\s+Supervisory\\s+Board|Aufsichtsrat)\\b', TRUE, 0.30),
    ('annual_report', '^(Combined\\s+Management\\s+Report)\\b', TRUE, 0.45)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- interim_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('interim_report', '^(Interim|Half\\-Year|Halbjahres)\\s+(Report|Financial\\s+Report)\\b', TRUE, 0.70),
    ('interim_report', '^Q[1-4]\\s*20\\d{2}\\b', TRUE, 0.35),
    ('interim_report', '^(Quarterly\\s+(Statement|Report)|Quartalsmitteilung)\\b', TRUE, 0.60)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- auditor_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('auditor_report', '^(Independent\\s+Auditor(''s|’s)?\\s+Report)\\b', TRUE, 0.80),
    ('auditor_report', '^(Bestätigungsvermerk|Prüfungsurteil)\\b', TRUE, 0.75),
    ('auditor_report', 'Opinion\\b', FALSE, 0.30)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- financial_statements
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('financial_statements', '^(Consolidated\\s+Financial\\s+Statements|Konzernabschluss)\\b', TRUE, 0.70),
    ('financial_statements', '^(Statement\\s+of\\s+Financial\\s+Position|Bilanz)\\b', TRUE, 0.40),
    ('financial_statements', '^(Income\\s+Statement|Gewinn\\s+und\\s+Verlustrechnung)\\b', TRUE, 0.40),
    ('financial_statements', '^(Cash\\s+Flow\\s+Statement|Kapitalflussrechnung)\\b', TRUE, 0.45),
    ('financial_statements', '^(Statement\\s+of\\s+Changes\\s+in\\s+Equity|Eigenkapitalveränderungsrechnung)\\b', TRUE, 0.40)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- notes_financials
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('notes_financials', '^(Notes\\s+to\\s+the\\s+Consolidated?\\s+Financial\\s+Statements)\\b', TRUE, 0.75),
    ('notes_financials', '^(Anhang\\s+zum\\s+(Konzern)?abschluss)\\b', TRUE, 0.70),
    ('notes_financials', '^Accounting\\s+Policies\\b', TRUE, 0.35)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- management_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('management_report', '^(Management\\s+Discussion\\s+and\\s+Analysis|MD&A)\\b', TRUE, 0.70),
    ('management_report', '^(Lagebericht)\\b', TRUE, 0.70),
    ('management_report', 'Outlook\\b', FALSE, 0.25)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- company_register_extract
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('company_register_extract', '^(Handelsregister(auszug)?)\\b', TRUE, 0.80),
    ('company_register_extract', '^HRB\\s*\\d+\\b', TRUE, 0.55),
    ('company_register_extract', '^(Companies\\s+House|Unternehmensregister)\\b', TRUE, 0.50)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- articles_of_association
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('articles_of_association', '^(Articles\\s+of\\s+Association|Satzung|Gesellschaftsvertrag)\\b', TRUE, 0.80),
    ('articles_of_association', 'Share\\s+Capital\\b', FALSE, 0.30)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- investor_presentation
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('investor_presentation', '^(Investor\\s+Presentation|Earnings\\s+Presentation)\\b', TRUE, 0.65),
    ('investor_presentation', '^Safe\\s+Harbor\\b', TRUE, 0.40),
    ('investor_presentation', '^Appendix\\b', TRUE, 0.25)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- press_release_financial
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('press_release_financial', '^(Ad\\-hoc\\s+Mitteilung|Ad\\-hoc\\s+Disclosure)\\b', TRUE, 0.70),
    ('press_release_financial', '^(Press\\s+Release|Pressemitteilung)\\b', TRUE, 0.55),
    ('press_release_financial', '^(Preliminary\\s+Results|Vorläufige\\s+Zahlen)\\b', TRUE, 0.50)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- bond_prospectus
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('bond_prospectus', '^(Prospectus|Offering\\s+Memorandum)\\b', TRUE, 0.70),
    ('bond_prospectus', '^(Terms\\s+and\\s+Conditions\\s+of\\s+the\\s+Notes)\\b', TRUE, 0.80),
    ('bond_prospectus', '^(Risk\\s+Factors)\\b', TRUE, 0.45)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- equity_prospectus
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('equity_prospectus', '^(Prospectus)\\b', TRUE, 0.65),
    ('equity_prospectus', '^(Summary)\\b', TRUE, 0.25),
    ('equity_prospectus', '^(Use\\s+of\\s+Proceeds)\\b', TRUE, 0.40)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- rating_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('rating_report', '^(Rating\\s+Action)\\b', TRUE, 0.60),
    ('rating_report', '^(Issuer\\s+Profile|Credit\\s+Opinion)\\b', TRUE, 0.55),
    ('rating_report', '^(Moody’s|Moody''s|S&P|Fitch)\\b', TRUE, 0.35)
ON CONFLICT ("class", pattern)
DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- credit_agreement
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('credit_agreement', '^(Loan\\s+Agreement|Credit\\s+Agreement)\\b', TRUE, 0.75),
    ('credit_agreement', '^(Covenants|Events\\s+of\\s+Default)\\b', TRUE, 0.45),
    ('credit_agreement', '^(Definitions)\\b', TRUE, 0.25)
ON CONFLICT ("class", pattern)
DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- invoice
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('invoice', '^(Invoice|Rechnung)\\b', TRUE, 0.80),
    ('invoice', '^(Invoice\\s+No\\.|Rechnungsnr\\.|Rechnungsnummer)\\b', TRUE, 0.60),
    ('invoice', '^(VAT|USt\\.)\\b', TRUE, 0.40)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- bank_statement
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('bank_statement', '^(Bank\\s+Statement|Kontoauszug)\\b', TRUE, 0.80),
    ('bank_statement', '^(IBAN|BIC)\\b', TRUE, 0.40),
    ('bank_statement', '^(Opening\\s+Balance|Anfangssaldo)\\b', TRUE, 0.35)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- tax_assessment
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('tax_assessment', '^(Tax\\s+Assessment|Steuerbescheid)\\b', TRUE, 0.80),
    ('tax_assessment', '^(Einkommensteuer|Körperschaftsteuer|Umsatzsteuer)\\b', TRUE, 0.45)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- esg_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('esg_report', '^(Sustainability\\s+Report|ESG\\s+Report|Nachhaltigkeitsbericht)\\b', TRUE, 0.70),
    ('esg_report', '^(Non\\-Financial\\s+Statement|Nichtefinanzielle\\s+Erklärung)\\b', TRUE, 0.55),
    ('esg_report', '^(Scope\\s+(1|2|3))\\b', TRUE, 0.35)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

-- remuneration_report
INSERT INTO classification.header_weights ("class", pattern, is_regex, weight) VALUES
    ('remuneration_report', '^(Remuneration\\s+Report|Vergütungsbericht)\\b', TRUE, 0.75),
    ('remuneration_report', '^(Supervisory\\s+Board\\s+Compensation|Aufsichtsrat\\s+Vergütung)\\b', TRUE, 0.45)
ON CONFLICT ("class", pattern) DO UPDATE SET is_regex = EXCLUDED.is_regex, weight = EXCLUDED.weight;

COMMIT;
"""
    )


def downgrade() -> None:
    # delete seeded data by class keys (keeps migration reversible)
    op.execute(
        r"""
BEGIN;

DELETE FROM classification.header_weights
WHERE "class" IN (
    'annual_report','interim_report','auditor_report','financial_statements',
    'notes_financials','management_report','company_register_extract',
    'articles_of_association','investor_presentation','press_release_financial',
    'bond_prospectus','equity_prospectus','rating_report','credit_agreement',
    'invoice','bank_statement','tax_assessment','esg_report','remuneration_report'
);

DELETE FROM classification.doc_classes
WHERE "class" IN (
    'annual_report','interim_report','auditor_report','financial_statements',
    'notes_financials','management_report','company_register_extract',
    'articles_of_association','investor_presentation','press_release_financial',
    'bond_prospectus','equity_prospectus','rating_report','credit_agreement',
    'invoice','bank_statement','tax_assessment','esg_report','remuneration_report'
);

COMMIT;
"""
    )
