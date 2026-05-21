from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, validator
from typing import Dict
import sqlite3, csv, uuid, os
from datetime import datetime
from groq import Groq
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from dotenv import load_dotenv
load_dotenv() 
app = FastAPI(title="GreenPack EPR Service")

# ── DB Setup ──────────────────────────────────────────────
DB_PATH = "greenpack.db"
CORPUS_DIR = "corpus"
ERP_FILE = "data/erp_data.csv"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS declarations (
            record_id TEXT PRIMARY KEY,
            producer_id TEXT,
            month TEXT,
            rigid_plastic REAL,
            flexible_plastic REAL,
            multilayer_plastic REAL,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ── RAG Setup ─────────────────────────────────────────────
embeddings = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2"
)

def build_vectorstore():
    docs = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500, chunk_overlap=50
    )
    for fname in os.listdir(CORPUS_DIR):
        if fname.endswith(".txt"):
            loader = TextLoader(
                os.path.join(CORPUS_DIR, fname)
            )
            loaded = loader.load()
            chunks = splitter.split_documents(loaded)
            for chunk in chunks:
                chunk.metadata["source"] = fname
            docs.extend(chunks)
    return Chroma.from_documents(docs, embeddings)

vectorstore = build_vectorstore()

# ── Groq Client ───────────────────────────────────────────
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ── Models ────────────────────────────────────────────────
class Declaration(BaseModel):
    producer_id: str
    month: str
    declared_quantities_kg: Dict[str, float]

    @validator("declared_quantities_kg")
    def no_negative(cls, v):
        for k, val in v.items():
            if val < 0:
                raise ValueError(
                    f"{k} cannot be negative"
                )
        return v

    @validator("month")
    def valid_month(cls, v):
        try:
            datetime.strptime(v, "%Y-%m")
        except ValueError:
            raise ValueError(
                "month must be YYYY-MM format"
            )
        return v

class Question(BaseModel):
    question: str

# ── Endpoint 1: POST /submit ──────────────────────────────
@app.post("/submit")
def submit_declaration(data: Declaration):
    required = [
        "rigid_plastic",
        "flexible_plastic",
        "multilayer_plastic"
    ]
    for field in required:
        if field not in data.declared_quantities_kg:
            raise HTTPException(
                400,
                f"Missing required field: {field}"
            )

    record_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().isoformat()
    q = data.declared_quantities_kg

    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        INSERT INTO declarations VALUES
        (?,?,?,?,?,?,?)
    """, (
        record_id,
        data.producer_id,
        data.month,
        q["rigid_plastic"],
        q["flexible_plastic"],
        q["multilayer_plastic"],
        timestamp
    ))
    conn.commit()
    conn.close()

    return {
        "record_id": record_id,
        "producer_id": data.producer_id,
        "month": data.month,
        "declared_quantities_kg": q,
        "timestamp": timestamp,
        "status": "stored"
    }

# ── Endpoint 2: GET /summary ──────────────────────────────
@app.get("/summary/{producer_id}/{month}")
def get_summary(producer_id: str, month: str):
    # Fetch declaration
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""
        SELECT rigid_plastic, flexible_plastic,
               multilayer_plastic
        FROM declarations
        WHERE producer_id=? AND month=?
        ORDER BY timestamp DESC LIMIT 1
    """, (producer_id, month)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(
            404, "Declaration not found"
        )

    declared = {
        "rigid_plastic": row[0],
        "flexible_plastic": row[1],
        "multilayer_plastic": row[2]
    }

    # Read ERP CSV
    erp = {}
    with open(ERP_FILE) as f:
        reader = csv.DictReader(f)
        for r in reader:
            if (r["producer_id"] == producer_id
                    and r["month"] == month):
                erp[r["category"]] = float(
                    r["procured_kg"]
                )

    if not erp:
        raise HTTPException(
            404, "ERP data not found"
        )

    # Reconcile
    reconciliation = {}
    flags = []
    for cat in declared:
        decl = declared[cat]
        proc = erp.get(cat, 0)
        diff = abs(decl - proc)
        pct = (diff / proc * 100) if proc else 100
        flagged = pct > 5
        reconciliation[cat] = {
            "declared_kg": decl,
            "procured_kg": proc,
            "difference_kg": round(decl - proc, 2),
            "variance_pct": round(pct, 2),
            "flagged": flagged
        }
        if flagged:
            flags.append(
                f"{cat}: declared {decl}kg vs "
                f"procured {proc}kg "
                f"({round(pct,1)}% variance)"
            )

    # LLM Summary
    flag_text = (
        "\n".join(flags) if flags
        else "No significant discrepancies found."
    )
    prompt = f"""
You are a compliance assistant for GreenPack Industries.
Based on the reconciliation below, write a 3-5 sentence 
plain-English summary explaining any discrepancies and 
recommending actions.

Producer: {producer_id}
Month: {month}
Discrepancies:
{flag_text}

Be concise and professional.
"""
    # Used to "llama-3.3-70b-versatile"
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    narrative = response.choices[0].message.content

    return {
        "producer_id": producer_id,
        "month": month,
        "reconciliation": reconciliation,
        "narrative_summary": narrative
    }

# ── Endpoint 3: POST /ask ─────────────────────────────────
@app.post("/ask")
def ask_question(body: Question):
    docs = vectorstore.similarity_search(
        body.question, k=3
    )

    if not docs:
        return {
            "answer": (
                "I do not know based on the "
                "provided documents"
            ),
            "citations": []
        }

    context = "\n\n".join(
        [f"[{d.metadata['source']}]\n{d.page_content}"
         for d in docs]
    )

    prompt = f"""
Answer the question using ONLY the documents below.
If the answer is not in the documents, say exactly:
"I do not know based on the provided documents"

Documents:
{context}

Question: {body.question}

Provide a clear answer and cite the document name.
"""
    # Used to "llama-3.3-70b-versatile"
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    answer = response.choices[0].message.content

    citations = list(set([
        d.metadata["source"] for d in docs
    ]))

    return {
        "answer": answer,
        "citations": citations
    }