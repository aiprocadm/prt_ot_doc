FROM minio/minio:RELEASE.2024-03-07T00-43-48Z
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9000/minio/health/ready || exit 1
CMD ["server", "/data", "--console-address", ":9001"]
