FROM node:20-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN useradd -m app
WORKDIR /srv/app
COPY backend/requirements.txt backend/
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=ui /ui/dist frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN mkdir -p data exports backups && chown -R app:app /srv/app && chmod +x /entrypoint.sh
USER app
WORKDIR /srv/app/backend
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
