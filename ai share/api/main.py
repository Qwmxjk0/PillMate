#!/usr/bin/env python3
# main.py -- DrugBank LLM API (full)
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import pymysql
import openai
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import json
import re
from fastapi.responses import StreamingResponse

load_dotenv()

app = FastAPI(title="DrugBank-LLM API")

# --- Configuration (จาก .env หรือค่าเริ่มต้น) ---
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "DrugBank")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# --- Models ---
class QueryBody(BaseModel):
    user_id: Optional[str] = None
    drug_name: List[str]

class LLMResult(BaseModel):
    prompt: str
    llm_response: str

# --- DB helper ---
def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        local_infile=1,
    )

# --- LLM-based mapping: ไทย -> English generic names (one call) ---
def llm_map_drug_names(names: List[str]) -> List[str]:
    """
    เรียก LLM หนึ่งครั้งเพื่อแมปชื่อยา (ภาษาไทย/ยาการค้า/สะกดต่างๆ) -> ชื่อสามัญภาษาอังกฤษ (generic/INN).
    คืน list ความยาวเท่ากับ input; ถ้าแปลงไม่ได้ คืนชื่อเดิม
    """
    if not (LLM_PROVIDER == "openai" and OPENAI_API_KEY):
        return names

    instruction = (
        "You will receive a JSON array of drug names (which may be Thai names, brand names, or variant spellings).\n"
        "Return a JSON array of English generic names (INN) aligned with the input order.\n"
        "If you are not sure about an item, return the original item for that position.\n"
        "Respond with the JSON array only (no extra commentary).\n"
    )
    try:
        messages = [
            {"role": "system", "content": "You are a precise medical nomenclature normalizer."},
            {"role": "user", "content": instruction + "\nInput:\n" + json.dumps(names, ensure_ascii=False)}
        ]
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=200,
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        # extract JSON array substring (robust)
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end+1]
        mapped = json.loads(raw)
        if isinstance(mapped, list) and len(mapped) == len(names):
            return [ (str(x).strip() if x is not None else names[i]) for i,x in enumerate(mapped) ]
        return names
    except Exception:
        # on any error, fallback to original names
        return names

# --- Lookup drugs and interactions in DB ---
def lookup_drugs(drug_names: List[str]) -> Dict[str, Any]:
    """
    คืน dict: { matches: {query: {by_name: [...], by_synonym: [...] } }, interactions: [...] }
    interactions are pairs where both sides are in the found id set.
    """
    qnames = [dn.strip() for dn in drug_names if dn and dn.strip()]
    if not qnames:
        return {"matches": {}, "interactions": []}

    ids = set()
    matches = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # search by name
            for q in qnames:
                likeq = f"%{q}%"
                cur.execute(
                    "SELECT drugbank_id, name, description FROM drugs WHERE name LIKE %s LIMIT 20;",
                    (likeq,)
                )
                rows = cur.fetchall()
                matches[q] = {"by_name": rows, "by_synonym": []}
                for r in rows:
                    if r.get("drugbank_id"):
                        ids.add(r["drugbank_id"])

            # search synonyms
            for q in qnames:
                likeq = f"%{q}%"
                cur.execute(
                    "SELECT s.drugbank_id, s.synonym, d.name FROM synonyms s LEFT JOIN drugs d ON s.drugbank_id=d.drugbank_id WHERE s.synonym LIKE %s LIMIT 20;",
                    (likeq,)
                )
                rows = cur.fetchall()
                matches[q]["by_synonym"] = rows
                for r in rows:
                    if r.get("drugbank_id"):
                        ids.add(r["drugbank_id"])

            interactions = []
            if ids:
                id_list = list(ids)
                placeholders = ",".join(["%s"] * len(id_list))
                sql = f"""
                    SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                    FROM drug_interactions di
                    WHERE di.drugbank_id IN ({placeholders})
                      AND di.interacts_with_drugbank_id IN ({placeholders})
                    LIMIT 10000;
                """
                params = id_list + id_list
                cur.execute(sql, params)
                rows = cur.fetchall()
                # dedupe symmetric pairs
                seen = set()
                for r in rows:
                    a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                    if not a or not b:
                        continue
                    key = tuple(sorted([a, b]))
                    if key not in seen:
                        seen.add(key)
                        interactions.append(r)
            else:
                interactions = []
    finally:
        conn.close()

    return {"matches": matches, "interactions": interactions}

# --- Fetch information fields for given IDs ---
def fetch_info_for_ids(id_list: List[str]) -> Dict[str, Dict[str, Any]]:
    if not id_list:
        return {}
    placeholders = ",".join(["%s"] * len(id_list))
    sql = f"""
        SELECT drugbank_id, name, type, description, cas_number, unii, state
        FROM drugs
        WHERE drugbank_id IN ({placeholders});
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, id_list)
            rows = cur.fetchall()
    finally:
        conn.close()
    return { r["drugbank_id"]: r for r in rows }

# --- Build prompt: returns (system_message, user_message, interactions_count) ---
# --- Build prompt: returns (system_message, user_message, interactions_count) ---
def build_prompt(user_id: Optional[str], original_names: List[str], lookup_result: Dict[str, Any], info_by_id: Dict[str, Dict[str, Any]]):
    """
    คืนค่า: (system_message, user_message, interactions_count)
    - ข้อสำคัญ: ให้ LLM แสดง 'ข้อมูลยา (Information)' ก่อนเสมอ
    - หากไม่มี interaction ให้แสดงข้อความ 'ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล'
      ในส่วนปฏิกิริยาเท่านั้น (แต่ยังต้องแสดง Information)
    """
    # system message: role-level instruction (สั้นๆ แต่ชัดเจน)
    system_message = (
        "You are a strict factual summarizer. Use ONLY the records provided in the user message. "
        "Do not invent or add external information. Answer in Thai and format the answer as Markdown. "
        "Always start by listing the 'ข้อมูลยา (Information)' section, then the 'ปฏิกิริยา (Interactions)' section."
    )

    # Build user_message with explicit sections: original queries, Information, matched rows, interactions
    lines = []
    lines.append(f"User ID: {user_id or 'Guest'}")
    lines.append("")
    lines.append("Query drug names (original):")
    for q in original_names:
        lines.append(f"- {q}")
    lines.append("")

    # Information section (this must appear first in the content)
    lines.append("=== ข้อมูลยา (Information) ===")
    if info_by_id:
        for did, r in sorted(info_by_id.items(), key=lambda x: x[1].get("name") or x[0]):
            name = r.get("name") or did
            dtype = r.get("type") or ""
            cas = r.get("cas_number") or ""
            unii = r.get("unii") or ""
            state = r.get("state") or ""
            desc = (r.get("description") or "").replace("\n", " ")
            desc_short = desc[:400]
            lines.append(f"- **{name}** (ID: {did}) | ประเภท: {dtype} | CAS: {cas} | UNII: {unii} | สถานะ: {state}")
            if desc_short:
                lines.append(f"  - คำอธิบาย: {desc_short}")
    else:
        lines.append("- ไม่พบข้อมูลยาในฐานข้อมูลสำหรับรายการที่ระบุ")
    lines.append("")

    # Matched rows (transparency)
    lines.append("=== รายการที่แมช (Matched rows) ===")
    for q, info in lookup_result.get("matches", {}).items():
        lines.append(f"Query: {q}")
        if info.get("by_name"):
            for r in info["by_name"]:
                desc_raw = r.get("description") or ""
                desc_s = desc_raw.replace("\n", " ")[:200]
                lines.append(f"  - ID: {r.get('drugbank_id')} | Name: {r.get('name')} | Desc: {desc_s}")
        if info.get("by_synonym"):
            for r in info["by_synonym"]:
                syn = r.get("synonym") or ""
                can = r.get("name") or ""
                lines.append(f"  - Synonym match: ID: {r.get('drugbank_id')} | Synonym: {syn} | Canonical: {can}")
        lines.append("")

    # Interactions section (list raw rows here for LLM to use)
    interactions = lookup_result.get("interactions", [])
    lines.append(f"=== ปฏิกิริยา (Interactions) - raw records: {len(interactions)} ===")
    if interactions:
        for it in interactions[:200]:
            desc_raw = it.get("description") or ""
            desc_s = desc_raw.replace("\n", " ")[:400]
            lines.append(
                f"- {it.get('drugbank_id')}  <->  {it.get('interacts_with_drugbank_id')}  "
                f"| name: {it.get('interacts_with_name')}  | desc: {desc_s}"
            )
    else:
        # note: we still include this line in the user_message so LLM can follow instructions
        lines.append("- (no interaction records found)")

    lines.append("")
    # Clear instructions for LLM output
    lines.append("=== คำสั่งการสรุป (ให้ LLM ปฏิบัติตาม) ===")
    lines.append("1) ให้ตอบเป็น **ภาษาไทย** และใช้ **Markdown** เท่านั้น.")
    lines.append("2) เริ่มต้นด้วยหัวข้อ `ข้อมูลยา (Information)` — แสดงข้อมูลยา (ที่ปรากฎในส่วน Information ด้านบน) เป็นข้อย่อยสั้น ๆ.")
    lines.append("3) ตามด้วยหัวข้อ `สรุปปฏิกิริยา (Interactions)` —")
    lines.append("   - หากมีรายการปฏิกิริยา ให้สรุปเฉพาะปฏิกิริยาที่ปรากฎในส่วน `raw records` เท่านั้น (อย่าเติมหรือเดาข้อมูล).")
    lines.append("   - หากไม่มีรายการปฏิกิริยา ให้เขียนประโยคเดียวดังนี้ในหัวข้อนี้: `ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล`")
    lines.append("4) จำกัดความยาวรวม 2-4 ย่อหน้า สั้น กระชับ; เขียนให้ง่ายสำหรับคนทั่วไป.")
    lines.append("5) ห้ามอ้างอิงแหล่งภายนอกหรือเติมข้อมูลที่ไม่อยู่ในข้อความด้านบน.")
    lines.append("6) หากมีข้อสงสัย ให้เลือกแสดงคำว่า 'ไม่แน่ใจ' แทนการเดาข้อมูล (แต่พยายามอย่าแสดงถ้าไม่จำเป็น).")
    lines.append("")

    user_message = "\n".join(lines)
    return system_message, user_message, len(interactions)

# --- call LLM (sync) ---
def call_llm_openai(system_message: str, user_message: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured in environment.")
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=800,
            temperature=0,  # deterministic
        )
        if hasattr(resp.choices[0].message, 'content'):
            return resp.choices[0].message.content
        return str(resp)
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

# --- streaming LLM helper (yield SSE chunks) ---
def stream_llm_openai(system_message: str, user_message: str):
    if not OPENAI_API_KEY:
        yield f"data: {json.dumps({'error': 'OPENAI_API_KEY not configured'})}\n\n"
        return
    try:
        resp_iter = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message}
            ],
            max_tokens=800,
            temperature=0,
            stream=True
        )

        for chunk in resp_iter:
            try:
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                if "content" in delta:
                    text = delta["content"]
                    payload = {"delta": text}
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                # finish_reason handled implicitly (we send done after loop)
            except Exception:
                continue

        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

# --- Utility: build info_by_id fallback from matches if SQL returned empty ---
def build_info_fallback(info_by_id: Dict[str, Dict[str, Any]], lookup_matches: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    ถ้า info_by_id ว่าง ให้สร้างจาก matches (rows) เพื่อไม่ให้ section 'Information' หาย
    """
    if info_by_id:
        return info_by_id
    fallback = {}
    for q, v in lookup_matches.items():
        rows = (v.get("by_name") or []) + (v.get("by_synonym") or [])
        for row in rows:
            did = row.get("drugbank_id")
            if not did:
                continue
            if did not in fallback:
                fallback[did] = {
                    "name": row.get("name") or row.get("synonym") or did,
                    "type": row.get("type") or "",
                    "description": row.get("description") or "",
                    "cas_number": row.get("cas_number") or "",
                    "unii": row.get("unii") or "",
                    "state": row.get("state") or ""
                }
    return fallback

# --- API endpoints ---

@app.post("/analyze", response_model=LLMResult)
def analyze(body: QueryBody):
    # 1) mapping names via LLM (optional)
    mapped = llm_map_drug_names(body.drug_name)
    if DEBUG:
        print("DEBUG mapped:", mapped)

    # 2) lookup (try with mapped)
    try:
        lookup = lookup_drugs(mapped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB lookup error: {e}")

    # fallback: if mapped produced no matches at all, retry with original names
    any_matches = any((lookup.get("matches", {}) or {}).values())
    if DEBUG:
        print("DEBUG any_matches after mapped lookup:", any_matches)
    if not any_matches:
        # retry with original names
        retry_lookup = lookup_drugs(body.drug_name)
        if any((retry_lookup.get("matches", {}) or {}).values()):
            lookup = retry_lookup
            if DEBUG:
                print("DEBUG: fallback to original names for lookup")

    # 3) ids and fetch info
    ids = list({
        r["drugbank_id"]
        for v in lookup.get("matches", {}).values()
        for r in (v.get("by_name") or [])
    } | {
        r["drugbank_id"]
        for v in lookup.get("matches", {}).values()
        for r in (v.get("by_synonym") or [])
    })
    if DEBUG:
        print("DEBUG ids:", ids)

    info_by_id = fetch_info_for_ids(ids) if ids else {}
    if DEBUG:
        print("DEBUG info_by_id (from SQL):", list(info_by_id.keys()))

    # 3b) fallback from matched rows if SQL returned empty
    info_by_id = build_info_fallback(info_by_id, lookup.get("matches", {}))
    if DEBUG:
        print("DEBUG info_by_id (after fallback):", list(info_by_id.keys()))

    # 4) determine interactions according to guest/user rules
    is_user = bool(body.user_id)
    drug_count = len(ids)
    interactions = []

    try:
        if is_user:
            if drug_count <= 1:
                # find user's daily drugs (if table exists)
                try:
                    conn = get_db_connection()
                    user_daily = []
                    with conn.cursor() as cur:
                        cur.execute("SELECT drugbank_id FROM user_daily_drugs WHERE user_id = %s;", (str(body.user_id),))
                        rows = cur.fetchall()
                        user_daily = [r["drugbank_id"] for r in rows]
                    conn.close()
                except Exception:
                    user_daily = []
                if ids and user_daily:
                    conn = get_db_connection()
                    with conn.cursor() as cur:
                        one = ids
                        other = user_daily
                        ph1 = ",".join(["%s"]*len(one))
                        ph2 = ",".join(["%s"]*len(other))
                        sql = f"""
                            SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                            FROM drug_interactions di
                            WHERE (di.drugbank_id IN ({ph1}) AND di.interacts_with_drugbank_id IN ({ph2}))
                               OR (di.drugbank_id IN ({ph2}) AND di.interacts_with_drugbank_id IN ({ph1}))
                        """
                        params = one + other + other + one
                        cur.execute(sql, params)
                        rows = cur.fetchall()
                    seen = set()
                    for r in rows:
                        a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                        key = tuple(sorted([a, b]))
                        if key not in seen:
                            seen.add(key)
                            interactions.append(r)
            else:
                if ids:
                    conn = get_db_connection()
                    ph = ",".join(["%s"]*len(ids))
                    sql = f"""
                        SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                        FROM drug_interactions di
                        WHERE di.drugbank_id IN ({ph}) AND di.interacts_with_drugbank_id IN ({ph})
                    """
                    cur = conn.cursor()
                    cur.execute(sql, ids + ids)
                    rows = cur.fetchall()
                    conn.close()
                    seen = set()
                    for r in rows:
                        a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                        key = tuple(sorted([a, b]))
                        if key not in seen:
                            seen.add(key)
                            interactions.append(r)
        else:
            # guest
            if drug_count <= 1:
                interactions = []
            else:
                if ids:
                    conn = get_db_connection()
                    ph = ",".join(["%s"]*len(ids))
                    sql = f"""
                        SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                        FROM drug_interactions di
                        WHERE di.drugbank_id IN ({ph}) AND di.interacts_with_drugbank_id IN ({ph})
                    """
                    cur = conn.cursor()
                    cur.execute(sql, ids + ids)
                    rows = cur.fetchall()
                    conn.close()
                    seen = set()
                    for r in rows:
                        a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                        key = tuple(sorted([a, b]))
                        if key not in seen:
                            seen.add(key)
                            interactions.append(r)
    except Exception as e:
        # DB error while fetching interactions
        raise HTTPException(status_code=500, detail=f"DB interactions error: {e}")

    # 5) build prompt (system + user messages)
    system_message, user_message, interactions_count = build_prompt(body.user_id, body.drug_name, {"matches": lookup.get("matches", {}), "interactions": interactions}, info_by_id)

    if DEBUG:
        print("DEBUG system_message:", system_message)
        # don't print full user_message when large
        print("DEBUG user_message preview:", user_message[:2000])

    # 6) call LLM (sync)
    if LLM_PROVIDER == "openai":
        try:
            llm_text = call_llm_openai(system_message, user_message)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM error: {e}")
    else:
        raise HTTPException(status_code=501, detail="Only openai LLM_PROVIDER implemented")

    # 7) SANITY CHECK: ถ้ามี interactions แต่ LLM บอก "ไม่พบข้อมูล..." ให้ตัดประโยคนั้นทิ้ง
    if interactions_count > 0 and "ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล" in llm_text:
        llm_text = re.sub(r"(?i)ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล[^\n]*", "", llm_text).strip()
        if not llm_text:
            llm_text = "มีข้อมูลการโต้ตอบระหว่างยา (รายละเอียดถูกลบโดยระบบตรวจสอบความสอดคล้อง)"

    return {"prompt": user_message, "llm_response": llm_text}

@app.post("/analyze_stream")
def analyze_stream(body: QueryBody):
    # same flow as /analyze but stream LLM output (SSE)
    mapped = llm_map_drug_names(body.drug_name)
    if DEBUG:
        print("DEBUG mapped (stream):", mapped)

    try:
        lookup = lookup_drugs(mapped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB lookup error: {e}")

    any_matches = any((lookup.get("matches", {}) or {}).values())
    if not any_matches:
        retry_lookup = lookup_drugs(body.drug_name)
        if any((retry_lookup.get("matches", {}) or {}).values()):
            lookup = retry_lookup
            if DEBUG:
                print("DEBUG: fallback to original names for lookup (stream)")

    ids = list({
        r["drugbank_id"]
        for v in lookup.get("matches", {}).values()
        for r in (v.get("by_name") or [])
    } | {
        r["drugbank_id"]
        for v in lookup.get("matches", {}).values()
        for r in (v.get("by_synonym") or [])
    })
    info_by_id = fetch_info_for_ids(ids) if ids else {}
    info_by_id = build_info_fallback(info_by_id, lookup.get("matches", {}))

    # interactions (user/guest logic) - same as above (kept concise)
    is_user = bool(body.user_id)
    drug_count = len(ids)
    interactions = []
    try:
        if is_user:
            if drug_count <= 1:
                try:
                    conn = get_db_connection()
                    user_daily = []
                    with conn.cursor() as cur:
                        cur.execute("SELECT drugbank_id FROM user_daily_drugs WHERE user_id = %s;", (str(body.user_id),))
                        rows = cur.fetchall()
                        user_daily = [r["drugbank_id"] for r in rows]
                    conn.close()
                except Exception:
                    user_daily = []
                if ids and user_daily:
                    conn = get_db_connection()
                    with conn.cursor() as cur:
                        one = ids
                        other = user_daily
                        ph1 = ",".join(["%s"]*len(one))
                        ph2 = ",".join(["%s"]*len(other))
                        sql = f"""
                            SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                            FROM drug_interactions di
                            WHERE (di.drugbank_id IN ({ph1}) AND di.interacts_with_drugbank_id IN ({ph2}))
                               OR (di.drugbank_id IN ({ph2}) AND di.interacts_with_drugbank_id IN ({ph1}))
                        """
                        params = one + other + other + one
                        cur.execute(sql, params)
                        rows = cur.fetchall()
                    seen = set()
                    for r in rows:
                        a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                        key = tuple(sorted([a, b]))
                        if key not in seen:
                            seen.add(key)
                            interactions.append(r)
            else:
                if ids:
                    conn = get_db_connection()
                    ph = ",".join(["%s"]*len(ids))
                    sql = f"""
                        SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                        FROM drug_interactions di
                        WHERE di.drugbank_id IN ({ph}) AND di.interacts_with_drugbank_id IN ({ph})
                    """
                    cur = conn.cursor()
                    cur.execute(sql, ids + ids)
                    rows = cur.fetchall()
                    conn.close()
                    seen = set()
                    for r in rows:
                        a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                        key = tuple(sorted([a, b]))
                        if key not in seen:
                            seen.add(key)
                            interactions.append(r)
        else:
            if drug_count <= 1:
                interactions = []
            else:
                if ids:
                    conn = get_db_connection()
                    ph = ",".join(["%s"]*len(ids))
                    sql = f"""
                        SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                        FROM drug_interactions di
                        WHERE di.drugbank_id IN ({ph}) AND di.interacts_with_drugbank_id IN ({ph})
                    """
                    cur = conn.cursor()
                    cur.execute(sql, ids + ids)
                    rows = cur.fetchall()
                    conn.close()
                    seen = set()
                    for r in rows:
                        a = r.get("drugbank_id"); b = r.get("interacts_with_drugbank_id")
                        key = tuple(sorted([a, b]))
                        if key not in seen:
                            seen.add(key)
                            interactions.append(r)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB interactions error: {e}")

    system_message, user_message, interactions_count = build_prompt(body.user_id, body.drug_name, {"matches": lookup.get("matches", {}), "interactions": interactions}, info_by_id)

    # stream and return SSE
    generator = stream_llm_openai(system_message, user_message)

    # wrapper: simply forward chunks (no post-processing, because streaming)
    return StreamingResponse(generator, media_type="text/event-stream")

# --- Root / health ---
@app.get("/")
def root():
    return {"status": "ok", "note": "DrugBank-LLM API"}

if __name__ == "__main__":
    print("Run this app with uvicorn main:app --host 0.0.0.0 --port 8000")
