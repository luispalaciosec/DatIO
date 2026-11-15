FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY api ./api
RUN pip install --no-cache-dir . \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
# #11: --proxy-headers hace que request.client sea la IP real que informa el proxy de Railway
# (el límite por IP depende de eso). El contenedor solo recibe tráfico a través de ese proxy,
# por eso se confía en él ("*"). Si Railway publica rangos fijos, restringirlo a ellos.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
