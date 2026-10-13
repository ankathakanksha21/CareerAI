# UK Career Navigator

A career agent for international students and recent graduates looking for work in the UK. It builds a profile from a voice call, an uploaded CV, pasted text or GitHub projects, turns that experience into UK-standard CVs and interview practice, finds current jobs and compares them with it, and tracks applications to show what is and is not working.

- **Scope, architecture, decisions and how to run it:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Specs and plans for each build step:** `docs/superpowers/`
- **The retired demo's documents:** `docs/archive/`

Stack: React + Vite, Python FastAPI, Supabase (login and Postgres), AWS Bedrock, ElevenLabs, Reed (job adverts), gov.uk (sponsor register), GitHub (public repositories).

Quick start, once `backend/.env` is filled in from `backend/.env.example`:

```
cd backend && .venv\Scripts\python -m uvicorn main:app --reload --port 8000
cd frontend && npm run dev
```

Then open http://localhost:5173. First-time setup is in section 12 of the architecture document.
