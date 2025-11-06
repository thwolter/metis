SET search_path TO vectra, public;

UPDATE langchain_pg_embedding
SET cmetadata = COALESCE(cmetadata, '{}'::jsonb) || '{"document_type": "Annual Report"}'::jsonb
WHERE cmetadata ->> 'digest' = 'vI7EHYpQg6bnz2PsLviZVeneXbMs9iqDQyOgUjIhClc=';
