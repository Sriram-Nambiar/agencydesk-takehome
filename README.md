# AgencyDesk

[![CI](https://github.com/Sriram-Nambiar/agencydesk-takehome/actions/workflows/ci.yml/badge.svg)](https://github.com/Sriram-Nambiar/agencydesk-takehome/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-1.0-009688?logo=fastapi)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript)

> A multi-tenant client & project management platform purpose-built for agency-client collaboration with strict data isolation, client leak-shield boundaries, and Redis-powered workflow automations.

---

## Tech Stack

- **Frontend:** React 19, TypeScript, Vite, Vitest, Testing Library
- **Backend:** Python 3.11, FastAPI, Pydantic v2, `psycopg2-binary`, `python-jose`
- **Database & Cache:** PostgreSQL 16, Redis 7

---

## Getting Started

You can run the complete app with Docker, or run its services natively.

### Prerequisites

| Requirement | Version | Required For |
| :--- | :--- | :--- |
| **Docker Desktop** | Latest | Complete app with one command |
| **Node.js** | 20+ | Native frontend development and testing |
| **Python** | 3.10+ | Native backend development and testing |
| **Local PostgreSQL** | 15+ | Native database setup |
| **Local Redis** | 6+ | Native cache and event setup |

---

### Start the complete app with Docker

From the repository root, run:

```bash
docker compose up --build
```

This builds and starts the React frontend, FastAPI backend, PostgreSQL, and Redis. On the first start, PostgreSQL loads `backend/schema.sql` and the backend adds the demo data automatically.

Open **http://localhost:5173**. The API is available at **http://localhost:8000**, including interactive docs at **http://localhost:8000/docs**.

To run the stack in the background, append `-d`:

```bash
docker compose up --build -d
```

To stop it:

```bash
docker compose down
```

To reset all local Docker data and recreate the demo data, run:

```bash
docker compose down -v
docker compose up --build
```

> [!NOTE]
> `docker compose up` preserves existing database and upload volumes. The demo seed runs only when the database is empty.

---

### Starting without Docker

Use this option if you prefer running native PostgreSQL and Redis installations on your host machine.

#### 1. Ensure Local PostgreSQL & Redis are Running

Make sure PostgreSQL is running on port `5432` and Redis is running on port `6379`.

**macOS (via Homebrew):**
```bash
brew services start postgresql@16
brew services start redis
```

**Ubuntu / Debian:**
```bash
sudo systemctl start postgresql
sudo systemctl start redis-server
```

**Windows:**
Start PostgreSQL and Redis services via the Windows Services Manager or native installer.

#### 2. Create the Database & Initialize Schema

Create the `agencydesk` database and execute `schema.sql`:

```bash
# Create database (if not exists)
createdb -U postgres agencydesk

# Run initial schema
psql -U postgres -d agencydesk -f backend/schema.sql
```

*(If prompted for password, enter your local PostgreSQL password).*

#### 3. Configure Backend Environment

Copy the example environment file and customize your database/redis credentials if they differ from the defaults:

```bash
cd backend
cp .env.example .env
```

Default `.env` configuration:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=agencydesk
DB_USER=postgres
DB_PASS=devpass
REDIS_HOST=localhost
REDIS_PORT=6379
SECRET_KEY=dev-only-change-me-before-deploying-long-random-string
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

#### 4. Install Dependencies & Seed Demo Data

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
python -m uvicorn main:app --reload --port 8000
```

**macOS / Linux (Bash):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
python -m uvicorn main:app --reload --port 8000
```

#### 5. Start Frontend App

```bash
cd ../frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Demo Test Accounts

The seed script creates two agencies (`Acme Digital Agency` and `Beta Media Group`) and accounts demonstrating multi-tenancy and role-based permissions.

**Default Password for all accounts:** `password123`

| User | Email | Role | Agency | Access Scope |
| :--- | :--- | :--- | :--- | :--- |
| **Alex Rivera** | `alex@example.com` | `agency_admin` | Acme Digital Agency | Full administrative control, all projects, billing time, staff directory, automations |
| | | `client_user` | Beta Media Group | Demonstrates **"One person, two agencies"**: switching agency context makes Alex a client user scoped only to Nike Retail |
| **Sarah Chen** | `sarah@acme.com` | `agency_member` | Acme Digital Agency | Staff member: sees only assigned projects (`Website Redesign`), logs time, creates tasks |
| **John Starlight**| `john@starlight.com` | `client_user` | Acme Digital Agency | Client user for Starlight Tech: strictly sees client-visible deliverables, cannot see internal tasks, staff notes, or time entries |

*(Use the **Quick Demo** switcher buttons in the app header to switch between accounts instantly).*

---

## Verifying & Testing

### 1. Security & Leak-Shield Smoke Script

Validates tenant isolation, permission boundaries, and leak-shield rules through the HTTP API:

```bash
python backend/security_checks.py
```
*(Runs 24 automated assertion checks covering cross-tenant data access, member removal, and invite deduplication).*

### 2. Backend Automated Test Suite (Pytest)

Executes the backend integration suite against a dedicated `agencydesk_test` database, verifying API endpoints, schemas, tenant constraints, and workflow behavior. The test fixture refuses to run against a database whose name does not end in `_test`.

Create the test database once if needed:

```bash
docker compose exec postgres psql -U postgres -d postgres -c "CREATE DATABASE agencydesk_test;"
```

Then run:

```bash
cd backend
pytest -v tests/
```

### 3. Frontend Unit & Component Tests (Vitest)

Executes 13 tests covering React components, role badges, tenant switching, and leak-shield UI assertions:

```bash
cd frontend
npm test
```

### 4. Production Build

Compiles TypeScript and bundles production assets:

```bash
cd frontend
npm run build
```

---

## API Health & Observability Endpoints

- **Liveness Probe:** `GET http://localhost:8000/healthz` (returns application process state)
- **Readiness Probe:** `GET http://localhost:8000/readyz` (validates live PostgreSQL & Redis connections)
- **Interactive OpenAPI Documentation:** `GET http://localhost:8000/docs` (interactive Swagger UI)

---

## Architecture & Edge Cases Write-Up

For details on schema-level foreign key isolation, client leak-shield mechanics, identity modeling across multiple agencies, and Redis event bus architecture, see **[DESIGN.md](DESIGN.md)**.
