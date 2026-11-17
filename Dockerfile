FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm AS backend
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend/dist
WORKDIR /app
COPY scripts/install_stockfish.py /tmp/install_stockfish.py
RUN python /tmp/install_stockfish.py --destination /opt/stockfish --link /usr/local/bin/stockfish
COPY backend/requirements.lock backend/requirements-studio.txt ./
RUN pip install --no-cache-dir -r requirements-studio.txt \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /data /app/.langgraph_api && chown app:app /data /app/.langgraph_api
COPY backend/ ./backend/
COPY langgraph.json ./
COPY --from=frontend /build/dist ./frontend/dist/
USER app
EXPOSE 8000 2024
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM backend AS test
USER root
RUN pip install --no-cache-dir 'pytest>=8,<10'
USER app
CMD ["python", "-m", "pytest", "backend/tests", "-q", "-p", "no:cacheprovider"]

FROM backend AS app
