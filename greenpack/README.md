# GreenPack EPR Compliance Service

A FastAPI backend for GreenPack Industries to manage 
EPR (Extended Producer Responsibility) compliance.

## Stack Choices
- **FastAPI** — Fast, modern Python API framework
- **Groq (llama-3.3-70b)** — Free, fast LLM for narrative generation
- **ChromaDB** — Local vector store for RAG pipeline
- **HuggingFace Embeddings** — all-MiniLM-L6-v2 (free, no API key)
- **SQLite** — Simple local storage for declarations
- **AI Assistant Used** — Claude (claude.ai) for code structure and debugging

## Setup

pip install -r requirements.txt

**Mac/Linux:**
export GROQ_API_KEY=your_key_here
uvicorn main:app --reload

**Windows PowerShell:**
$env:GROQ_API_KEY="your_key_here"
uvicorn main:app --reload

Then open: http://127.0.0.1:8000/docs

## Endpoints

### 1. POST /submit
Submit monthly plastic declaration.
```bash
curl -X POST http://localhost:8000/submit \
-H "Content-Type: application/json" \
-d '{
  "producer_id": "GREENPACK-001",
  "month": "2026-04",
  "declared_quantities_kg": {
    "rigid_plastic": 12000,
    "flexible_plastic": 8500,
    "multilayer_plastic": 3200
  }
}'
```

### 2. GET /summary/{producer_id}/{month}
Reconcile declaration against ERP data.
```bash
curl http://localhost:8000/summary/GREENPACK-001/2026-04
```

### 3. POST /ask
Ask plain-English EPR compliance questions.
```bash
curl -X POST http://localhost:8000/ask \
-H "Content-Type: application/json" \
-d '{"question": "What is the deadline for monthly declaration?"}'
```

## RAG Corpus Sources
- `epr_guidelines.txt` — CPCB EPR Guidelines 2022 (mock)
- `plastic_waste_rules.txt` — Plastic Waste Management Rules 2016 (mock)
- `epr_faq.txt` — EPR Registration FAQ (mock)

## Trade-off
Chose **ChromaDB local** over Pinecone for zero cost 
and faster local development. For production, Pinecone 
would offer better scalability and persistence.

## What I Would Do Differently
With one more day, I would add authentication (API keys), 
async database operations, and deploy on Railway/Render 
with environment variable management.
