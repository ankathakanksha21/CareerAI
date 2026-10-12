# UK Career Navigator

A career agent for international students and recent graduates looking for work in the UK. It turns their own experience into UK-standard CVs and interview practice, and tracks applications to show what is and is not working.

- **Scope, architecture, decisions and how to run it:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Specs and plans for each build step:** `docs/superpowers/`
- **The retired demo's documents:** `docs/archive/`

Stack: React + Vite, Python FastAPI, Supabase (login and Postgres), AWS Bedrock, ElevenLabs.

Quick start, once `backend/.env` is filled in from `backend/.env.example`:

```
cd backend && .venv\Scripts\python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

Then open http://localhost:5173. First-time setup is in section 12 of the architecture document.
