# FastAPI + PostgreSQL con Docker

## Levantar todo (un solo comando)

```bash
docker compose up --build
```

Esto:
1. Levanta un contenedor de PostgreSQL 16 (`db`) con un volumen persistente.
2. Espera a que Postgres esté listo (healthcheck).
3. Construye la API, aplica las migraciones de Alembic y arranca FastAPI.

API: http://localhost:8000 · Documentación: http://localhost:8000/docs

No hace falta crear `.env`: los valores por defecto son `postgres / postgres / inventario`.
Para cambiarlos, copia `.env.example` a `.env` y edítalo.

## Comandos útiles

```bash
docker compose up --build -d     # en segundo plano
docker compose logs -f web       # ver logs de la API
docker compose down              # detener (conserva los datos)
docker compose down -v           # detener y BORRAR la base de datos
docker compose exec db psql -U postgres -d inventario   # consola SQL
```

## Endpoints nuevos

- `GET /health` → `{"status": "ok"}`
- `POST /images` → sube una imagen (JPG/PNG/WEBP/GIF, máx 5 MB) a S3 con Boto3 y guarda la referencia en la tabla `app_images`
- `GET /images` → lista las imágenes con una URL temporal para verlas

## Despliegue en AWS (3 EC2)

Ver **[GUIA_AWS.md](GUIA_AWS.md)**. Archivos de despliegue en `deploy/`:

| Carpeta | EC2 | Qué levanta |
|---|---|---|
| `deploy/proxy` | #1 pública | Nginx Proxy Manager (80, 443, 81) |
| `deploy/api` | #2 privada | FastAPI (8000) |
| `deploy/postgres` | #3 privada | PostgreSQL (5432) + volumen |
| `deploy/install-docker.sh` | las 3 | Docker + Compose (User data) |
| `deploy/s3-policy.json` | IAM | Permisos mínimos sobre el bucket |
