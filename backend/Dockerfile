FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY api ./api
RUN pip install --no-cache-dir . \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
