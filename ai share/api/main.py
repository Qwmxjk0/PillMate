from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import pymysql
import openai
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()  # allow .env values inside container if mounted

app = FastAPI(title="DrugBank-LLM API")

# Config
DB_HOST = os.getenv("DB_HOST", "db")
DB_PORT = int(os.getenv("DB_PORT", 3306))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "DrugBank")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if LLM_PROVIDER == "openai" and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# Request/Response models
class QueryBody(BaseModel):
    user_id: int
    drug_name: List[str]

class LLMResult(BaseModel):
    prompt: str
    llm_response: str

# DB helper (simple poolless)
def get_db_connection():
    conn = pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        local_infile=1,
    )
    return conn

# Lookup drugs and interactions
def lookup_drugs(drug_names: List[str]) -> Dict[str, Any]:
    qnames = [dn.strip() for dn in drug_names if dn and dn.strip()]
    if not qnames:
        return {}

    ids = set()
    matches = {}
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for q in qnames:
                likeq = f"%{q}%"
                cur.execute(
                    "SELECT drugbank_id, name, description FROM drugs WHERE name LIKE %s LIMIT 20;",
                    (likeq,)
                )
                rows = cur.fetchall()
                matches[q] = {"by_name": rows, "by_synonym": []}
                for r in rows:
                    ids.add(r["drugbank_id"])
            for q in qnames:
                likeq = f"%{q}%"
                cur.execute(
                    "SELECT s.drugbank_id, s.synonym, d.name FROM synonyms s LEFT JOIN drugs d ON s.drugbank_id=d.drugbank_id WHERE s.synonym LIKE %s LIMIT 20;",
                    (likeq,)
                )
                rows = cur.fetchall()
                matches[q]["by_synonym"] = rows
                for r in rows:
                    ids.add(r["drugbank_id"])

            interactions = []
            if ids:
                id_list = list(ids)
                placeholders = ",".join(["%s"] * len(id_list))
                sql = f"""
                    SELECT di.drugbank_id, di.interacts_with_drugbank_id, di.interacts_with_name, di.description
                    FROM drug_interactions di
                    WHERE di.drugbank_id IN ({placeholders})
                    AND di.interacts_with_drugbank_id IN ({placeholders});
                """
                params = id_list + id_list
                cur.execute(sql, params)
                interactions = cur.fetchall()
            else:
                interactions = []

    return {"matches": matches, "interactions": interactions}

# Build prompt for LLM (safe: sanitize before f-strings)
def build_prompt(user_id: int, drug_names: List[str], lookup_result: Dict[str, Any]) -> str:
    lines = []
    lines.append(f"User ID: {user_id}")
    lines.append("")
    lines.append("Query drug names:")
    for q in drug_names:
        lines.append(f"- {q}")
    lines.append("")
    lines.append("Matched drugs (from DrugBank):")
    for q, info in lookup_result.get("matches", {}).items():
        lines.append(f"Query: {q}")
        if info.get("by_name"):
            for r in info["by_name"]:
                desc_raw = r.get("description") or ""
                desc_s = desc_raw.replace("\\n", " ")[:200]
                lines.append(f"  - ID: {r.get('drugbank_id')} | Name: {r.get('name')} | Desc: {desc_s}")
        if info.get("by_synonym"):
            for r in info["by_synonym"]:
                syn = r.get("synonym") or ""
                can = r.get("name") or ""
                lines.append(f"  - Synonym match: ID: {r.get('drugbank_id')} | Synonym: {syn} | Canonical: {can}")
        lines.append("")

    interactions = lookup_result.get("interactions", [])
    lines.append(f"Found {len(interactions)} interaction records:")
    for it in interactions[:200]:
        desc_raw = it.get("description") or ""
        desc_s = desc_raw.replace("\\n", " ")[:400]
        lines.append(
            f"- {it.get('drugbank_id')}  <->  {it.get('interacts_with_drugbank_id')}  "
            f"| name: {it.get('interacts_with_name')}  | desc: {desc_s}"
        )

    lines.append(""" 
        Task for LLM:
        กรุณาตอบกลับเป็น **ภาษาไทย** เท่านั้น  
        รูปแบบคำตอบ: **Markdown**  

        ข้อกำหนด:
        1. สรุปปฏิกิริยาระหว่างยาที่พบจากข้อมูลด้านบน (drug-drug interactions)  
        2. เน้นข้อห้ามใช้ (contraindications), คำเตือนร้ายแรง หรือคำเตือนแบบ black box ที่พบ **เฉพาะจากข้อมูลที่ให้ไว้**  
        3. หากไม่พบข้อมูล ให้ระบุว่า “ไม่พบข้อมูลการโต้ตอบระหว่างยาจากฐานข้อมูล”  
        4. ห้ามเดาหรือเติมข้อมูลนอกเหนือจากที่ feed เข้ามา  
        5. จัดข้อความให้อ่านง่ายด้วย Markdown (ใช้หัวข้อ, bullet points, หรือ emphasis ได้)
        6. ใช้ภาษาที่ชาวบ้าน คนแก่คนที่ไม่มีความรู้เรื่องยาสามารถเข้าใจได้
        7. สรุปโดยไม่ใช้ประโยคพลิกกลับ แต่ความหมายเหมือนเดิม
        8. กล่าวถึงแค่ยาใน List Query drug names นอกนั้นไม่ต้องพูดถึง
        จำกัดคำตอบ: 2-4 ย่อหน้า สั้น กระชับ 
        """)

    return "\\n".join(lines)

# Call LLM (OpenAI ChatCompletion example)
def call_llm_openai(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured in environment.")
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=800,
            temperature=0.2,
        )
        # compatibility: some SDKs return different attrs
        text = None
        if hasattr(resp.choices[0].message, 'content'):
            text = resp.choices[0].message.content
        else:
            text = resp.choices[0].text if hasattr(resp.choices[0], 'text') else str(resp)
        return text
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")

@app.post("/analyze", response_model=LLMResult)
def analyze(body: QueryBody):
    try:
        lookup = lookup_drugs(body.drug_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB lookup error: {e}")

    prompt = build_prompt(body.user_id, body.drug_name, lookup)

    if LLM_PROVIDER == "openai":
        try:
            llm_text = call_llm_openai(prompt)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"LLM error: {e}")
    else:
        raise HTTPException(status_code=501, detail="Only openai LLM_PROVIDER implemented in this template.")

    return {"prompt": prompt, "llm_response": llm_text}