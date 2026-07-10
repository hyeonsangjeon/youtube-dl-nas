FROM denoland/deno:bin-2.9.1 AS deno

FROM python:3.12-slim

LABEL org.opencontainers.image.title="youtube-dl-nas" \
      org.opencontainers.image.description="Authenticated yt-dlp download queue for private NAS servers" \
      org.opencontainers.image.source="https://github.com/hyeonsangjeon/youtube-dl-nas" \
      org.opencontainers.image.licenses="MIT"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    DOWNLOAD_DIR=/downfolder \
    STATE_DIR=/usr/src/app/metadata

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /usr/src/app/

# Install Python dependencies
COPY requirements.txt /usr/src/app/requirements.txt
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy files
COPY --from=deno /deno /usr/local/bin/deno
COPY /subber /usr/bin/subber
COPY /run.sh /
COPY / /usr/src/app/

RUN chmod +x /usr/bin/subber /run.sh && \
    mkdir -p /downfolder/.incomplete /usr/src/app/metadata

EXPOSE 8080
VOLUME ["/downfolder", "/usr/src/app/metadata"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.environ.get('APP_PORT') or '8080'; urllib.request.urlopen('http://127.0.0.1:' + port + '/health', timeout=3)" || exit 1

CMD ["/bin/bash", "/run.sh"]
