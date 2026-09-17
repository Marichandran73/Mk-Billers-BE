# Mk-Billers-BE

FastAPI backend for MK Billers.

## Local Run

1. Create and activate your virtual environment.
2. Install dependencies:

	pip install -r requirements.txt

3. Copy `.env.example` to `.env` and fill real values.
4. Start server:

	uvicorn app.main:app --reload

Health endpoint:

GET /api/health

## SMTP Setup For Invite Mail

Configure SMTP in `.env` to send invite OTP mail:

- `SMTP_HOST` (for Gmail: `smtp.gmail.com`)
- `SMTP_PORT` (`587` for TLS, `465` for SSL)
- `SMTP_USER` (your sender email)
- `SMTP_PASSWORD` (for Gmail, use App Password)
- `SMTP_FROM_EMAIL` (from address shown in email)
- `SMTP_FROM_NAME` (display name)
- `SMTP_USE_TLS` (`true` for port 587)
- `SMTP_USE_SSL` (`true` for port 465)
- `INVITE_CODE_EXPIRE_MINUTES` (`60` for 1 hour)

Recommended for Gmail:

- `SMTP_HOST=smtp.gmail.com`
- `SMTP_PORT=587`
- `SMTP_USE_TLS=true`
- `SMTP_USE_SSL=false`

## Render Deployment

This folder includes [render.yaml](render.yaml) and [Procfile](Procfile).

Required start command:

uvicorn app.main:app --host 0.0.0.0 --port $PORT

Notes:

- Do not use `--reload` in Render.
- Set Render Root Directory to this backend folder.
- Add all required environment variables from [.env.example](.env.example).
- Ensure `CORS_ORIGINS` includes your frontend Render URL.
