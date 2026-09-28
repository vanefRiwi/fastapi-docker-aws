# 1. Imagen base oficial de Python 3.12 en Debian Slim
FROM python:3.12-slim

# 2. Copiar el binario oficial de uv directamente desde su imagen
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 3. Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# 4. Variables de entorno para optimizar uv y Python en contenedores
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 5. Copiar únicamente los manifiestos de dependencias
COPY pyproject.toml uv.lock ./

# 6. Instalar dependencias sin empaquetar el código fuente (Capa cacheable)
RUN uv sync --frozen --no-install-project --no-dev

# 7. Copiar el resto del código fuente del proyecto
COPY . .

# 8. Instalar el proyecto en el entorno virtual
RUN uv sync --frozen --no-dev

# 9. Agregar el entorno virtual generado por uv al PATH del sistema
ENV PATH="/app/.venv/bin:$PATH"

# 10. Asignar permisos de ejecución al script de arranque
RUN chmod +x entrypoint.sh

# 11. Exponer el puerto de la aplicación
EXPOSE 8000

# 12. Punto de entrada
ENTRYPOINT ["./entrypoint.sh"]