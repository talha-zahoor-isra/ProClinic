# TalMedix — Healthcare Management System

> **A full-stack Hospital Management System** built with Django 6, Django REST Framework, and WeasyPrint. Designed for Indian clinics and hospitals, TalMedix covers patient registration, appointment scheduling, electronic health records (EHR), prescriptions, billing, lab reports, research publication management, and a fully automated audit trail.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Key Features](#key-features)
3. [Technology Stack](#technology-stack)
4. [System Architecture](#system-architecture)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Installation Guide](#installation-guide)
8. [Environment Configuration](#environment-configuration)
9. [Database Setup and Migrations](#database-setup-and-migrations)
10. [Running the Application](#running-the-application)
11. [Development Workflow](#development-workflow)
12. [Build Instructions](#build-instructions)
13. [Testing Strategy and Commands](#testing-strategy-and-commands)
14. [API Overview and Endpoints](#api-overview-and-endpoints)
15. [Authentication and Authorization](#authentication-and-authorization)
16. [Configuration Reference](#configuration-reference)
17. [Deployment Instructions](#deployment-instructions)
18. [Security Considerations](#security-considerations)
19. [Performance Notes](#performance-notes)
20. [Monitoring and Logging](#monitoring-and-logging)
21. [Management Commands](#management-commands)
22. [Troubleshooting](#troubleshooting)
23. [Contributing Guidelines](#contributing-guidelines)
24. [License Information](#license-information)

---

## Executive Summary

TalMedix is a monolithic Django application structured around eight self-contained Django apps. It provides two distinct portal experiences: a **staff portal** (admin, doctors, receptionists, pharmacists, accountants) served through server-rendered HTML templates, and a **patient portal** accessed both through session-based HTML pages and a JWT-authenticated REST API under `/api/patient/`.

The system was designed for deployment on [Render](https://render.com/)'s free tier with PostgreSQL and Cloudinary for media storage, but runs equally well locally with SQLite and the filesystem. Every write operation on key clinical entities is automatically captured in an immutable `AuditLog` via Django signals—no additional instrumentation is required.

---

## Key Features

### Clinical Operations
- **Patient Registration** — Staff or patients self-register with full demographic and medical data (blood group, allergies, DOB)
- **Appointment Scheduling** — Book, reschedule, cancel; double-booking prevention; doctor unavailability blocks; automatic no-show marking via management command
- **Electronic Health Records (EHR)** — `Visit` records link appointments to clinical notes and diagnosis
- **Prescription Management** — Doctors create multi-item prescriptions tied to a visit; pharmacists manage a dispense queue; PDF export via WeasyPrint
- **Lab Reports** — Upload/download PDF lab reports (max 5 MB); staff verify or archive; email notifications to treating doctors on upload
- **Billing & Invoicing** — Itemised invoices (consultation, medicine, lab, procedure, other); automatic draft invoice generated when an appointment is marked COMPLETED; GST calculation; PDF download; email notifications on draft and payment
- **Medicine Catalogue** — `MedicineMaster` for standard pricing; auto-populated from prescriptions into draft invoices

### Research Module
- Doctors submit research papers (PDF + abstract + authors)
- Admin review queue: approve → paper becomes publicly visible; reject → rejection reason shown to doctor
- Public listing at `/publications/` and `/api/publications/public-list/` (no auth required)

### AI Health Assistant
- Patient-exclusive feature powered by **Google Gemini 2.5 Flash**
- Structured, safe health information responses with emergency escalation logic
- Enforced 1000-character question limit; quota-aware error handling

### Administration
- Role-based dashboard with context-specific KPIs for each role
- Full CRUD user management (create / deactivate / reactivate staff accounts)
- Complete audit trail (CREATE / UPDATE / DELETE / LOGIN) with before/after diffs
- Django admin integration for all models

### Developer & Infrastructure
- Dual authentication: Django session auth (browser) + JWT (API clients)
- Argon2 password hashing
- Docker + Docker Compose for local development
- One-click Render Blueprint deployment (`render.yaml`)
- WhiteNoise for static file serving in production
- Cloudinary for media uploads in production (falls back to local filesystem)

---

## Technology Stack

| Category | Technology | Version |
|---|---|---|
| Web framework | Django | 6.0.1 |
| REST API | Django REST Framework | 3.16.1 |
| JWT auth | djangorestframework-simplejwt | 5.5.1 |
| Database (dev) | SQLite | bundled |
| Database (prod) | PostgreSQL | 16 (Alpine) |
| Cache/queue | Redis | 7 (Alpine, Docker only) |
| PDF generation | WeasyPrint | 68.1 |
| Media storage | Cloudinary | 1.44.0 |
| Static files | WhiteNoise | 6.12.0 |
| Password hashing | argon2-cffi | 25.1.0 |
| Filtering | django-filter | 25.2 |
| CORS | django-cors-headers | 4.9.0 |
| Image processing | Pillow | 12.2.0 |
| Env management | django-environ | 0.12.0 |
| AI assistant | google-generativeai | 0.8.3 |
| WSGI server | Gunicorn | 25.3.0 |
| Language | Python | 3.12 |

---

## System Architecture

TalMedix is a **monolithic Django application** with a layered architecture:

```
┌────────────────────────────────────────────────────────────────────────┐
│                            Client Layer                                │
│                                                                        │
│   ┌──────────────────┐              ┌──────────────────────────────┐   │
│   │  Web Browser     │              │  API Client (mobile / curl)  │   │
│   │  HTML/CSS/JS     │              │  JSON + JWT Bearer token     │   │
│   └────────┬─────────┘              └──────────────┬───────────────┘   │
└────────────┼───────────────────────────────────────┼───────────────────┘
             │ HTTP                                  │ HTTP
             ▼                                       ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        Django Application                              │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │               WSGI / Gunicorn (production)                       │  │
│  └─────────────────────────┬────────────────────────────────────────┘  │
│                            │                                           │
│  ┌─────────────────────────▼────────────────────────────────────────┐  │
│  │               URL Router  (core/urls.py)                         │  │
│  └───┬────────────────────────────┬──────────────────────┬──────────┘  │
│      │ /api/*                     │ /accounts/*          │ /*          │
│      ▼                            ▼                      ▼             │
│  ┌─────────┐   ┌──────────────────────────┐  ┌───────────────────┐     │
│  │ DRF     │   │ Authentication Views     │  │ App Views         │     │
│  │ViewSets │   │ (login/logout/signup/OTP)│  │ (HTML templates)  │     │
│  └────┬────┘   └──────────────────────────┘  └─────────┬─────────┘     │
│       │                                                │               │
│  ┌────▼────────────────────────────────────────────────▼────────────┐  │
│  │          Business Logic (Models + Managers + Services)           │  │
│  │                                                                  │  │
│  │  accounts  patients  appointments  prescriptions  billing        │  │
│  │  publications  audit                                             │  │
│  └───────────────────────────┬──────────────────────────────────────┘  │
│                              │ Django Signals (pre_save / post_save    │
│                              │                / post_delete)           │
│  ┌───────────────────────────▼──────────────────────────────────────┐  │
│  │          Audit App  (audit/signals.py + middleware)              │  │
│  │   Captures CREATE / UPDATE / DELETE for all key entities         │  │
│  │   Actor resolved via AuditUserMiddleware → threading.local       │  │
│  └───────────────────────────┬──────────────────────────────────────┘  │
└──────────────────────────────┼─────────────────────────────────────────┘
                               │ Django ORM
                   ┌───────────▼───────────┐
                   │  Database             │
                   │  SQLite (dev)         │
                   │  PostgreSQL 16 (prod) │
                   └───────────────────────┘
```

### Django App Responsibilities

| App | Responsibility |
|---|---|
| `core` | Project settings, root URL config, base views (dashboard router, home, design system), WSGI/ASGI |
| `accounts` | `CustomUser` model (role-aware), dual login/logout views, patient signup, OTP-based password reset |
| `patients` | `Patient`, `Visit`, `LabReport` models; staff CRUD views; patient self-service; AI Ask endpoint |
| `appointments` | `Appointment`, `DoctorUnavailability`; booking/cancel/reschedule logic; slot availability API |
| `prescriptions` | `Prescription`, `PrescriptionItem`; WeasyPrint PDF export; pharmacist dispense queue |
| `billing` | `Invoice`, `InvoiceItem`, `MedicineMaster`; auto-draft signal; PDF generation; email notifications |
| `publications` | Research paper submission → admin approval workflow → public listing |
| `audit` | `AuditLog` model; Django signals for all tracked entities; `AuditUserMiddleware` |
| `api` | DRF ViewSets, serializers, filters, pagination classes, JWT auth endpoints, patient-facing REST API |

### Automatic Draft Invoice Signal

When an `Appointment` transitions to `COMPLETED`, a `post_save` signal in `billing/signals.py` automatically generates a **DRAFT invoice** pre-populated with:
- A consultation line item (priced from `settings.CONSULTATION_FEE`)
- Medicine line items sourced from any `Prescription` linked via the `Visit` record (priced from `MedicineMaster`)

---

## Project Structure

```
TalMedix/
├── backend/                          # Django project root
│   ├── core/                         # Project settings, root URLs, base views, utils
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── views.py                  # Dashboard router + prototype views
│   │   ├── utils.py                  # Email notification utilities
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── accounts/                     # User model + authentication
│   │   ├── models.py                 # CustomUser, PatientOTP
│   │   ├── views.py                  # Login, signup, OTP password reset
│   │   └── urls.py
│   ├── patients/                     # Patient records + EHR
│   │   ├── models.py                 # Patient, Visit, LabReport
│   │   ├── views.py                  # CRUD + self-service + AI Ask
│   │   └── urls.py
│   ├── appointments/                 # Appointment scheduling
│   │   ├── models.py                 # Appointment, DoctorUnavailability
│   │   ├── services.py               # auto_mark_noshow()
│   │   ├── management/commands/
│   │   │   └── mark_noshow.py        # CLI: auto no-show marking
│   │   └── urls.py
│   ├── prescriptions/                # Prescription management
│   │   ├── models.py                 # Prescription, PrescriptionItem
│   │   ├── utils.py                  # WeasyPrint PDF generation
│   │   └── urls.py
│   ├── billing/                      # Invoice and payment
│   │   ├── models.py                 # Invoice, InvoiceItem, MedicineMaster
│   │   ├── signals.py                # Auto-draft invoice on appointment COMPLETED
│   │   ├── utils.py                  # Invoice PDF + email notifications
│   │   └── urls.py
│   ├── publications/                 # Research paper workflow
│   │   ├── models.py                 # Publication (DRAFT→PENDING→APPROVED/REJECTED)
│   │   └── urls.py
│   ├── audit/                        # Immutable audit trail
│   │   ├── models.py                 # AuditLog
│   │   ├── signals.py                # pre_save / post_save / post_delete hooks
│   │   ├── middleware.py             # AuditUserMiddleware (thread-local actor)
│   │   └── urls.py
│   ├── api/                          # DRF REST API
│   │   ├── urls.py                   # Staff router + JWT token endpoints
│   │   ├── patient_urls.py           # Patient-facing REST endpoints
│   │   ├── views.py                  # Staff ViewSets
│   │   ├── patient_views.py          # Patient API views
│   │   ├── serializers.py            # Staff serializers
│   │   ├── patient_serializers.py    # Patient-facing serializers
│   │   ├── filters.py                # django-filter FilterSets
│   │   ├── pagination.py             # StandardResultsSetPagination (20), LargeResultsSetPagination (50)
│   │   ├── permissions.py            # IsStaff, IsPatient, IsDoctor, IsAdminRole
│   │   ├── tests.py                  # Patient API test suite
│   │   └── tests_extended.py         # Extended staff API + signal tests
│   ├── manage.py
│   ├── create_admin.py               # Upserts admin superuser on deploy
│   └── .env                          # Local environment variables (not committed)
├── frontend/
│   ├── templates/                    # Django HTML templates (role-aware dashboards)
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── accounts/
│   │   ├── appointments/
│   │   ├── billing/
│   │   ├── patients/
│   │   ├── prescriptions/
│   │   ├── publications/
│   │   ├── audit/
│   │   ├── dashboards/               # Per-role dashboard partials
│   │   ├── layouts/
│   │   ├── components/
│   │   └── prototype/                # Design system + A4 PDF templates
│   ├── static/                       # CSS, JS, images
│   └── media/                        # Local media uploads (dev only)
├── docs/
│   ├── api.md                        # API reference documentation
│   ├── architecture.md               # Architecture overview
│   ├── models.md                     # Data model reference
│   ├── workflow.md                   # User journey workflows
│   ├── proclinic_design_handoff.md   # UI/UX design handoff
│   ├── PRD.pdf                       # Product Requirements Document
│   ├── TalMedixSRS.pdf              # Software Requirements Specification
│   └── TalMedix_DFD.pdf             # Data Flow Diagram
├── Dockerfile                        # Production container (python:3.12-slim)
├── docker-compose.yml                # Local dev: Django + PostgreSQL 16 + Redis 7
├── render.yaml                       # Render Blueprint (one-click deployment)
├── build.sh                          # Render build script (pip install + collectstatic)
└── requirements.txt                  # Pinned Python dependencies
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.12+ | 3.12.3 used in production |
| pip | latest | `pip install --upgrade pip` |
| Git | any | |
| **For local dev (SQLite)** | — | No additional database required |
| **For Docker dev** | Docker + Docker Compose v2 | PostgreSQL 16 + Redis 7 |
| **For PDF generation** | System libraries | See WeasyPrint dependencies below |
| **For production** | PostgreSQL 16 | Via `DATABASE_URL` |
| **For media uploads (prod)** | Cloudinary account | Free tier sufficient |
| **For AI assistant** | Google AI Studio API key | `GEMINI_API_KEY` |
| **For email** | Gmail account with App Password | SMTP |

### WeasyPrint System Dependencies

WeasyPrint requires Pango, Cairo, and GDK-Pixbuf. Install them before running:

**Debian/Ubuntu:**
```bash
sudo apt-get install -y \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
  libfontconfig1 libgdk-pixbuf-2.0-0 libcairo2 \
  shared-mime-info libjpeg62-turbo-dev zlib1g-dev \
  libpq-dev gcc g++
```

**macOS (Homebrew):**
```bash
brew install pango cairo gdk-pixbuf libffi
```

---

## Installation Guide

### Option 1 — Local Development (SQLite, recommended for first run)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/TalMedix.git
cd TalMedix

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Configure environment variables
cp backend/.env backend/.env.local    # or edit backend/.env directly
# See Environment Configuration section for required values

# 5. Run database migrations
cd backend
python manage.py migrate

# 6. Create the initial admin superuser
python manage.py createsuperuser
# OR use the provided bootstrap script:
python create_admin.py             # creates username=admin, password=Admin@12345

# 7. Collect static files (required for the admin interface)
python manage.py collectstatic --no-input

# 8. Start the development server
python manage.py runserver
```

The application is now available at **http://127.0.0.1:8000/**

### Option 2 — Docker Compose (PostgreSQL + Redis)

```bash
# 1. Clone and enter the repository
git clone https://github.com/your-org/TalMedix.git
cd TalMedix

# 2. Copy and customise the environment file
#    The docker-compose.yml has defaults for local use, but you can override
cp backend/.env backend/.env.docker   # optional; compose uses its own env block

# 3. Build and start all services
docker compose up --build

# 4. In a second terminal, run migrations
docker compose exec web python backend/manage.py migrate

# 5. Create the admin user
docker compose exec web python backend/create_admin.py
```

Services exposed:
- **Django** → http://localhost:8000
- **PostgreSQL** → localhost:5432
- **Redis** → localhost:6379

---

## Environment Configuration

TalMedix reads all configuration from a `.env` file located at `backend/.env`. Create this file before running for the first time.

### Minimal `.env` for local development

```env
DEBUG=True
SECRET_KEY=django-insecure-replace-this-with-a-random-string
ALLOWED_HOSTS=127.0.0.1,localhost
CONSULTATION_FEE=500.00
GST_RATE=0.18
```

### Complete Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | ✅ | — | Django secret key. Generate with `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DEBUG` | ✅ | `False` | `True` for development; must be `False` in production |
| `ALLOWED_HOSTS` | ✅ | — | Comma-separated hostnames (e.g. `127.0.0.1,localhost`) |
| `DATABASE_URL` | ❌ | SQLite | Full PostgreSQL URL: `postgres://user:pass@host:5432/dbname`. If omitted, SQLite is used |
| `CLOUDINARY_CLOUD_NAME` | ❌ | — | Cloudinary cloud name. Required for media in production |
| `CLOUDINARY_API_KEY` | ❌ | — | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | ❌ | — | Cloudinary API secret |
| `CONSULTATION_FEE` | ❌ | `500.00` | Default consultation fee in invoice auto-generation (₹) |
| `GST_RATE` | ❌ | `0.18` | GST rate applied to invoices (18% = `0.18`) |
| `GEMINI_API_KEY` | ❌ | — | Google AI Studio API key for the patient AI health assistant |
| `GMAIL_USER` | ❌ | — | Gmail address for SMTP email notifications |
| `GMAIL_PASS` | ❌ | — | Gmail App Password (not the account password) |
| `REDIS_URL` | ❌ | — | Redis URL (used in Docker Compose: `redis://redis:6379/0`) |
| `RENDER` | ❌ | — | Set to `true` on Render to enable IS_RENDER flag and media URL handling |
| `SECURE_SSL_REDIRECT` | ❌ | `False` | Set `True` in production; redirects all HTTP to HTTPS |
| `SESSION_COOKIE_SECURE` | ❌ | `False` | Set `True` in production |
| `CSRF_COOKIE_SECURE` | ❌ | `False` | Set `True` in production |
| `CSRF_TRUSTED_ORIGINS` | ❌ | `https://*.onrender.com` | Additional trusted origins for CSRF |
| `SECURE_HSTS_SECONDS` | ❌ | `0` | Set `31536000` (1 year) in production |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | ❌ | `False` | Set `True` in production |
| `SECURE_HSTS_PRELOAD` | ❌ | `False` | Set `True` in production |

> **Note:** The `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` variables are used only during Render deployments by `create_admin.py`, not by standard Django's `createsuperuser --noinput`.

---

## Database Setup and Migrations

### Running Migrations

```bash
cd backend
python manage.py migrate
```

### Migration History

| App | Migration Chain |
|---|---|
| `accounts` | `0001_initial` |
| `patients` | `0001_initial` → `0002_add_user_fk_visit_labreport` → `0003_backfill_user_fk` → `0004_upgrade_labreport_pdf_status` |
| `appointments` | `0001_initial` → `0002_doctorunavailability` → `0003_add_rescheduled_status_cancellation_fields` |
| `prescriptions` | `0001_initial` → `0002_add_visit_fk_remove_notes` |
| `billing` | `0001_initial` |
| `publications` | `0001_initial` → `0002_add_approval_fields` |
| `audit` | `0001_initial` |

### Resetting the Database (development only)

```bash
cd backend
rm db.sqlite3
python manage.py migrate
python create_admin.py
```

---

## Running the Application

### Development Server

```bash
cd backend
python manage.py runserver
```

Entry points after startup:

| URL | Description |
|---|---|
| `http://127.0.0.1:8000/` | Redirects to login selection |
| `http://127.0.0.1:8000/accounts/choose-login/` | Choose Staff or Patient portal |
| `http://127.0.0.1:8000/accounts/login/staff/` | Staff login |
| `http://127.0.0.1:8000/accounts/login/patient/` | Patient login |
| `http://127.0.0.1:8000/accounts/signup/patient/` | Patient self-registration |
| `http://127.0.0.1:8000/dashboard/` | Role-aware dashboard (login required) |
| `http://127.0.0.1:8000/admin/` | Django admin |
| `http://127.0.0.1:8000/api/` | DRF browsable API root |
| `http://127.0.0.1:8000/design-system/` | UI component reference |
| `http://127.0.0.1:8000/publications/` | Public research paper listing |

### Production (Gunicorn)

```bash
cd backend
gunicorn core.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120
```

The `--timeout 120` is required to prevent Gunicorn from killing WeasyPrint PDF generation processes before they complete.

---

## Development Workflow

### First-time setup checklist

```bash
# 1. Install system libraries (WeasyPrint)
# 2. Create virtualenv and install requirements
# 3. Copy and populate backend/.env
# 4. python manage.py migrate
# 5. python create_admin.py
# 6. python manage.py runserver
```

### Creating a Staff Account

After logging in as admin, navigate to **Dashboard → Staff Management** or use the Django admin at `/admin/accounts/customuser/`. Alternatively, the staff creation form is at `/accounts/staff/create/`.

Available roles: `ADMIN`, `DOCTOR`, `RECEPTIONIST`, `PHARMACIST`, `ACCOUNTANT`.

### Day-to-day development

```bash
# Run tests before committing
cd backend
python manage.py test api patients appointments billing publications audit accounts

# Check migrations after model changes
python manage.py makemigrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input
```

---

## Build Instructions

### Render / Production Build

The `build.sh` script runs during Render's build phase:

```bash
#!/usr/bin/env bash
set -o errexit
cd backend
pip install --upgrade pip
pip install -r ../requirements.txt
python manage.py collectstatic --no-input
```

Migrations run in the **start command** (not the build), after Render confirms the database is reachable:

```bash
cd backend && \
python manage.py migrate --no-input && \
python create_admin.py && \
gunicorn core.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120
```

### Docker Build

```bash
# Build the production image
docker build -t proclinic:latest .

# Run locally
docker run -p 8000:8000 \
  -e SECRET_KEY=your-secret \
  -e DEBUG=False \
  -e ALLOWED_HOSTS=localhost \
  proclinic:latest
```

---

## Testing Strategy and Commands

TalMedix has a substantial test suite split across multiple files.

### Running All Tests

```bash
cd backend
python manage.py test
```

### Running Specific Test Modules

```bash
# Patient-facing API tests (profile, appointments, prescriptions, invoices, lab reports, visits)
python manage.py test api.tests

# Extended staff API + audit signal tests
python manage.py test api.tests_extended

# JWT authentication tests
python manage.py test api.test_jwt_auth

# Appointment conflict detection
python manage.py test appointments.test_conflicts

# No-show auto-marking
python manage.py test appointments.test_noshow

# Consultation fee validation
python manage.py test appointments.test_consultation

# Invoice flow
python manage.py test billing.test_invoice_flow

# Patient model tests
python manage.py test patients.tests

# Lab report model tests
python manage.py test patients.test_lab_reports

# Accounts tests
python manage.py test accounts.tests
```

### Test Coverage

```bash
pip install coverage
cd backend
coverage run manage.py test
coverage report
coverage html   # generates htmlcov/index.html
```

A `.coverage` file is present in the repository (excluded from version control via `.gitignore`).

### What is Tested

| Area | Coverage |
|---|---|
| Patient profile (own vs other) | ✅ GET, PUT, 401, 403 |
| Appointment booking | ✅ Success, double-book, past time |
| Appointment reschedule | ✅ Success, conflict, invalid time |
| Appointment cancel | ✅ Success, already cancelled, other patient blocked |
| Prescription access | ✅ Own vs other, staff-blocked endpoint |
| Invoice access | ✅ Own vs other, patient cannot POST |
| Lab report upload | ✅ PDF only, ≤5 MB, ownership |
| Visit / EHR access | ✅ Own vs other |
| Staff permission on patient endpoints | ✅ 403 enforcement |
| Audit signals | ✅ CREATE/UPDATE/DELETE diffs |
| Publication workflow | ✅ Approve, reject, public list |
| Appointment model methods | ✅ cancel(), reschedule(), is_cancellable |

---

## API Overview and Endpoints

The full REST API is mounted at `/api/`. All staff endpoints require a JWT `Bearer` token. Patient endpoints require a `PATIENT`-role JWT token.

### Authentication Endpoints

```http
POST /api/token/
Content-Type: application/json

{ "username": "alice", "password": "secret" }
```

**Response:**
```json
{ "access": "<jwt_access_token>", "refresh": "<jwt_refresh_token>" }
```

```http
POST /api/token/refresh/
Content-Type: application/json

{ "refresh": "<jwt_refresh_token>" }
```

**Access token lifetime:** 60 minutes  
**Refresh token lifetime:** 1 day (rotated on each refresh; old token blacklisted)

### Staff API Endpoints

All endpoints below require `Authorization: Bearer <token>` with a staff-role account.

#### Patients — `/api/patients/`

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/patients/` | List all patients (paginated) |
| `POST` | `/api/patients/` | Create patient record |
| `GET` | `/api/patients/{id}/` | Retrieve patient |
| `PUT/PATCH` | `/api/patients/{id}/` | Update patient |
| `DELETE` | `/api/patients/{id}/` | Delete patient |

**Filter params:** `?first_name=`, `?last_name=`, `?blood_group=A+`, `?gender=Male`, `?search=`

#### Appointments — `/api/appointments/`

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/appointments/` | List appointments |
| `POST` | `/api/appointments/` | Create appointment |
| `GET` | `/api/appointments/{id}/` | Retrieve |
| `PUT/PATCH` | `/api/appointments/{id}/` | Update |
| `DELETE` | `/api/appointments/{id}/` | Delete |
| `POST` | `/api/appointments/{id}/cancel/` | Cancel with optional reason |
| `POST` | `/api/appointments/{id}/reschedule/` | Reschedule `{ "new_time": "<iso8601>" }` |

**Filter params:** `?status=`, `?doctor_id=`, `?patient_id=`, `?date=YYYY-MM-DD`, `?date_from=`, `?date_to=`

#### Prescriptions — `/api/prescriptions/`

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/prescriptions/` | List prescriptions |
| `POST` | `/api/prescriptions/` | Create prescription |
| `GET` | `/api/prescriptions/{id}/` | Retrieve |
| `GET` | `/api/prescriptions/{id}/pdf/` | Download as PDF |
| `GET` | `/api/prescriptions/{id}/html-preview/` | HTML template preview |

**Filter params:** `?patient_id=`, `?doctor_id=`, `?created_from=`, `?created_to=`, `?search=`

#### Invoices — `/api/invoices/`

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/invoices/` | List invoices |
| `POST` | `/api/invoices/` | Create invoice |
| `GET` | `/api/invoices/{id}/` | Retrieve |
| `PUT/PATCH` | `/api/invoices/{id}/` | Update |

**Filter params:** `?status=UNPAID|PAID|PARTIAL|DRAFT|REFUNDED`, `?patient_id=`, `?created_from=`, `?created_to=`

#### Publications — `/api/publications/`

| Method | URL | Auth | Description |
|---|---|---|---|
| `GET` | `/api/publications/` | Staff | List all publications |
| `POST` | `/api/publications/` | Staff | Submit a publication |
| `GET` | `/api/publications/{id}/` | Staff | Retrieve |
| `GET` | `/api/publications/public-list/` | **None** | APPROVED papers only |
| `POST` | `/api/publications/{id}/approve/` | Admin | Approve |
| `POST` | `/api/publications/{id}/reject/` | Admin | Reject `{ "reason": "..." }` |

**Filter params:** `?status=`, `?authors=`, `?year=`, `?search=`

#### Audit Logs — `/api/audit/logs/`

| Method | URL | Auth | Description |
|---|---|---|---|
| `GET` | `/api/audit/logs/` | Admin only | Paginated audit log |
| `GET` | `/api/audit/logs/{id}/` | Admin only | Single log entry |

**Filter params:** `?action_type=CREATE|UPDATE|DELETE|LOGIN`, `?entity_type=Patient|Invoice|...`, `?ordering=timestamp|-timestamp`

### Patient API Endpoints

All endpoints require `Authorization: Bearer <patient_token>`. Each patient can only access their own data.

| Method | URL | Description |
|---|---|---|
| `GET` | `/api/patient/profile/` | Own patient profile |
| `PUT/PATCH` | `/api/patient/profile/` | Update own profile |
| `GET` | `/api/patient/visits/` | EHR visit history |
| `GET` | `/api/patient/appointments/` | Own appointments (filter: `?status=upcoming`) |
| `POST` | `/api/patient/appointments/` | Book appointment |
| `PUT` | `/api/patient/appointments/{id}/reschedule/` | Reschedule `{ "scheduled_time": "..." }` |
| `POST` | `/api/patient/appointments/{id}/cancel/` | Cancel |
| `GET` | `/api/patient/prescriptions/` | Own prescriptions |
| `GET` | `/api/patient/prescriptions/{id}/` | Prescription detail |
| `GET` | `/api/patient/invoices/` | Own invoices |
| `GET` | `/api/patient/lab-reports/` | Own lab reports |
| `POST` | `/api/patient/lab-reports/` | Upload lab report PDF (≤5 MB, multipart) |

### Pagination

All list endpoints return paginated responses:

```json
{
  "count": 84,
  "next": "http://localhost:8000/api/patients/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

| Param | Default | Max | Notes |
|---|---|---|---|
| `?page=<n>` | 1 | — | 1-indexed page number |
| `?page_size=<n>` | 20 | 100 | Standard endpoints |
| `?page_size=<n>` | 50 | 200 | Publications endpoint |

### HTTP Status Codes

| Code | Meaning |
|---|---|
| `200 OK` | Successful read or action |
| `201 Created` | Resource created |
| `400 Bad Request` | Validation error or invalid input |
| `401 Unauthorized` | Missing or invalid JWT token |
| `403 Forbidden` | Authenticated but insufficient permissions |
| `404 Not Found` | Resource does not exist or outside patient's scope |
| `405 Method Not Allowed` | HTTP method not supported on this endpoint |

---

## Authentication and Authorization

### Authentication Methods

TalMedix supports two authentication mechanisms simultaneously:

| Method | Used by | How |
|---|---|---|
| **Django Session Auth** | Staff and patient web browsers | `POST /accounts/login/staff/` or `/accounts/login/patient/` |
| **JWT Bearer Token** | API clients, mobile apps | `POST /api/token/` → `Authorization: Bearer <access_token>` |

### Role System

All permission decisions are driven by `CustomUser.role`:

| Role | Portal Access | Key Permissions |
|---|---|---|
| `ADMIN` | Staff portal | Full system access; approve/reject publications; manage staff accounts; view audit logs |
| `DOCTOR` | Staff portal | Own appointments; create prescriptions and visits; submit publications; verify lab reports |
| `RECEPTIONIST` | Staff portal | Book/manage appointments; register patients; check in patients |
| `PHARMACIST` | Staff portal | View and dispense prescription queue |
| `ACCOUNTANT` | Staff portal | Generate and manage invoices; manage medicine catalogue |
| `PATIENT` | Patient portal | Own appointments, prescriptions, invoices, lab reports; AI health assistant |

### Permission Classes (DRF)

| Class | File | Description |
|---|---|---|
| `IsStaff` | `api/permissions.py` | Any of ADMIN, DOCTOR, RECEPTIONIST, PHARMACIST, ACCOUNTANT |
| `IsPatient` | `api/permissions.py` | PATIENT role only |
| `IsDoctor` | `api/permissions.py` | DOCTOR role only |
| `IsAdminRole` | `api/permissions.py` | ADMIN role only |

### Permission Matrix

| Action | Admin | Doctor | Receptionist | Pharmacist | Accountant | Patient | Anonymous |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| View all patients | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Register patient | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Book appointment | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Create prescription | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Dispense prescription | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ |
| Generate invoice | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ | ❌ |
| View own invoices | — | — | — | — | — | ✅ | ❌ |
| Upload lab report | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Verify lab report | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Archive lab report | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Submit research paper | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Approve / reject paper | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| View approved papers | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| View audit logs | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Use AI assistant | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ |

### Patient Forgot Password (OTP Flow)

Patients can reset their password via a three-step OTP email flow:

1. `GET/POST /accounts/login/patient/forgot-password/` — submit username or email
2. `GET/POST /accounts/login/patient/forgot-password/verify/` — enter 6-digit OTP (valid 10 minutes)
3. `GET/POST /accounts/login/patient/forgot-password/reset/` — set new password

The response at step 1 is non-enumerating: the same success message is shown whether or not the account exists.

---

## Configuration Reference

### JWT Settings (`core/settings.py`)

```python
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME':  timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS':  True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
}
```

### REST Framework Defaults

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'api.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 20,
}
```

### Password Hashing

Argon2 is the primary hasher, with PBKDF2 and BCrypt as fallbacks for imported user records:

```python
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
    'django.contrib.auth.hashers.BCryptSHA256PasswordHasher',
]
```

### Timezone and Locale

```python
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_TZ = True
```

### Storage Backends

When Cloudinary credentials are present, media files (PDFs, lab reports, publication PDFs) are stored in Cloudinary. Otherwise, local `MEDIA_ROOT` is used:

```python
# Automatically selected based on env vars
STORAGES = {
    'default': {
        'BACKEND': 'cloudinary_storage.storage.MediaCloudinaryStorage'
        # OR 'django.core.files.storage.FileSystemStorage'
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}
```

---

## Deployment Instructions

### Render (Recommended)

TalMedix includes a `render.yaml` Blueprint for one-click deployment.

#### Steps

1. Fork or clone the repository and push to GitHub
2. In the Render Dashboard, click **New → Blueprint** and connect your repository
3. Render will read `render.yaml` and provision:
   - A Python web service (`proclinic`) in Singapore region
   - A PostgreSQL 16 database (`proclinic-db`) in Oregon region
4. After the initial deploy, set these environment variables manually in the Render Dashboard:

| Variable | Where to get value |
|---|---|
| `DATABASE_URL` | Render Dashboard → `proclinic-db` → Connections → External Database URL |
| `CLOUDINARY_CLOUD_NAME` | Cloudinary Dashboard → Settings → Access Keys |
| `CLOUDINARY_API_KEY` | Cloudinary Dashboard |
| `CLOUDINARY_API_SECRET` | Cloudinary Dashboard |
| `GEMINI_API_KEY` | Google AI Studio |
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_PASS` | Gmail App Password |

5. Trigger a manual redeploy after setting environment variables

#### Render Plan Notes

- **Web service:** Free plan (512 MB RAM, 0.1 CPU, spins down after 15 min inactivity)
- **Database:** Free plan (1 GB storage, expires after 90 days — upgrade for production use)
- `autoDeploy: true` — every push to `main` triggers an automatic redeploy
- `SECRET_KEY` is auto-generated by Render on first deploy

#### Default Admin Credentials on Render

The `create_admin.py` script runs on every deploy:
- **Username:** `admin`
- **Password:** `Admin@12345`

> **Change this password immediately** after the first deployment.

### Docker (Self-Hosted)

```bash
# 1. Build image
docker build -t proclinic:latest .

# 2. Run with PostgreSQL
docker run -d \
  --name proclinic \
  -p 8000:8000 \
  -e DEBUG=False \
  -e SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(50))") \
  -e DATABASE_URL=postgres://user:pass@db-host:5432/proclinic \
  -e ALLOWED_HOSTS=yourdomain.com \
  -e CLOUDINARY_CLOUD_NAME=... \
  -e CLOUDINARY_API_KEY=... \
  -e CLOUDINARY_API_SECRET=... \
  proclinic:latest
```

Place a reverse proxy (nginx, Caddy) in front to handle HTTPS termination.

---

## Security Considerations

### Implemented Security Measures

| Measure | Implementation |
|---|---|
| **Password hashing** | Argon2 (primary); PBKDF2 and BCrypt as fallbacks |
| **JWT token rotation** | Refresh tokens are blacklisted after use |
| **HTTPS enforcement** | `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` in production |
| **HSTS** | `SECURE_HSTS_SECONDS=31536000` with `include_subdomains` and `preload` in production |
| **CSRF protection** | Django middleware enabled; `CSRF_TRUSTED_ORIGINS` configured for Render |
| **Clickjacking protection** | `XFrameOptionsMiddleware` enabled |
| **Role-based access** | Every view enforces `request.user.role` checks |
| **Patient data isolation** | Patient API views filter all querysets by `request.user` — patients cannot see other patients' data |
| **Audit trail** | Every CREATE/UPDATE/DELETE/LOGIN is logged with before/after diffs |
| **Sensitive field exclusion** | `password`, `token`, `secret`, `api_key` are never stored in AuditLog |
| **File upload validation** | Lab reports and publication PDFs: PDF extension enforced; lab reports ≤5 MB |
| **Last admin protection** | Cannot deactivate the last active admin account |
| **Self-deactivation protection** | Admins cannot deactivate their own account |
| **OTP non-enumeration** | Password reset always returns the same response regardless of whether the account exists |
| **OTP expiry** | OTPs expire after 10 minutes; 2-minute cooldown between requests |
| **SQL injection** | Django ORM parameterised queries throughout — no raw SQL |
| **XSS** | Django template auto-escaping enabled |

### Security Headers (production only)

```python
SECURE_PROXY_SSL_HEADER         = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT             = True
SESSION_COOKIE_SECURE           = True
CSRF_COOKIE_SECURE              = True
SECURE_HSTS_SECONDS             = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = True
```

### AI Assistant Safety

The Gemini AI assistant system prompt enforces:
- Clear "not a doctor" disclaimer in every response
- Immediate emergency escalation for life-threatening symptom keywords
- Structured response format (no free-form diagnosis)
- Hard 1000-character input limit

---

## Performance Notes

- **`select_related` and `prefetch_related`** are used on all multi-join querysets to prevent N+1 queries
- **`update_fields`** is used on all model method saves (`cancel()`, `reschedule()`, `mark_verified()`, etc.) to minimise database write overhead
- **WhiteNoise** with `CompressedManifestStaticFilesStorage` gzips and fingerprint-hashes all static assets; browsers can cache them indefinitely
- **Gunicorn workers:** 2 workers (safe for 512 MB RAM on Render free tier)
- **Gunicorn timeout:** 120 seconds to allow WeasyPrint PDF generation to complete
- **PDF generation:** WeasyPrint renders entirely in-memory (`BytesIO`) — no temporary files on disk
- **`db_index=True`** is set on frequently filtered fields: `Appointment.status`, `Prescription.dispense_status`, `Publication.status`, `LabReport.status`
- **Audit writes:** All `AuditLog.objects.create()` calls are wrapped in exception handlers — audit failures never block the main transaction

---

## Monitoring and Logging

### Logging Configuration

TalMedix streams all logs to **stdout** so they are captured by Render's log viewer (or any container runtime's log aggregator):

| Logger | Level | Description |
|---|---|---|
| `root` | `WARNING` | All libraries not explicitly configured |
| `django` | `INFO` | Framework-level information |
| `django.request` | `ERROR` | Request errors only |
| `accounts` | `DEBUG` | Login, OTP, user management events |
| Audit module | `ERROR` | Audit write failures |
| Billing | `INFO/ERROR` | Invoice PDF generation, email delivery |
| AI assistant | `INFO/WARNING/ERROR` | Gemini API calls, quota errors |

**Log format:**
```
[LEVELNAME] TIMESTAMP logger_name message
```

**Example:**
```
[INFO] 2026-05-28 06:30:00,000 billing.utils Saved PDF for invoice 42 → invoice_42_2026-05-28.pdf
[ERROR] 2026-05-28 06:31:00,000 billing.utils Failed to send draft invoice email for invoice 42: Connection refused
```

### Audit Log Access

- **Web UI:** `GET /audit/` — paginated read-only view (Admin only)
- **REST API:** `GET /api/audit/logs/` — filterable, searchable (Admin only; returns empty list for non-admins)
- **Django Admin:** `/admin/audit/auditlog/` — read-only; add/change/delete permissions disabled

### Tracking Covered Entities

`AuditLog` automatically records operations on: `Patient`, `Appointment`, `Prescription`, `Invoice`, `Publication`, `LabReport`

---

## Management Commands

### `mark_noshow`

Marks `SCHEDULED` and `RESCHEDULED` appointments as `NOSHOW` when the patient has not checked in within the configured grace period after the scheduled start time.

```bash
# Default: 30-minute grace period
python manage.py mark_noshow

# Custom grace period
python manage.py mark_noshow --grace 15
```

**Cron schedule example (every 5 minutes):**
```cron
*/5 * * * * /path/to/.venv/bin/python /path/to/backend/manage.py mark_noshow >> /var/log/proclinic/noshow.log 2>&1
```

---

## Troubleshooting

### `WeasyPrint` PDF generation fails

**Symptom:** `RuntimeError: WeasyPrint failed` or blank PDF download

**Cause:** Missing system libraries (Pango, Cairo, GDK-Pixbuf)

**Fix:**
```bash
# Ubuntu/Debian
sudo apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    libfontconfig1 libgdk-pixbuf-2.0-0 libcairo2 shared-mime-info

# macOS
brew install pango
```

---

### `django.db.utils.OperationalError: no such table`

**Cause:** Migrations have not been applied

**Fix:**
```bash
cd backend
python manage.py migrate
```

---

### `SECRET_KEY` error on startup

**Cause:** `backend/.env` file is missing or `SECRET_KEY` is not set

**Fix:** Create `backend/.env` with a `SECRET_KEY` value. See [Environment Configuration](#environment-configuration).

---

### Media files not loading in production

**Cause:** Cloudinary credentials not configured; `IS_RENDER=true` but no persistent disk

**Fix:** Set `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` environment variables. When all three are present, the storage backend switches to Cloudinary automatically.

---

### AI assistant returns "service not configured"

**Cause:** `GEMINI_API_KEY` environment variable is not set

**Fix:** Add `GEMINI_API_KEY=<your-key>` to `backend/.env` (local) or the Render Dashboard (production).

---

### Emails not being sent

**Cause:** `GMAIL_USER` and/or `GMAIL_PASS` not configured, or Gmail SMTP is blocked

**Fix:**
1. Enable 2FA on your Gmail account
2. Generate an [App Password](https://support.google.com/accounts/answer/185833)
3. Set `GMAIL_USER=your@gmail.com` and `GMAIL_PASS=<app-password>` in `.env`

---

### JWT token rejected (`401 Unauthorized`)

**Cause:** Expired access token (60-minute lifetime)

**Fix:** Refresh the token:
```bash
curl -X POST http://localhost:8000/api/token/refresh/ \
  -H "Content-Type: application/json" \
  -d '{"refresh": "<your_refresh_token>"}'
```

---

### Static files return 404 in production

**Cause:** `collectstatic` not run, or `STATIC_ROOT` not pointing to `backend/staticfiles/`

**Fix:**
```bash
cd backend
python manage.py collectstatic --no-input
```

Ensure WhiteNoise is in `MIDDLEWARE` before `CommonMiddleware`:
```python
'whitenoise.middleware.WhiteNoiseMiddleware',
```

---

### `CORS` errors from API client

**Cause:** `CORS_ALLOW_ALL_ORIGINS = True` is set (development mode); if customised, the client origin may not be listed

**Note:** The current setting allows all origins. For production hardening, replace with:
```python
CORS_ALLOWED_ORIGINS = ['https://yourfrontend.com']
```

---

## Contributing Guidelines

### Branching Strategy

- `main` — production-ready; auto-deployed to Render
- Feature branches — `feature/<name>`, merged via pull request

### Code Standards

1. **Django conventions** — follow the [Django Coding Style](https://docs.djangoproject.com/en/dev/internals/contributing/writing-code/coding-style/)
2. **Model methods** — use `update_fields` when saving partial changes
3. **Views** — always check `request.user.role` before returning sensitive data
4. **Signals** — wrap all signal logic in `try/except`; logging failures must never crash the main transaction
5. **Tests** — add tests for any new API endpoint or model behaviour before opening a PR
6. **Migrations** — generate and commit migrations for all model changes; never edit existing migration files
7. **Secrets** — never commit credentials; use `backend/.env` (listed in `.gitignore`)

### Running Tests Before a PR

```bash
cd backend
python manage.py test
```

All tests must pass. New features should include corresponding test coverage.

### Submitting a Pull Request

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes, write tests, run `python manage.py test`
4. Commit with a descriptive message
5. Push and open a pull request against `main`

---

## License Information

License information could not be determined from the codebase. No `LICENSE` file is present in the repository. Contact the project maintainer to determine usage terms.

---

## Credits and Acknowledgements

TalMedix was developed using the following open-source technologies:

- [Django](https://www.djangoproject.com/) — Web framework
- [Django REST Framework](https://www.django-rest-framework.org/) — REST API toolkit
- [djangorestframework-simplejwt](https://django-rest-framework-simplejwt.readthedocs.io/) — JWT authentication
- [WeasyPrint](https://weasyprint.org/) — HTML-to-PDF rendering for prescriptions and invoices
- [WhiteNoise](http://whitenoise.evans.io/) — Static file serving
- [django-environ](https://django-environ.readthedocs.io/) — Environment variable management
- [django-filter](https://django-filter.readthedocs.io/) — QuerySet filtering
- [django-cors-headers](https://github.com/adamchainz/django-cors-headers) — CORS headers
- [Cloudinary](https://cloudinary.com/) — Cloud media storage
- [Pillow](https://pillow.readthedocs.io/) — Image processing
- [argon2-cffi](https://argon2-cffi.readthedocs.io/) — Argon2 password hashing
- [Gunicorn](https://gunicorn.org/) — WSGI HTTP server
- [psycopg2](https://www.psycopg.org/) — PostgreSQL adapter
- [Google Generative AI (Gemini)](https://ai.google.dev/) — AI health assistant backend
- [Render](https://render.com/) — Cloud deployment platform

<!-- TALMEDIX-DEVELOPMENT-NOTES -->

## Recent Development Work

This section documents areas of ongoing development. The notes below describe
changes visible in the working tree and should not be interpreted as a claim
that every change has been fully tested or deployed.

### Branding and User Interface

- Updated application branding from ProClinic to TalMedix in multiple templates.
- Updated branding across login and account-related screens.
- Worked on the shared base template and design-system page.
- Refined selected billing and invoice templates.

### Backend and Application Configuration

- Updated Django settings and application configuration.
- Worked on patient, prescription, and publication model definitions.
- Updated patient URL configuration.
- Updated selected billing utility code.

### Docker and Dependencies

- Updated the existing Docker Compose configuration.
- Reviewed the Python dependency list and project configuration.
- Existing Docker and application setup instructions elsewhere in this README
  remain the primary setup reference.

### Database Migrations and File Handling

- Reviewed migration files related to patient lab-report PDF fields,
  prescription PDF fields, and publication PDF fields.
- Apply migrations and test file uploads and PDF generation in a development
  environment before deploying these changes.

### Validation Status

The changes listed here are development notes, not a declaration that all
features are production-ready. Before release:

1. Review the Django settings and environment variables.
2. Install dependencies in the intended environment.
3. Run database migrations.
4. Run the project's available automated tests.
5. Verify authentication, patient workflows, billing, prescriptions,
   publications, PDF generation, and Docker startup.
6. Confirm that secrets and production credentials are not committed.

### Planned Improvements

The following are roadmap items unless their implementation is verified
elsewhere in the project:

- Validate patient-count-based subscription limits.
- Add or verify subscription and billing enforcement.
- Improve deployment documentation and add verified application screenshots.
- Document tested installation and backup/restore procedures.

<!-- END TALMEDIX-DEVELOPMENT-NOTES -->
