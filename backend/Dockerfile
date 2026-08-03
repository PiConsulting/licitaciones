FROM python:3.11-slim

WORKDIR /app

COPY backend/pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir \
    fastapi uvicorn sqlalchemy alembic pydantic-settings pyjwt passlib[bcrypt] structlog psycopg2-binary python-dotenv

COPY backend /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
