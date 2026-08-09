# Build context is the repo root (backend/main.py uses `from .models import ...`,
# so it must run as the `backend` package). On Railway: set the service's root
# directory to the repo root and its Dockerfile path to backend/Dockerfile.
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
