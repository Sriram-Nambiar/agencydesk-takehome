# AgencyDesk

> A multi-tenant client & project management platform purpose-built for agency-client collaboration with strict data isolation, client leak-shield boundaries, and Redis-powered workflow automations.

---

## Tech Stack

- **Frontend:** React 19, TypeScript, Vite, Vitest, Testing Library
- **Backend:** Python 3.11, FastAPI, Pydantic v2, `psycopg2-binary`, `python-jose`
- **Database & Cache:** PostgreSQL 16, Redis 7

---

## Getting Started

You can run AgencyDesk locally either **with Docker** (fastest, manages database and Redis for you) or **without Docker** (running services natively).

### Prerequisites

| Requirement | Version | Required For |
| :--- | :--- | :--- |
| **Node.js** | 20+ | Frontend development and testing |
| **Python** | 3.10+ | Backend API, migrations, and test runner |
| **Docker Desktop** | Latest | *Option 1 only* (PostgreSQL & Redis containers) |
| **Local PostgreSQL** | 15+ | *Option 2 only* (Native database) |
| **Local Redis** | 6+ | *Option 2 only* (Native event bus & caching) |

---

### Option 1: Starting with Docker (Recommended)

Docker Compose automatically spins up PostgreSQL (with schema pre-loaded) and Redis on standard ports.

#### 1. Start Database & Redis Services

```bash
docker compose up -d
```
*This starts:*
- **PostgreSQL 16** on `localhost:5432` (database: `agencydesk`, user: `postgres`, password: `devpass`)
- **Redis 7** on `localhost:6379`
- Schema is automatically initialized from `backend/schema.sql` on first boot.

#### 2. Start the Backend API

In a new terminal:

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python seed.py
python -m uvicorn main:app --reload --port 8000
```

**macOS / Linux (Bash):**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python seed.py
python -m uvicorn main:app --reload --port 8000
```

#### 3. Start the Frontend App

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

> [!TIP]
> **Need a clean slate?** Run `docker compose down -v && docker compose up -d` to clear database volumes, then rerun `python backend/seed.py`.

---

### Option 2: Starting without Docker (Native Local Services)

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

Executes 91 tests verifying API endpoints, Pydantic schemas, database foreign key constraints, and Redis event automations:

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
