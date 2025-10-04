# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import os
import pymysql
import openai
from typing import List, Dict, Any, Optional, Union, Tuple, Generator
from dotenv import load_dotenv
import json
import re
from fastapi.responses import StreamingResponse
from passlib.context import CryptContext
import uvicorn

# =========================
# Boot
# =========================
load_dotenv()
app = FastAPI(title="DrugBank-LLM API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict on production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# =========================
# Config
# =========================
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "druguser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "supersecret")
DB_NAME = os.getenv("DB_NAME", "DrugBank")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
ALWAYS_INCLUDE_DEBUG = True  # แนบ debug เสมอเพื่อช่วยไล่ปัญหา

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # รองรับ vision ใน Chat Completions

if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# =========================
# Models
# =========================
class QueryBody(BaseModel):
    user_id: Optional[str] = None
    drug_name: List[str] = Field(default_factory=list)              # ยาที่ผู้ใช้พิมพ์เอง

    # เดิมของคุณ
    ocr_drug_name: Optional[Union[str, List[str]]] = None           # ถ้าเป็นข้อความ ให้ "ต่อ" เข้า list ด้วย

    # ใหม่+BC: รองรับทุกคีย์ที่หน้าบ้านอาจส่งมา
    img_base64: Optional[str] = None                                # <-- เพิ่ม: รองรับชื่อเดิม
    image_base64: Optional[str] = None                              # data URL หรือ base64 (รูปเดียว)
    images_base64: Optional[List[str]] = None                       # ถ้าส่งหลายรูป จะใช้รูปแรก

class LLMResult(BaseModel):
    prompt: str
    llm_response: str
    suggestion: bool
    drug_found: List[str]
    debug: Optional[Dict[str, Any]] = None

class UserCreate(BaseModel):
    email: str
    password: str
    confirm_password: str

class UserResponse(BaseModel):
    email: str
    id: int

class UserLogin(BaseModel):
    email: str
    password: str

class UserDrugCreate(BaseModel):
    drugbank_id: str

class UserDrugResponse(BaseModel):
    user_drugs_id: int
    drugbank_id: str
    drug_name: str
    created_at: str

class UserDrugAndDescription(BaseModel):
    id: int
    user_id: int
    drug_id: str
    drug_name: str
    drug_description: str
    created_at: str
    class Config:
        orm_mode = True

# =========================
# DB helpers
# =========================
def get_db_connection():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, local_infile=1
    )

def set_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)

def get_user_daily_drug_ids(user_id: Optional[str]) -> List[str]:
    if not user_id:
        return []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT drugbank_id FROM user_drugs WHERE user_id = %s;", (str(user_id),))
            rows = cur.fetchall()
            return [r["drugbank_id"] for r in rows if r.get("drugbank_id")]
    except Exception:
        return []
    finally:
        conn.close()

def fetch_interactions_between(set_a: List[str], set_b: List[str]) -> List[Dict[str, Any]]:
    if not set_a or not set_b:
        return []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            ph1 = ",".join(["%s"] * len(set_a))
            ph2 = ",".join(["%s"] * len(set_b))
            sql = f"""
                SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                FROM drug_interactions di
                WHERE (di.drugbank_id IN ({ph1}) AND di.interacts_with_drugbank_id IN ({ph2}))
                   OR (di.drugbank_id IN ({ph2}) AND di.interacts_with_drugbank_id IN ({ph1}))
            """
            params = set_a + set_b + set_b + set_a
            cur.execute(sql, params)
            rows = cur.fetchall()
        # dedupe symmetric
        seen = set()
        out = []
        for r in rows:
            a, b = r.get("drugbank_id"), r.get("interacts_with_drugbank_id")
            if not a or not b:
                continue
            key = tuple(sorted([a, b]))
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out
    finally:
        conn.close()

def fetch_all_interactions_for(single_id: str, limit: int = 10000) -> List[Dict[str, Any]]:
    if not single_id:
        return []
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                FROM drug_interactions di
                WHERE di.drugbank_id = %s OR di.interacts_with_drugbank_id = %s
                LIMIT %s;
            """
            cur.execute(sql, (single_id, single_id, limit))
            rows = cur.fetchall()
        seen = set()
        out = []
        for r in rows:
            a, b = r.get("drugbank_id"), r.get("interacts_with_drugbank_id")
            if not a or not b:
                continue
            key = tuple(sorted([a, b]))
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out
    finally:
        conn.close()

# =========================
# Lookup & mapping helpers
# =========================
def lookup_drugs_by_names(names: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    qnames = [n.strip() for n in names if isinstance(n, str) and n.strip()]
    if not qnames:
        return {"matches": {}}, []
    ids = set()
    matches: Dict[str, Dict[str, Any]] = {}
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # by name
            for q in qnames:
                likeq = f"%{q}%"
                cur.execute("SELECT drugbank_id, name, description FROM drugs WHERE name LIKE %s LIMIT 20;", (likeq,))
                rows = cur.fetchall()
                matches[q] = {"by_name": rows, "by_synonym": []}
                for r in rows:
                    if r.get("drugbank_id"):
                        ids.add(r["drugbank_id"])
            # by synonym
            for q in qnames:
                likeq = f"%{q}%"
                cur.execute("""
                    SELECT s.drugbank_id, s.synonym, d.name
                    FROM synonyms s
                    LEFT JOIN drugs d ON s.drugbank_id = d.drugbank_id
                    WHERE s.synonym LIKE %s
                    LIMIT 20;
                """, (likeq,))
                rows = cur.fetchall()
                matches[q]["by_synonym"] = rows
                for r in rows:
                    if r.get("drugbank_id"):
                        ids.add(r["drugbank_id"])
    finally:
        conn.close()
    return {"matches": matches}, list(ids)

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
    return {r["drugbank_id"]: r for r in rows}

def pick_single_best_id_from_match_entry(query: str, match_entry: Dict[str, Any]) -> Optional[str]:
    q = (query or "").strip().lower()
    if not match_entry:
        return None
    by_name = match_entry.get("by_name") or []
    by_syn  = match_entry.get("by_synonym") or []
    for r in by_name:
        if r.get("drugbank_id") and (r.get("name") or "").strip().lower() == q:
            return r["drugbank_id"]
    for r in by_syn:
        if r.get("drugbank_id") and (r.get("synonym") or "").strip().lower() == q:
            return r["drugbank_id"]
    if by_name and by_name[0].get("drugbank_id"):
        return by_name[0]["drugbank_id"]
    if by_syn and by_syn[0].get("drugbank_id"):
        return by_syn[0]["drugbank_id"]
    return None

# =========================
# LLM utilities (GPT-4o-mini)
# =========================
def _chat(messages: List[Dict[str, Any]], max_tokens: int = 800, temperature: float = 0.2) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured.")
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature
    )
    return (resp.choices[0].message.content or "").strip()

def _chat_stream(messages: List[Dict[str, Any]], max_tokens: int = 900, temperature: float = 0.2) -> Generator[str, None, None]:
    if not OPENAI_API_KEY:
        yield ""
        return
    resp = openai.ChatCompletion.create(
        model=OPENAI_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True
    )
    for chunk in resp:
        try:
            delta = chunk["choices"][0]["delta"].get("content", "")
            if delta:
                yield delta
        except Exception:
            continue

def llm_map_drug_names(names: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    dbg = {"called": False, "model": OPENAI_MODEL, "input": names, "output": None, "error": None}
    if not names:
        return [], dbg
    dbg["called"] = True
    instruction = (
        "You will receive a JSON array of drug names (Thai/brand/misspellings). "
        "Return a JSON array of English generic names (INN) in the same order. "
        "If unsure for any item, return the original item. Respond with the JSON array only."
    )
    try:
        raw = _chat([
            {"role": "system", "content": "You are a precise medical nomenclature normalizer."},
            {"role": "user", "content": instruction + "\nInput:\n" + json.dumps(names, ensure_ascii=False)}
        ], max_tokens=300, temperature=0)
        s, e = raw.find("["), raw.rfind("]")
        if s != -1 and e != -1 and e > s:
            raw = raw[s:e+1]
        mapped = json.loads(raw)
        dbg["output"] = mapped
        if isinstance(mapped, list) and len(mapped) == len(names):
            return [(str(x).strip() if x is not None else names[i]) for i, x in enumerate(mapped)], dbg
        return names, dbg
    except Exception as ex:
        dbg["error"] = str(ex)
        return names, dbg

def llm_pick_single_id(query: str, match_entry: Dict[str, Any]) -> Optional[str]:
    try:
        options = []
        for r in (match_entry.get("by_name") or []):
            options.append({"drugbank_id": r.get("drugbank_id"), "name": r.get("name"), "source": "name"})
        for r in (match_entry.get("by_synonym") or []):
            options.append({"drugbank_id": r.get("drugbank_id"), "name": r.get("synonym"), "source": "synonym"})
        if not options:
            return None
        payload = {"query": query, "options": options, "instruction": "Pick the best match. Return JSON: {'drugbank_id': 'DBxxxxx'}"}
        raw = _chat([
            {"role": "system", "content": "You are a strict selector. Return only one best match as JSON."},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        ], max_tokens=80, temperature=0)
        s, e = raw.find("{"), raw.rfind("}")
        if s == -1 or e == -1 or e <= s:
            return None
        data = json.loads(raw[s:e+1])
        did = (data or {}).get("drugbank_id")
        return did if isinstance(did, str) and did.strip() else None
    except Exception:
        return None

def llm_extract_drug_from_ocr_text(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    instr = (
        "From the following OCR text, extract exactly ONE most likely medicine/drug name (Thai or English). "
        "If none, return empty string. Respond with JSON: {'drug_name': '<name or empty>'}."
    )
    try:
        raw = _chat([
            {"role": "system", "content": "You are an OCR post-processor specialized in medicine names."},
            {"role": "user", "content": instr + "\nOCR:\n" + text}
        ], max_tokens=80, temperature=0)
        s, e = raw.find("{"), raw.rfind("}")
        if s == -1 or e == -1 or e <= s:
            return None
        data = json.loads(raw[s:e+1])
        name = (data or {}).get("drug_name")
        name = (name or "").strip()
        return name if name else None
    except Exception:
        return None

def looks_like_base64_image(s: str) -> bool:
    if not isinstance(s, str) or not s.strip():
        return False
    if s.startswith("data:image/") and ";base64," in s:
        return True
    return bool(re.fullmatch(r"[A-Za-z0-9+/=\s]{256,}", s.strip()))

def _ensure_data_url(img_b64: str) -> Optional[str]:
    if not isinstance(img_b64, str) or not img_b64.strip():
        return None
    s = img_b64.strip()
    if s.startswith("data:image/") and ";base64," in s:
        return s
    if looks_like_base64_image(s):
        return "data:image/jpeg;base64," + s
    return None

def llm_extract_names_from_image_base64(data_url: str, max_items: int = 5) -> List[str]:
    """
    ใช้ GPT‑4o‑mini (Vision) เพื่ออ่าน 'หลายชื่อ' จากภาพฉลาก
    คืนลิสต์สั้น ๆ (ไม่เกิน max_items)
    """
    if not data_url:
        return []
    try:
        prompt = (
            f"Check the label image and extract up to {max_items} names.\n"
            "- Allowed: product/brand names and active ingredients visible in the image.\n"
            "- Disallowed: dosage, manufacturer, slogans.\n"
            "- Respond ONLY this JSON array (no comments): [\"name1\",\"name2\",...]\n"
            "- If unreadable, respond []."
        )

        raw = _chat([
            {"role": "system", "content": "You read medicine labels and return JSON arrays only."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]}
        ], max_tokens=220, temperature=0)
        s, e = raw.find("["), raw.rfind("]")
        if s == -1 or e == -1 or e <= s:
            return []
        arr = json.loads(raw[s:e+1])
        if isinstance(arr, list):
            out = []
            for x in arr:
                if isinstance(x, str):
                    x2 = re.sub(r"\s+", " ", x).strip()
                    if x2:
                        out.append(x2[:120])
            # unique preserve order
            seen = set(); uniq = []
            for x in out:
                k = x.lower()
                if k not in seen:
                    seen.add(k); uniq.append(x)
            return uniq[:max_items]
        return []
    except Exception:
        return []

def llm_friendly_descriptions(names_to_desc: List[Dict[str, str]]) -> Dict[str, str]:
    if not names_to_desc:
        return {}
    instr = (
        "Rewrite or supply a short, layperson-friendly Thai explanation (1–2 sentences) for each drug below. "
        "Focus on what it helps with (e.g., pain relief, fever reduction). Avoid dosage. "
        "If info is limited, say 'ข้อมูลจำกัด'. Return JSON object mapping name -> explanation_th."
    )
    try:
        raw = _chat([
            {"role": "system", "content": "You are a medical writer who explains drugs in simple Thai accurately and safely."},
            {"role": "user", "content": instr + "\nInput:\n" + json.dumps(names_to_desc, ensure_ascii=False)}
        ], max_tokens=600, temperature=0.2)
        s, e = raw.find("{"), raw.rfind("}")
        if s == -1 or e == -1 or e <= s:
            return {}
        data = json.loads(raw[s:e+1])
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except Exception:
        return {}

# =========================
# Small utilities
# =========================
def _to_clean_list(items: Optional[List[str]]) -> List[str]:
    return [x.strip() for x in (items or []) if isinstance(x, str) and x.strip()]

def _collect_inputs(body: QueryBody) -> Tuple[List[str], Optional[str], Optional[str], bool]:
    """
    รวมชื่อจาก drug_name + ocr_drug_name (ข้อความ) + รูป (รองรับ img_base64 / image_base64 / images_base64[0])
    คืน: (names, ocr_raw_text, image_data_url, image_present_flag)
    """
    names = _to_clean_list(body.drug_name)
    ocr_raw = None
    image_b64 = None

    # 1) รองรับทั้งสามคีย์
    if body.image_base64:
        image_b64 = body.image_base64
    elif isinstance(body.images_base64, list) and body.images_base64:
        image_b64 = body.images_base64[0]
    elif body.img_base64:  # <-- สำคัญ: backward compatible
        image_b64 = body.img_base64

    # 2) ocr_drug_name ถ้าเป็นข้อความ ให้ "ต่อ" เข้า list ทีหลัง
    if isinstance(body.ocr_drug_name, str):
        # ถ้าดันส่ง base64 ผิดฟิลด์ จะจับไปเป็นรูปแทน
        if looks_like_base64_image(body.ocr_drug_name):
            if not image_b64:
                image_b64 = body.ocr_drug_name
        else:
            ocr_raw = body.ocr_drug_name

    data_url = _ensure_data_url(image_b64) if image_b64 else None
    return names, ocr_raw, data_url, bool(data_url)

def build_info_fallback(info_by_id: Dict[str, Dict[str, Any]], lookup_matches: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    if info_by_id:
        return info_by_id
    fallback: Dict[str, Dict[str, Any]] = {}
    for v in (lookup_matches or {}).values():
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

def _strip_db_ids_from_text(md: str) -> str:
    if not md:
        return md
    return re.sub(r"DB\d{5}", "", md)

def id_to_name_map(info_by_id: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    return {did: (row.get("name") or did) for did, row in (info_by_id or {}).items()}

def pair_interactions_to_name_lines(interactions: List[Dict[str, Any]], name_map: Dict[str, str]) -> List[str]:
    out = []
    for it in interactions:
        a = name_map.get(it.get("drugbank_id"), it.get("drugbank_id") or "")
        b = it.get("interacts_with_name") or name_map.get(it.get("interacts_with_drugbank_id"), it.get("interacts_with_drugbank_id") or "")
        desc = (it.get("description") or "").replace("\n", " ").strip()
        if a and b:
            out.append(f"- **{a}** ↔ **{b}**: {desc}")
    return out

# =========================
# Prompt builder (ข้อความไทย, ไม่แสดง ID)
# =========================
def build_messages_for_llm(
    user_id: Optional[str],
    mode: str,                                  # "SINGLE" | "LIST" | "NONE"
    asked_names: List[str],
    saved_names: List[str],
    info_for_asked: Dict[str, str],             # name -> friendly desc
    info_for_saved: Dict[str, str],             # name -> friendly desc
    interactions_name_lines: List[str]          # ["- **A** ↔ **B**: desc", ...]
) -> Tuple[str, str]:
    system_message = (
        "You are a careful medical assistant. Answer in Thai with clean Markdown. "
        "Keep it short and easy to read. Summarize only with the data given. "
        "Do NOT invent interactions. NEVER print any database codes."
    )
    asked_block = "\n".join([f"- **{n}**" + (f" — {info_for_asked.get(n)}" if info_for_asked.get(n) else "") for n in asked_names]) or "- (ไม่มี)"
    saved_block = "\n".join([f"- **{n}**" + (f" — {info_for_saved.get(n)}" if info_for_saved.get(n) else "") for n in saved_names]) or "- (ไม่มี)"
    inter_block = "\n".join(interactions_name_lines) if interactions_name_lines else "ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล"

    user_message = (
f"User ID: {user_id or 'Guest'}\n"
f"MODE: {mode}\n\n"
"## ยาที่สอบถาม\n"
f"{asked_block}\n\n"
"## ยาที่ทานอยู่ (จากคลังผู้ใช้)\n"
f"{saved_block}\n\n"
"## ผลสรุปปฏิกิริยา (Interactions)\n"
f"{inter_block}\n\n"
"> หมายเหตุ: ใช้เฉพาะข้อมูล interactions จากฐานข้อมูลที่ให้ไว้เท่านั้น และห้ามใส่รหัสยา"
    )
    return system_message, user_message

# =========================
# /analyze
# =========================
@app.post("/analyze", response_model=LLMResult)
def analyze(body: QueryBody):
    # 0) รวมอินพุต (ชื่อ + รูป + OCR text)
    input_names, ocr_raw_text, image_data_url, image_present = _collect_inputs(body)

    # 0.1) มีรูป → เอาเข้า LLM (Vision) สกัด “หลายชื่อ” แล้วต่อเข้า list
    vision_names: List[str] = []
    if image_present:
        vision_names = llm_extract_names_from_image_base64(image_data_url, max_items=5)
        input_names.extend(vision_names)

    # 0.2) ถ้ามี ocr_raw_text (ข้อความ) → ตามที่คุณขอ “เอาข้อความนี้ไป ‘ต่อ’ เข้า drug_name”
    if ocr_raw_text:
        input_names.append(ocr_raw_text)

        # และพยายามสกัดชื่อหลักจากข้อความ (เสริมความแม่น)
        picked = llm_extract_drug_from_ocr_text(ocr_raw_text)
        if picked:
            input_names.append(picked)

    # 1) ถ้าไม่มีชื่อใดเลย และไม่มี user → not found
    if not input_names and not body.user_id:
        return {
            "prompt": "N/A",
            "llm_response": "ไม่สามารถค้นหาจากฐานข้อมูลได้",
            "suggestion": False,
            "drug_found": [],
            "debug": {
                "input_names": [],
                "image_present": image_present,
                "vision_names": vision_names,
                "ocr_text_len": len(ocr_raw_text or ""),
                "mapped_names": [],
                "asked_ids": [],
                "user_saved_ids": [],
                "effective_ids": [],
                "interaction_pairs": 0,
                "mode": "NONE",
                "llm_model": OPENAI_MODEL
            }
        }

    # 2) map → INN
    mapped, map_dbg = llm_map_drug_names(input_names)

    # 3) lookup (ใช้ mapped ก่อน; ถ้าไม่เจอ ค่อย fallback original)
    matches_mapped, ids_from_lookup = lookup_drugs_by_names(mapped)
    any_matches = any((matches_mapped.get("matches") or {}).values())
    matches = matches_mapped
    if not any_matches and input_names:
        matches, ids_from_lookup = lookup_drugs_by_names(input_names)

    # 4) ถ้ามีแค่ 1 ชื่อ → เลือกตัวเดียวที่น่าเป็นไปได้ที่สุด
    chosen_single_id: Optional[str] = None
    if len(input_names) == 1:
        key_candidates = list((matches.get("matches") or {}).keys()) or (mapped or input_names)
        only_key = key_candidates[0] if key_candidates else (mapped[0] if mapped else input_names[0])
        entry = (matches.get("matches") or {}).get(only_key)
        chosen_single_id = pick_single_best_id_from_match_entry(only_key, entry) if entry else None
        if not chosen_single_id and entry:
            chosen_single_id = llm_pick_single_id(only_key, entry)
        if chosen_single_id:
            ids_from_lookup = [chosen_single_id]

    # 5) รวมกับยาของ user (คลังรายวัน)
    user_saved_ids: List[str] = get_user_daily_drug_ids(body.user_id)
    effective_ids = sorted(set(ids_from_lookup) | set(user_saved_ids))
    if not effective_ids and body.user_id:
        effective_ids = sorted(set(user_saved_ids))

    if not effective_ids:
        return {
            "prompt": "N/A",
            "llm_response": "ไม่สามารถค้นหาจากฐานข้อมูลได้",
            "suggestion": False,
            "drug_found": [],
            "debug": {
                "input_names": input_names,
                "image_present": image_present,
                "vision_names": vision_names,
                "ocr_text_len": len(ocr_raw_text or ""),
                "mapped_names": mapped,
                "map_debug": map_dbg,
                "asked_ids": [],
                "user_saved_ids": user_saved_ids,
                "effective_ids": [],
                "interaction_pairs": 0,
                "mode": "NONE",
                "llm_model": OPENAI_MODEL
            }
        }

    # 6) ข้อมูลยา + คำอธิบายง่าย ๆ
    info_by_id = fetch_info_for_ids(effective_ids)
    info_by_id = build_info_fallback(info_by_id, matches.get("matches", {}))
    name_map = id_to_name_map(info_by_id)

    asked_ids = ids_from_lookup[:]
    asked_names = [name_map.get(did, did) for did in asked_ids]
    saved_names = [name_map.get(did, did) for did in user_saved_ids]

    pack_asked = [{"name": n, "desc": (info_by_id.get(did, {}) or {}).get("description") or ""} 
                  for did, n in zip(asked_ids, asked_names)]
    pack_saved = [{"name": n, "desc": (info_by_id.get(did, {}) or {}).get("description") or ""} 
                  for did, n in zip(user_saved_ids, saved_names)]

    friendly_a = llm_friendly_descriptions(pack_asked) if pack_asked else {}
    friendly_s = llm_friendly_descriptions(pack_saved) if pack_saved else {}

    # 7) คำนวณโหมด + interactions
    interactions: List[Dict[str, Any]] = []
    mode = "LIST"
    if len(effective_ids) >= 2:
        interactions = fetch_interactions_between(effective_ids, effective_ids)
    elif len(effective_ids) == 1:
        only_id = effective_ids[0]
        if (len(input_names) == 1) and (len(user_saved_ids) == 0):
            interactions = fetch_all_interactions_for(only_id)
            mode = "SINGLE"
        else:
            mode = "SINGLE"

    interactions_name_lines = pair_interactions_to_name_lines(interactions, name_map)

    # 8) Prompt & LLM สรุป
    system_message, user_message = build_messages_for_llm(
        user_id=body.user_id,
        mode=mode,
        asked_names=asked_names,
        saved_names=saved_names,
        info_for_asked=friendly_a,
        info_for_saved=friendly_s,
        interactions_name_lines=interactions_name_lines
    )
    try:
        llm_text = _chat([
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ], max_tokens=900, temperature=0.2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    # 9) ป้องกันรหัส DB + guard
    llm_text = _strip_db_ids_from_text(llm_text).strip()
    if interactions_name_lines and "ไม่พบข้อมูลการโต้ตอบ" in llm_text:
        llm_text = re.sub(r"ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล[^\n]*", "", llm_text).strip()

    # 10) Suggestion: ยาใหม่ 1 ตัวที่ยังไม่อยู่ในคลัง
    new_ids = [did for did in ids_from_lookup if did not in set(user_saved_ids)]
    is_suggestion = (len(new_ids) == 1)

    debug_obj = {
        "input_names": input_names,
        "image_present": image_present,
        "vision_names": vision_names,
        "ocr_text_len": len(ocr_raw_text or ""),
        "mapped_names": mapped,
        "map_debug": map_dbg,
        "asked_ids": asked_ids,
        "user_saved_ids": user_saved_ids,
        "effective_ids": effective_ids,
        "interaction_pairs": len(interactions),
        "mode": mode,
        "llm_model": OPENAI_MODEL
    }

    return {
        "prompt": user_message,
        "llm_response": llm_text,
        "suggestion": is_suggestion,
        "drug_found": effective_ids,
        "debug": debug_obj if (ALWAYS_INCLUDE_DEBUG or DEBUG) else None
    }

# =========================
# /analyze_stream (SSE)
# =========================
@app.post("/analyze_stream")
def analyze_stream(body: QueryBody):
    # ทำงานเหมือน /analyze จนถึงการสร้าง system_message/user_message แล้วสตรีมเฉพาะผลลัพธ์

    input_names, ocr_raw_text, image_data_url, image_present = _collect_inputs(body)
    vision_names: List[str] = []
    if image_present:
        vision_names = llm_extract_names_from_image_base64(image_data_url, max_items=5)
        input_names.extend(vision_names)
    if ocr_raw_text:
        input_names.append(ocr_raw_text)
        picked = llm_extract_drug_from_ocr_text(ocr_raw_text)
        if picked:
            input_names.append(picked)

    if not input_names and not body.user_id:
        def gen_empty():
            yield f"data: {json.dumps({'error': 'no inputs'})}\n\n"
            yield "data: {\"done\": true}\n\n"
        return StreamingResponse(gen_empty(), media_type="text/event-stream")

    mapped, map_dbg = llm_map_drug_names(input_names)
    matches_mapped, ids_from_lookup = lookup_drugs_by_names(mapped)
    any_matches = any((matches_mapped.get("matches") or {}).values())
    matches = matches_mapped if any_matches else lookup_drugs_by_names(input_names)[0]
    if not any_matches:
        ids_from_lookup = lookup_drugs_by_names(input_names)[1]

    chosen_single_id: Optional[str] = None
    if len(input_names) == 1:
        key_candidates = list((matches.get("matches") or {}).keys()) or (mapped or input_names)
        only_key = key_candidates[0] if key_candidates else (mapped[0] if mapped else input_names[0])
        entry = (matches.get("matches") or {}).get(only_key)
        chosen_single_id = pick_single_best_id_from_match_entry(only_key, entry) if entry else None
        if not chosen_single_id and entry:
            chosen_single_id = llm_pick_single_id(only_key, entry)
        if chosen_single_id:
            ids_from_lookup = [chosen_single_id]

    user_saved_ids: List[str] = get_user_daily_drug_ids(body.user_id)
    effective_ids = sorted(set(ids_from_lookup) | set(user_saved_ids)) or sorted(set(user_saved_ids))

    info_by_id = fetch_info_for_ids(effective_ids) if effective_ids else {}
    info_by_id = build_info_fallback(info_by_id, matches.get("matches", {}))
    name_map = id_to_name_map(info_by_id)
    asked_names = [name_map.get(did, did) for did in ids_from_lookup]
    saved_names = [name_map.get(did, did) for did in user_saved_ids]

    pack_asked = [{"name": n, "desc": (info_by_id.get(did, {}) or {}).get("description") or ""} 
                  for did, n in zip(ids_from_lookup, asked_names)]
    pack_saved = [{"name": n, "desc": (info_by_id.get(did, {}) or {}).get("description") or ""} 
                  for did, n in zip(user_saved_ids, saved_names)]

    friendly_a = llm_friendly_descriptions(pack_asked) if pack_asked else {}
    friendly_s = llm_friendly_descriptions(pack_saved) if pack_saved else {}

    interactions: List[Dict[str, Any]] = []
    mode = "LIST"
    if len(effective_ids) >= 2:
        interactions = fetch_interactions_between(effective_ids, effective_ids)
    elif len(effective_ids) == 1:
        only_id = effective_ids[0]
        if (len(input_names) == 1) and (len(user_saved_ids) == 0):
            interactions = fetch_all_interactions_for(only_id)
            mode = "SINGLE"
        else:
            mode = "SINGLE"

    interactions_name_lines = pair_interactions_to_name_lines(interactions, name_map)

    system_message, user_message = build_messages_for_llm(
        user_id=body.user_id,
        mode=mode,
        asked_names=asked_names,
        saved_names=saved_names,
        info_for_asked=friendly_a,
        info_for_saved=friendly_s,
        interactions_name_lines=interactions_name_lines
    )

    def gen():
        # header event (optional debug)
        header = {
            "input_names": input_names,
            "image_present": image_present,
            "vision_names": vision_names,
            "mapped_names": mapped,
            "mode": mode
        }
        yield f"data: {json.dumps({'debug': header}, ensure_ascii=False)}\n\n"

        # stream LLM
        for delta in _chat_stream(
            [{"role": "system", "content": system_message},
             {"role": "user", "content": user_message}],
            max_tokens=900, temperature=0.2
        ):
            yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")

# =========================
# Users
# =========================
@app.post("/users/", response_model=UserResponse)
async def create_user(user: UserCreate):
    if user.password != user.confirm_password:
        raise HTTPException(status_code=401, detail="Password and Confirm Password do not match")
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (user.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")
            cursor.execute(
                "INSERT INTO users (email, password_hash, is_active, is_verified) VALUES (%s, %s, TRUE, TRUE)",
                (user.email, set_password(user.password))
            )
            connection.commit()
            cursor.execute("SELECT id, email FROM users WHERE email = %s", (user.email,))
            row = cursor.fetchone()
            return UserResponse(id=row["id"], email=row["email"])
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        connection.close()

@app.post("/users/login")
async def login_user(user_login: UserLogin):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE email = %s", (user_login.email,))
            user = cursor.fetchone()
            if not user or not verify_password(user_login.password, user["password_hash"]):
                raise HTTPException(status_code=401, detail="Incorrect email or password")
            if not user.get("is_active", True):
                raise HTTPException(status_code=400, detail="Inactive user account")
            return {"message": "Login successful", "user": user}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    finally:
        connection.close()

# =========================
# User-Drugs
# =========================
@app.post("/user-drugs/{user_id}", response_model=UserDrugResponse)
async def create_user_drug(user_drug: UserDrugCreate, user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="User not found")

            cursor.execute("SELECT * FROM user_drugs WHERE user_id = %s AND drugbank_id = %s", (user_id, user_drug.drugbank_id))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="User already has this drug")

            cursor.execute("INSERT INTO user_drugs (user_id, drugbank_id) VALUES (%s, %s)", (user_id, user_drug.drugbank_id))
            connection.commit()

            cursor.execute("""
                SELECT user_drugs.id AS user_drugs_id,
                       user_drugs.drugbank_id AS drugbank_id,
                       drugs.name AS drug_name,
                       user_drugs.created_at AS created_at
                FROM user_drugs
                JOIN drugs ON drugs.drugbank_id = user_drugs.drugbank_id
                WHERE user_drugs.user_id = %s AND user_drugs.drugbank_id = %s
            """, (user_id, user_drug.drugbank_id))
            row = cursor.fetchone()
            return UserDrugResponse(
                user_drugs_id=row["user_drugs_id"],
                drugbank_id=row["drugbank_id"],
                drug_name=row["drug_name"],
                created_at=row["created_at"].isoformat()
            )
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        connection.close()

@app.get("/user-drugs/{user_id}", response_model=List[UserDrugAndDescription])
async def get_user_drug(user_id: int):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT user_drugs.id AS user_drug_id,
                       user_drugs.user_id AS user_id,
                       drugs.drugbank_id AS drug_drugbank_id,
                       drugs.name AS drug_name,
                       drugs.description AS drug_description,
                       user_drugs.created_at AS created_at
                FROM user_drugs
                JOIN drugs ON drugs.drugbank_id = user_drugs.drugbank_id
                WHERE user_drugs.user_id = %s
            """, (user_id,))
            rows = cursor.fetchall()
            if not rows:
                raise HTTPException(status_code=404, detail="User-drug relationship not found")
            return [
                UserDrugAndDescription(
                    id=r["user_drug_id"],
                    user_id=r["user_id"],
                    drug_id=r["drug_drugbank_id"],
                    drug_name=r["drug_name"],
                    drug_description=r["drug_description"],
                    created_at=r["created_at"].isoformat()
                ) for r in rows
            ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        connection.close()

@app.delete("/user-drugs/{user_drug_id}")
async def delete_user_drug(user_drug_id: str):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM user_drugs WHERE id = %s", (user_drug_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="User-drug relationship not found")
            cursor.execute("DELETE FROM user_drugs WHERE id = %s", (user_drug_id,))
            connection.commit()
            return {"message": "User-drug relationship deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    finally:
        connection.close()

# =========================
# Main
# =========================
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
