CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.documents (
  doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT,
  source_url TEXT,
  lang TEXT,
  title TEXT,
  version_tag TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- bge-m3 = 1024 dimension
CREATE TABLE IF NOT EXISTS rag.chunks (
  chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id   UUID REFERENCES rag.documents(doc_id) ON DELETE CASCADE,
  doc_type TEXT,
  drug_key TEXT,
  lang     TEXT,
  content  TEXT NOT NULL,
  tokens   INT,
  embedding vector(1024),
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_embed_hnsw
  ON rag.chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS chunks_content_trgm_idx
  ON rag.chunks USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS chunks_filter_idx
  ON rag.chunks (doc_type, lang, drug_key);
