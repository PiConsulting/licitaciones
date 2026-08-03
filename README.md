# licitaciones-pi

Monorepo base para CedIA - Sistema de Analisis Automatico de Pliegos.

## Requisitos

- Python 3.11+
- Node.js 20+
- PostgreSQL local

## Backend

1. Crear y activar entorno virtual.
2. Instalar dependencias:
   - `c:/Users/AgostinaTorres/Desktop/Proyectos/licitaciones/licitaciones-pi/.venv/Scripts/python.exe -m pip install fastapi uvicorn sqlalchemy alembic pydantic-settings pyjwt passlib[bcrypt] structlog psycopg2-binary pytest httpx ruff email-validator`
3. Crear base local en PostgreSQL:
   - `CREATE DATABASE licitaciones;`
4. Ejecutar backend:
   - `c:/Users/AgostinaTorres/Desktop/Proyectos/licitaciones/licitaciones-pi/.venv/Scripts/python.exe -m uvicorn main:app --reload --app-dir backend`

## Frontend

1. Instalar dependencias:
   - `npm install` (en carpeta `frontend`)
2. Ejecutar frontend:
   - `npm run dev`

## Testing

- Backend: `c:/Users/AgostinaTorres/Desktop/Proyectos/licitaciones/licitaciones-pi/.venv/Scripts/python.exe -m pytest backend/tests`
- Frontend: `npm run test` (en `frontend`)
