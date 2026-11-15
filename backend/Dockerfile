FROM python:3.12-slim
WORKDIR /app
# #20: dependencias fijadas con hashes (requirements.lock, generado con pip-compile
# --generate-hashes desde pyproject.toml). El paquete propio va sin resolver dependencias.
COPY pyproject.toml requirements.lock ./
COPY api ./api
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
 && pip install --no-cache-dir --no-deps . \
 && playwright install --with-deps chromium \
 && rm -rf /var/lib/apt/lists/*
# #11: --proxy-headers hace que request.client sea la IP real que informa el proxy de Railway
# (el límite por IP depende de eso). El contenedor solo recibe tráfico a través de ese proxy,
# por eso se confía en él ("*"). Si Railway publica rangos fijos, restringirlo a ellos.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
