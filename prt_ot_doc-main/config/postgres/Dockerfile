FROM postgres:16-alpine
ENV POSTGRES_DB=app \
    POSTGRES_USER=app \
    POSTGRES_PASSWORD=app
COPY config/postgres/init.sql /docker-entrypoint-initdb.d/init.sql
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pg_isready -U "$${POSTGRES_USER}" -d "$${POSTGRES_DB}" || exit 1
