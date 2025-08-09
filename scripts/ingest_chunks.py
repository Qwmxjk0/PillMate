#!/usr/bin/env python3
import os, glob, uuid, requests, psycopg2
from psycopg2.extras import execute_values

DB_URL = os.getenv("DATABASE_URL", "postgresql://pillmate:pm_pass@localhost:5432/pillmate")
EMBED  = os.getenv("EMBED_ENDPOINT", "http://localhost:8081/embeddings")

def chunks_of(text, size=800, overlap=100):
    toks = text.split()
    step = max(1, size - overlap)
    out = []
    for i in range(0, len(toks), step):
        piece = " ".join(toks[i:i+size])
        if piece: out.append(piece)
        if i + size >= len(toks): break
    return out

def embed_batch(texts):
    r = requests.post(EMBED, json={"inputs": texts, "truncate": True}, timeout=120)
    r.raise_for_status()
    return [d["embedding"] for d in r.json()["data"]]

def main():
    conn = psycopg2.connect(DB_URL); conn.autocommit=False
    cur = conn.cursor()

    files = glob.glob("./data/*.txt") + glob.glob("./data/*.md")
    for path in files:
        title = os.path.basename(path)
        raw = open(path, "r", encoding="utf-8").read()

        cur.execute("""
            INSERT INTO rag.documents (doc_id, source, lang, title, version_tag)
            VALUES (%s,%s,%s,%s,%s) RETURNING doc_id
        """, (str(uuid.uuid4()), "local", "th", title, "v1"))
        doc_id = cur.fetchone()[0]

        cks = chunks_of(raw, 800, 100)
        rows = []
        for i in range(0, len(cks), 32):
            batch = cks[i:i+32]
            vecs = embed_batch(batch)
            for text, vec in zip(batch, vecs):
                rows.append((
                    str(uuid.uuid4()), doc_id, "general", None, "th", text, len(text.split()), vec
                ))

        execute_values(cur, """
            INSERT INTO rag.chunks
            (chunk_id, doc_id, doc_type, drug_key, lang, content, tokens, embedding)
            VALUES %s
        """, rows)
        conn.commit()
        print(f"ingested: {title} -> {len(rows)} chunks")

    cur.close(); conn.close()

if __name__ == "__main__":
    main()
