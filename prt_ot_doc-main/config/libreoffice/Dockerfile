FROM ubuntu:22.04
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice python3 \
    && rm -rf /var/lib/apt/lists/*
EXPOSE 2002
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD soffice --headless --nologo --nodefault --norestore --invisible --accept="socket,host=localhost,port=2002;urp;" --terminate_after_init && exit 0 || exit 1
CMD ["soffice", "--headless", "--nologo", "--nodefault", "--norestore", "--invisible", "--accept=socket,host=0.0.0.0,port=2002;urp;"]
