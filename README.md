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

## Render Deployment

This folder includes [render.yaml](render.yaml) and [Procfile](Procfile).

Required start command:

uvicorn app.main:app --host 0.0.0.0 --port $PORT

Notes:

- Do not use `--reload` in Render.
- Set Render Root Directory to this backend folder.
- Add all required environment variables from [.env.example](.env.example).
- Ensure `CORS_ORIGINS` includes your frontend Render URL.
