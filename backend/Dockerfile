FROM python:3.12-slim
WORKDIR /app
# El Node que trae Playwright (>= 1.65) necesita libatomic1, que la imagen slim no incluye;
# sin ella `playwright install` falla antes de poder instalar sus propias dependencias.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libatomic1 \
 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
COPY api ./api
RUN pip install --no-cache-dir . \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
