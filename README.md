# AI Hospital Assistant

My final year graduation project — an end-to-end AI-assisted healthcare platform that includes:
- **Hospital UI** for clinicians and staff
- **Company Portal UI** for administrative users
- **Backend API** (FastAPI) that integrates with FHIR services and provides AI/NLP features

> This repo is organized as a multi-service system with Docker-first workflows.

---

## ✨ Key Features

- **FastAPI backend** with authentication, scheduling, chat, and integrations APIs
- **FHIR server integration** (HAPI FHIR)
- **Hospital UI** (Vite + React + Tailwind + ShadCN)
- **Company Portal UI** (Vite + React + Tailwind + ShadCN)
- **GPU-enabled NLP stack** (Transformers + PyTorch)
- **MailHog** for local email testing
- **Docker Compose** for local development

---

## 🧱 Architecture Overview

```
ai-hospital-assistant/
├── company/
│   ├── backend/        # FastAPI backend + NLP
│   └── portal-ui/      # Company admin portal
├── hospital/
│   └── ui/             # Hospital-facing UI
├── docs/
├── tools/
└── README.md
```

**Services**
- **Backend API**: `http://localhost:8000`
- **Hospital UI**: `http://localhost:3000`
- **Portal UI**: `http://localhost:3001`
- **FHIR Server**: `http://localhost:8080/fhir/metadata`
- **MailHog UI**: `http://localhost:8025`

---

## 🛠️ Tech Stack

**Backend**
- FastAPI, Uvicorn
- SQLAlchemy, Alembic
- JWT auth
- PyTorch + Transformers (NLP)

**Frontends**
- Vite + React
- TailwindCSS
- Radix UI / ShadCN
- React Query

**Infra**
- Docker / Docker Compose
- MailHog
- HAPI FHIR

---

## ✅ Prerequisites

- **Docker** + Docker Compose
- **Python 3.13**
- **Node.js 18+** (if running UI locally outside Docker)

## Large Model Files

This repository uses Git LFS to store large NLP model and local wheel files.

Before cloning or pulling the repository, install Git LFS:

```bash
sudo apt update
sudo apt install git-lfs -y
git lfs install
```
---

## 🚀 Quick Start (Docker)

### 1) Clone
```bash
git clone https://github.com/1-Abdulrahman/ai-hospital-assistant.git
cd ai-hospital-assistant
```

### 2) Backend environment
Copy the example file:
```bash
cp company/.env.example company/backend/.env
```

> Edit values inside `company/backend/.env` if needed.

### 3) Create backend venv
```bash
cd company/backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ../..
```

### 4) Start everything (recommended)
```bash
./tools/start_backend_local_with_docker_hospital_portal.sh
```

This will:
- start **FHIR** + **MailHog**
- start **Hospital UI** + **Portal UI**
- run **DB migrations**
- run **FastAPI backend** locally with reload

---

## ⚙️ Optional Flags (startup script)

```bash
./tools/start_backend_local_with_docker_hospital_portal.sh --help
```

Common flags:
- `--seed-db` → seed backend DB
- `--seed-fhir` → seed FHIR records
- `--rebuild-hospital-ui` → rebuild hospital UI image
- `--portal-mock` → start portal UI in mock mode
- `--no-hospital-ui` / `--no-portal-ui`

---

## 🧪 Running Tests

**Backend**
```bash
cd company/backend
source .venv/bin/activate
pytest
```

**Frontend**
```bash
cd company/portal-ui
npm install
npm test
```

---

## 🔑 Environment Variables

Key backend settings are defined in:

```
company/.env.example
```

Important values:

- `HOSPITAL_ORIGIN` (default `http://localhost:3000`)
- `PORTAL_ORIGIN` (default `http://localhost:3001`)
- `DATABASE_URL` (default SQLite local)
- `JWT_SECRET`, `OTP_SECRET`
- `FHIR_BASE_URL`

---

## 🧩 Project Components

### Backend
- `company/backend/app/main.py` → FastAPI app startup
- `app/api/routes/*` → REST endpoints
- `app/modules/*` → core modules (NLP, integrations, FHIR, etc.)
- `app/db/*` → database models & seeding

### Portal UI (Company)
- `company/portal-ui/` — Vite + React app

### Hospital UI
- `hospital/ui/` — Vite + React app

---

## 📖 Docs & Tools

- `docs/` → documentation (offline)
- `tools/` → scripts for dev, CI, and demos

---

## ✅ Roadmap / Future Improvements

- Expanded AI triage workflows
- Expand Continuty of care using additional fhir resources such as episode of care and encounter.
- Implement a second nlp model for generating clarification questions.

---

## 📜 License

Not specified yet.

---

## 👤 Author

**Abdelrahman Amr Farag**  
Final year graduation project

---
