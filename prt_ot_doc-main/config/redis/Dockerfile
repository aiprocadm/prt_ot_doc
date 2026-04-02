FROM redis:7-alpine
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD redis-cli ping | grep -q PONG || exit 1
CMD ["redis-server", "--appendonly", "yes"]
