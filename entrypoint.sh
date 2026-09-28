#!/bin/sh
set -e

echo "==> Aplicando migraciones de base de datos con Alembic..."
alembic upgrade head

echo "==> Iniciando servidor de producción FastAPI..."
exec fastapi run main.py --host 0.0.0.0 --port 8000