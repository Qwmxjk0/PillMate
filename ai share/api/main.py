#!/usr/bin/env python3
# main.py -- DrugBank LLM API (full) with improved img_base64 OCR support + LLM-based OCR filtering
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
import base64
import io
from PIL import Image, ImageOps, ImageFilter, ImageEnhance
import pytesseract
import shutil
import traceback

load_dotenv()

app = FastAPI(title="DrugBank-LLM API (OCR-enabled)")

# --- Configuration (จาก .env หรือค่าเริ่มต้น) ---
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "DrugBank")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEBUG = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")

# maximum image bytes (base64 decoded) we'll accept
MAX_IMG_BYTES = int(os.getenv("MAX_IMG_BYTES", 5 * 1024 * 1024))  # 5 MB default

if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# --- Models ---
class QueryBody(BaseModel):
    user_id: Optional[str] = None
    drug_name: List[str] = []
    img_base64: Optional[str] = None  # accept data URI or plain base64
    ocr_only: Optional[bool] = False  # if true: run OCR, return OCR results and skip LLM/DB
    ocr_lang: Optional[str] = "tha+eng"  # default languages for Tesseract

class LLMResult(BaseModel):
    prompt: str
    llm_response: str
    ocr_text: Optional[str] = None
    ocr_candidates: Optional[List[str]] = []
    mapped_names: Optional[List[str]] = []

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

# --- Utility: detect tesseract availability ---
def has_tesseract():
    try:
        v = pytesseract.get_tesseract_version()  # will raise if binary missing
        if DEBUG:
            print("Tesseract version:", v)
        return True
    except Exception as e:
        if DEBUG:
            print("Tesseract not available:", e)
        return False

# --- OCR helper ---
def extract_base64_data(b64str: str) -> Optional[bytes]:
    """
    Extract raw base64 bytes from a string. Accepts data URI or plain base64.
    Returns decoded bytes or None on failure.
    """
    if not b64str or not isinstance(b64str, str):
        return None
    try:
        if b64str.startswith("data:"):
            parts = b64str.split(",", 1)
            b64payload = parts[1] if len(parts) == 2 else ""
        else:
            b64payload = b64str.strip()
        b64payload = re.sub(r"\s+", "", b64payload)
        decoded = base64.b64decode(b64payload, validate=True)
        if len(decoded) > MAX_IMG_BYTES:
            raise ValueError(f"image too large ({len(decoded)} bytes, limit {MAX_IMG_BYTES})")
        return decoded
    except Exception as e:
        if DEBUG:
            print("extract_base64_data error:", e)
        return None

def preprocess_image_for_ocr(img: Image.Image, max_dim: int = 1600) -> Image.Image:
    """
    Preprocessing to help Tesseract:
     - convert to RGB, resize if needed
     - grayscale, enhance contrast, denoise, sharpen
    """
    try:
        img = img.convert("RGB")
        w, h = img.size
        if max(w, h) > max_dim:
            scale = max_dim / float(max(w, h))
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.LANCZOS)

        gray = ImageOps.grayscale(img)
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(1.4)
        gray = gray.filter(ImageFilter.MedianFilter(size=3))
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1, percent=100, threshold=1))
        return gray
    except Exception as e:
        if DEBUG:
            print("preprocess_image_for_ocr error:", e)
        return img

def ocr_from_base64(b64str: str, lang: str = "tha+eng") -> str:
    """
    Debugging OCR: save image, try multiple configs/langs,
    return the best OCR text (and print debug info to stdout when DEBUG=True).
    """
    try:
        # 1) decode
        data = extract_base64_data(b64str)
        if not data:
            if DEBUG:
                print("ocr_from_base64: no decoded image data")
            return ""
        # 2) save raw image for inspection
        try:
            save_path = f"/tmp/ocr_debug_{int(time.time())}.png"
            with open(save_path, "wb") as f:
                f.write(data)
            if DEBUG:
                print("Saved decoded image to:", save_path)
        except Exception as e:
            save_path = None
            if DEBUG:
                print("Could not save decoded image:", e)

        # 3) open + preprocess
        img = Image.open(io.BytesIO(data))
        if DEBUG:
            print("Original image mode/size:", img.mode, img.size)
        img_proc = preprocess_image_for_ocr(img)

        # 4) Try multiple language/config combos and take the longest non-empty result
        candidates = []
        try_langs = []
        # build sensible fallbacks
        if lang:
            try_langs.append(lang)
        try_langs += ["eng", "tha", "eng+tha"]

        # common psm choices
        psm_list = ["", "--psm 6", "--psm 3", "--psm 11"]  # 6 = assume a single uniform block of text, 3 = fully automatic page segmentation

        for L in try_langs:
            for psm in psm_list:
                cfg = psm
                try:
                    raw = pytesseract.image_to_string(img_proc, lang=L, config=cfg) if cfg else pytesseract.image_to_string(img_proc, lang=L)
                except Exception as e:
                    raw = ""
                    if DEBUG:
                        print(f"pytesseract error lang={L} cfg='{cfg}':", e)
                text = (raw or "").strip()
                text = re.sub(r"\s+", " ", text)
                if text:
                    # also get word-level confidences for this combo
                    try:
                        d = pytesseract.image_to_data(img_proc, lang=L, config=cfg, output_type=pytesseract.Output.DICT)
                        words = []
                        for i, w in enumerate(d.get('text', [])):
                            conf = d.get('conf', [])[i] if 'conf' in d else None
                            if str(w).strip():
                                words.append({"word": w, "conf": conf})
                    except Exception:
                        words = []
                    candidates.append({"lang": L, "config": cfg, "text": text, "words": words})
                    if DEBUG:
                        print(f"Got OCR (len {len(text)}) lang={L} cfg='{cfg}'")
        # choose best candidate heuristics: longest text with some words/confidence
        if candidates:
            candidates_sorted = sorted(candidates, key=lambda x: (len(x["text"]), sum([ (int(w["conf"]) if w["conf"] and str(w["conf"]).isdigit() else 50) for w in x["words"] ]) ), reverse=True)
            best = candidates_sorted[0]
            if DEBUG:
                print("OCR candidates count:", len(candidates), "best:", best["lang"], best["config"])
            return best["text"]
        else:
            if DEBUG:
                print("OCR produced no candidates.")
            return ""
    except Exception as e:
        if DEBUG:
            import traceback
            print("ocr_from_base64 error:", e)
            traceback.print_exc()
        return ""


# --- LLM-based mapping: ไทย -> English generic names (one call) ---
def llm_map_drug_names(names: List[str]) -> List[str]:
    """
    ใส่ชื่อ (ไทย/อังกฤษ/brand) -> คืนชื่อสามัญภาษาอังกฤษ (INN) ในรูป list เดิมความยาวเท่ากัน
    ถ้าไม่มี openai key จะ return names เดิม
    """
    if not names:
        return names
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
        # prefer gpt-4o-mini if available, fallback to gpt-3.5-turbo
        model_choice = "gpt-4o-mini" if "gpt-4o-mini" in [] else "gpt-3.5-turbo"
        resp = openai.ChatCompletion.create(
            model=model_choice,
            messages=messages,
            max_tokens=200,
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end+1]
        mapped = json.loads(raw)
        if isinstance(mapped, list) and len(mapped) == len(names):
            return [ (str(x).strip() if x is not None else names[i]) for i,x in enumerate(mapped) ]
        return names
    except Exception as e:
        if DEBUG:
            print("llm_map_drug_names error:", e)
        return names

# --- LLM filter for OCR text (optional clean up) ---
def llm_filter_ocr_text(ocr_text: str) -> List[str]:
    """
    Use LLM to extract likely drug-name candidates from OCR text.
    Returns a list of short names/phrases.
    If LLM not available, fallback to simple splitting.
    """
    if not ocr_text:
        return []
    # quick heuristic split first
    heur_candidates = re.split(r"[\r\n,;|/·••]+", ocr_text)
    heur_candidates = [c.strip() for c in heur_candidates if c.strip()]
    if not (LLM_PROVIDER == "openai" and OPENAI_API_KEY):
        # return heuristics (trim to short items)
        return [c for c in heur_candidates if 1 <= len(c) <= 60][:20]

    # Use LLM to pick/normalize names
    prompt = (
        "You will be given a chunk of text (OCR output) that may contain product labels and other words.\n"
        "Return a JSON array of short strings that are likely drug names or product names found in the text, in the order you find them.\n"
        "Do not include non-drug words. If unsure about an item, include it anyway (we will validate later). Return only the JSON array.\n\n"
        "OCR Text:\n" + ocr_text
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"You are a helpful extractor that returns JSON arrays only."},
                {"role":"user","content":prompt}
            ],
            max_tokens=200,
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end+1]
        cand = json.loads(raw)
        if isinstance(cand, list):
            # cleanup whitespace
            cand = [re.sub(r"\s+", " ", str(x)).strip() for x in cand if str(x).strip()]
            return cand[:30]
        else:
            return heur_candidates[:30]
    except Exception as e:
        if DEBUG:
            print("llm_filter_ocr_text error:", e)
        return heur_candidates[:30]

# --- Lookup drugs and interactions in DB ---
# (same implementation as your original; omitted here for brevity — include the same code)
# For brevity in this snippet we reuse your existing lookup_drugs, fetch_info_for_ids, build_prompt, stream/call LLM functions.
# Paste the original implementations here (unchanged) or keep as in your working file.

# --- For this response I'll re-include the same implementations for lookup_drugs, fetch_info_for_ids, build_prompt, call_llm_openai, stream_llm_openai, build_info_fallback ---
# (TO AVOID LENGTHY DUPLICATION in this snippet: use your existing functions from the original file unchanged)
# ---------------------------
# Insert your existing functions here: lookup_drugs, fetch_info_for_ids, build_prompt,
# call_llm_openai, stream_llm_openai, build_info_fallback
# ---------------------------

# To keep the file self-contained, below I will paste the unchanged implementations (copy from your original file).
# (*** PASTE the previous functions lookup_drugs, fetch_info_for_ids, build_prompt, call_llm_openai, stream_llm_openai, build_info_fallback here exactly as you already have them ***)
# For the sake of clarity in this replacement file, **do not remove** your previous implementations.
# ---------------------------
# (BEGIN: paste unchanged implementations) 

# --- Lookup drugs and interactions in DB ---
def lookup_drugs(drug_names: List[str]) -> Dict[str, Any]:
    def normalize_text(s: str) -> str:
        s = (s or "").strip().lower()
        return re.sub(r"[^\w\u0E00-\u0E7F]", "", s)

    qnames = [dn.strip() for dn in drug_names if dn and dn.strip()]
    if not qnames:
        return {"matches": {}, "interactions": []}

    ids = set()
    matches = {}

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            for q in qnames:
                q_lower = q.lower()
                q_norm = normalize_text(q)
                matches[q] = {"by_name": [], "by_synonym": [], "match_ids": set()}

                cur.execute(
                    "SELECT s.drugbank_id, s.synonym, d.name FROM synonyms s "
                    "LEFT JOIN drugs d ON s.drugbank_id=d.drugbank_id "
                    "WHERE LOWER(s.synonym) = %s LIMIT 50;",
                    (q_lower,)
                )
                syn_rows = cur.fetchall()
                for r in syn_rows:
                    r['_match_type'] = 'exact_synonym'
                    matches[q]["by_synonym"].append(r)
                    matches[q]["match_ids"].add(r.get("drugbank_id"))
                    ids.add(r.get("drugbank_id"))

                cur.execute(
                    "SELECT drugbank_id, name, description FROM drugs WHERE LOWER(name) = %s LIMIT 50;",
                    (q_lower,)
                )
                name_rows = cur.fetchall()
                for r in name_rows:
                    r['_match_type'] = 'exact_name'
                    matches[q]["by_name"].append(r)
                    matches[q]["match_ids"].add(r.get("drugbank_id"))
                    ids.add(r.get("drugbank_id"))

                if not matches[q]["match_ids"] and q_norm:
                    cur.execute(
                        "SELECT drugbank_id, name, description FROM drugs "
                        "WHERE LOWER(REPLACE(REPLACE(REPLACE(name,' ',''),'-',''),'.','')) = %s LIMIT 50;",
                        (q_norm,)
                    )
                    norm_rows = cur.fetchall()
                    for r in norm_rows:
                        r['_match_type'] = 'normalized_exact'
                        matches[q]["by_name"].append(r)
                        matches[q]["match_ids"].add(r.get("drugbank_id"))
                        ids.add(r.get("drugbank_id"))

                if not matches[q]["match_ids"]:
                    try:
                        cur.execute(
                            "SELECT drugbank_id, name, description FROM drugs WHERE SOUNDEX(name) = SOUNDEX(%s) LIMIT 50;",
                            (q,)
                        )
                        sx_rows = cur.fetchall()
                        for r in sx_rows:
                            r['_match_type'] = 'soundex'
                            matches[q]["by_name"].append(r)
                            matches[q]["match_ids"].add(r.get("drugbank_id"))
                            ids.add(r.get("drugbank_id"))
                    except Exception:
                        pass

                if not matches[q]["match_ids"]:
                    likeq = f"%{q}%"
                    cur.execute(
                        "SELECT drugbank_id, name, description FROM drugs WHERE name LIKE %s LIMIT 50;",
                        (likeq,)
                    )
                    like_rows = cur.fetchall()
                    for r in like_rows:
                        r['_match_type'] = 'like'
                        matches[q]["by_name"].append(r)
                        matches[q]["match_ids"].add(r.get("drugbank_id"))
                        ids.add(r.get("drugbank_id"))

                if not matches[q]["by_synonym"]:
                    likeq = f"%{q}%"
                    cur.execute(
                        "SELECT s.drugbank_id, s.synonym, d.name FROM synonyms s LEFT JOIN drugs d ON s.drugbank_id=d.drugbank_id WHERE s.synonym LIKE %s LIMIT 50;",
                        (likeq,)
                    )
                    syn_like_rows = cur.fetchall()
                    for r in syn_like_rows:
                        r['_match_type'] = 'synonym_like'
                        matches[q]["by_synonym"].append(r)
                        matches[q]["match_ids"].add(r.get("drugbank_id"))
                        ids.add(r.get("drugbank_id"))

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

    for q in matches:
        matches[q]["match_ids"] = list(matches[q]["match_ids"])

    return {"matches": matches, "interactions": interactions}

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

def build_info_fallback(info_by_id: Dict[str, Dict[str, Any]], lookup_matches: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
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

def build_prompt(user_id: Optional[str], original_names: List[str], lookup_result: Dict[str, Any], info_by_id: Dict[str, Dict[str, Any]]):
    system_message = (
    "คุณเป็นเครื่องสรุปข้อเท็จจริงอย่างเคร่งครัด (strict factual summarizer). ใช้ข้อมูลเฉพาะเท่าที่ปรากฎในข้อความที่ผู้ใช้ส่งมาเท่านั้น — "
    "ห้ามเสริม เติม หรือให้ข้อมูลเพิ่มเติมนอกเหนือจากที่ปรากฎในบันทึกนั้น ๆ.\n\n"

    "ผลลัพธ์ต้องเป็น **ภาษาไทย** เท่านั้น และจัดรูปแบบเป็น **Markdown**. ห้ามแสดงแถวตารางดิบ (rows) หรือ ID ใด ๆ ให้ผู้ใช้เห็น.\n\n"

    "ส่วน **ข้อมูลยา (Information)** — ข้อกำหนดละเอียด:\n"
    "1. แสดงเป็นข้อย่อย (bullet list) **หนึ่งประโยคสั้นต่อยา** (ไม่เกิน 1–2 ประโยคสั้น) — ต้องเป็นประโยคที่อ่านง่ายสำหรับคนทั่วไป.\n"
    "2. ห้ามแสดง ID หรือ raw table rows ใด ๆ.\n"
    "3. สำหรับแต่ละยา หากในบันทึกที่ให้มามี `description` หรือข้อมูลชัดเจน ให้ต่อท้ายด้วยข้อความในวงเล็บเป็นคำอธิบายสั้น ๆ (3–10 คำไทย เป็นวลีสั้น ๆ) ที่อธิบายการใช้/indication แบบคนทั่วไป (เช่น '(รักษา/ป้องกันลิ่มเลือด)', '(ลดการอักเสบ)').\n"
    "4. หากคำอธิบายเป็นศัพท์เทคนิค ให้แปลงเป็นภาษาชาวบ้านและใช้วลีในวงเล็บตามข้อ (3).\n"
    "5. หาก **ไม่มีข้อมูลเพียงพอ** ในบันทึกที่ส่งมาและคุณไม่สามารถสรุปคำอธิบายอย่างน่าเชื่อถือได้ **อย่าใส่วงเล็บเลย** — ปล่อยเฉพาะชื่อยาเป็นข้อย่อย (ไม่ใส่ '(ไม่มีคำอธิบาย)' หรือข้อความอื่น) .\n"
    "6. ห้ามเติมข้อบ่งชี้หรือการใช้ยาใหม่ ๆ ที่ไม่สามารถอนุมานได้จากบันทึกที่ให้มา.\n\n"

    "ส่วน **สรุปปฏิกิริยา (Interactions)** — ข้อกำหนด:\n"
    "1. ให้สรุปเฉพาะรายการการโต้ตอบที่ปรากฎในส่วน 'raw records' ที่ถูกส่งมาเท่านั้น — ห้ามเดาหรือขยายความนอกเหนือจากบรรทัดเหล่านั้น.\n"
    "2. หากจำนวน interaction records = 0 ให้ในหัวข้อนี้พิมพ์ **ข้อความเดียวเท่านั้น** (และอย่าเพิ่มอะไรอีก):\n"
    "   `ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล`\n"
    "3. หากมีรายการ ให้สรุปเป็น bullet points สั้น ๆ โดยอ้างถึงชื่อยาที่ปรากฎใน raw records เท่านั้น (ไม่ต้องใส่ ID).\n\n"

    "ข้อเพิ่มเติมในการเขียน:\n"
    "- ตอบสั้น กระชับ (รวมทั้งหน้า 2–4 ย่อหน้าโดยประมาณ) และหลีกเลี่ยงคำศัพท์เทคนิคที่ซับซ้อน — ถ้าจำเป็นให้แปลเป็นคำง่าย ๆ.\n"
    "- ห้ามกล่าวถึงยาหรือข้อมูลที่ไม่ได้อยู่ในบันทึกที่ส่งมา (เช่น อย่าเพิ่ม 'Nitroaspirin' หรือยาอื่น ๆ หากไม่มีใน matched/interactions ที่ส่งมาอย่างชัดเจน).\n"
    "- หากพบความไม่สอดคล้องในข้อมูล ให้ตอบว่า 'ไม่แน่ใจ' ในวงเล็บเมื่อจำเป็น แต่อย่าใช้เป็นข้ออ้างให้เติมข้อมูลใหม่.\n"
    )

    lines = []
    lines.append(f"User ID: {user_id or 'Guest'}")
    lines.append("")
    lines.append("Query drug names (original):")
    for q in original_names:
        lines.append(f"- {q}")
    lines.append("")

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
        lines.append("- (no interaction records found)")

    lines.append("")
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
            temperature=0,
        )
        if hasattr(resp.choices[0].message, 'content'):
            return resp.choices[0].message.content
        return str(resp)
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

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
            except Exception:
                continue
        yield f"data: {json.dumps({'done': True})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

# (END: pasted functions)
# ---------------------------

# --- API endpoints ---

@app.post("/analyze", response_model=LLMResult)
def analyze(body: QueryBody):
    # 0) OCR if provided
    ocr_text = ""
    ocr_candidates = []
    tesseract_available = has_tesseract()
    if body.img_base64:
        if DEBUG:
            print("DEBUG: img_base64 provided, running OCR...")
        ocr_text = ocr_from_base64(body.img_base64, lang=body.ocr_lang or "tha+eng")
        if DEBUG:
            print("DEBUG OCR text raw:", repr(ocr_text))
        if ocr_text:
            # heuristic split to candidates
            candidates = re.split(r"[\r\n,;|/·••]+", ocr_text)
            candidates = [c.strip() for c in candidates if c.strip()]
            # use LLM to filter/normalize OCR candidates (if available)
            filtered = llm_filter_ocr_text(ocr_text) if (LLM_PROVIDER == "openai" and OPENAI_API_KEY) else candidates
            ocr_candidates = filtered or candidates
        else:
            if not tesseract_available:
                ocr_text = ""
                ocr_candidates = []
    # If ocr_only requested, return OCR results immediately
    if body.ocr_only:
        prompt = ""
        return {"prompt": prompt, "llm_response": "OCR only mode", "ocr_text": ocr_text, "ocr_candidates": ocr_candidates, "mapped_names": []}

    # 1) build starting drug_names from provided drug_name + OCR candidates
    drug_names = list(body.drug_name or [])
    if ocr_candidates:
        # append unique candidates
        for c in ocr_candidates:
            if c not in drug_names:
                drug_names.append(c)

    # 2) mapping names via LLM (optional)
    mapped = llm_map_drug_names(drug_names) if (LLM_PROVIDER == "openai" and OPENAI_API_KEY) else drug_names
    if DEBUG:
        print("DEBUG mapped:", mapped)

    # 3) lookup
    try:
        lookup = lookup_drugs(mapped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB lookup error: {e}")

    # fallback: if mapped produced no matches at all, retry with original drug_names
    any_matches = any((lookup.get("matches", {}) or {}).values())
    if DEBUG:
        print("DEBUG any_matches after mapped lookup:", any_matches)
    if not any_matches and drug_names:
        retry_lookup = lookup_drugs(drug_names)
        if any((retry_lookup.get("matches", {}) or {}).values()):
            lookup = retry_lookup
            if DEBUG:
                print("DEBUG: fallback to original names for lookup")

    # 4) gather ids and fetch info
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
    info_by_id = build_info_fallback(info_by_id, lookup.get("matches", {}))

    # 5) determine interactions (reusing your logic)
    is_user = bool(body.user_id)
    drug_count = len(ids)
    interactions = []
    try:
        # (copy the same interactions logic you already had)...
        # For brevity, call lookup_drugs again for interactions or reuse previously computed interactions if available.
        # Here we'll reuse the earlier 'lookup' structure's interactions if present.
        interactions = lookup.get("interactions", []) or []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB interactions error: {e}")

    # 6) build prompt and call LLM to produce final summary
    system_message, user_message, interactions_count = build_prompt(body.user_id, drug_names, {"matches": lookup.get("matches", {}), "interactions": interactions}, info_by_id)
    if DEBUG:
        print("DEBUG system_message preview:", system_message[:800])
        print("DEBUG user_message preview:", user_message[:1600])

    if LLM_PROVIDER == "openai":
        try:
            llm_text = call_llm_openai(system_message, user_message)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM error: {e}")
    else:
        raise HTTPException(status_code=501, detail="Only openai LLM_PROVIDER implemented")

    # 7) Sanity clean
    if interactions_count > 0 and "ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล" in llm_text:
        llm_text = re.sub(r"(?i)ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล[^\n]*", "", llm_text).strip()
        if not llm_text:
            llm_text = "มีข้อมูลการโต้ตอบระหว่างยา (รายละเอียดถูกลบโดยระบบตรวจสอบความสอดคล้อง)"

    return {"prompt": user_message, "llm_response": llm_text, "ocr_text": ocr_text, "ocr_candidates": ocr_candidates, "mapped_names": mapped}

@app.post("/analyze_stream")
def analyze_stream(body: QueryBody):
    # replicate main analyze flow but stream LLM output
    ocr_text = ""
    ocr_candidates = []
    tesseract_available = has_tesseract()
    if body.img_base64:
        if DEBUG:
            print("DEBUG: img_base64 provided (stream), running OCR...")
        ocr_text = ocr_from_base64(body.img_base64, lang=body.ocr_lang or "tha+eng")
        if ocr_text:
            candidates = re.split(r"[\r\n,;|/·••]+", ocr_text)
            candidates = [c.strip() for c in candidates if c.strip()]
            filtered = llm_filter_ocr_text(ocr_text) if (LLM_PROVIDER == "openai" and OPENAI_API_KEY) else candidates
            ocr_candidates = filtered or candidates
    if body.ocr_only:
        # return small SSE that contains OCR results and stop
        def g():
            yield f"data: {json.dumps({'ocr_text': ocr_text, 'ocr_candidates': ocr_candidates}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        return StreamingResponse(g(), media_type="text/event-stream")

    drug_names = list(body.drug_name or [])
    if ocr_candidates:
        for c in ocr_candidates:
            if c not in drug_names:
                drug_names.append(c)

    mapped = llm_map_drug_names(drug_names) if (LLM_PROVIDER == "openai" and OPENAI_API_KEY) else drug_names
    try:
        lookup = lookup_drugs(mapped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB lookup error: {e}")

    any_matches = any((lookup.get("matches", {}) or {}).values())
    if not any_matches and drug_names:
        retry_lookup = lookup_drugs(drug_names)
        if any((retry_lookup.get("matches", {}) or {}).values()):
            lookup = retry_lookup

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
    interactions = lookup.get("interactions", []) or []

    system_message, user_message, interactions_count = build_prompt(body.user_id, drug_names, {"matches": lookup.get("matches", {}), "interactions": interactions}, info_by_id)
    generator = stream_llm_openai(system_message, user_message)
    return StreamingResponse(generator, media_type="text/event-stream")

@app.get("/")
def root():
    return {"status": "ok", "note": "DrugBank-LLM API (OCR-enabled)"}

if __name__ == "__main__":
    print("Run this app with uvicorn main:app --host 0.0.0.0 --port 8000")
