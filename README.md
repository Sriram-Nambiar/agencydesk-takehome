# AgencyDesk

A small multi-tenant agency and client workspace built with React, FastAPI, and PostgreSQL.

## Run locally

Requirements: Docker Desktop, Node.js 20+, and Python 3.10+.

1. Start PostgreSQL and Redis: `docker compose up -d`
2. Start the API in one terminal:
   ```powershell
   cd backend
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
3. Seed the sample agencies, workflows, and demo data: `cd backend; python seed.py`
4. Start the UI: `cd frontend; npm install; npm run dev`
5. Open the Vite URL. Sample logins use password `password123`:
   - `alex@example.com` (Agency Admin / Beta Client User)
   - `sarah@acme.com` (Agency Staff Member)
   - `john@starlight.com` (Client Portal User)

For a fresh database and redis state after schema changes, run `docker compose down -v` and then `docker compose up -d` before seeding.

For an existing database created from the original assignment schema, apply `backend/migrations/001_tenant_boundaries.sql` once with `psql` before starting the updated API.

## Security check

With the API running and the sample data loaded, run `python backend/security_checks.py`. It checks tenant switching, project membership, client isolation, and internal task/comment/file filtering through the HTTP API. It exits nonzero on the first failed assertion.

See [DESIGN.md](DESIGN.md) for the isolation model and edge-case decisions. Run `pytest` inside `backend/` to execute the full automated test suite covering all endpoints, permissions, and tenant boundary shields.

Optional API settings: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_PORT`, `SECRET_KEY`, and comma-separated `CORS_ORIGINS`. Set a long random `SECRET_KEY` before deployment; the fallback key is for local development only.
