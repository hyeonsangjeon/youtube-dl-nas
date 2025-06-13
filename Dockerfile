# Base image with Python 3.10
FROM python:3.10-slim

LABEL maintainer="wingnut0310 <wingnut0310@gmail.com>"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install required system packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        v4l-utils \
        dos2unix \
        vim \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY /subber /usr/bin/subber
COPY /run.sh /
COPY / /usr/src/app/

# Fix permissions and formatting
RUN chmod +x /usr/bin/subber /run.sh && \
    dos2unix /usr/bin/subber /run.sh && \
    ln -s /usr/src/app/downfolder /

# Set working directory
WORKDIR /usr/src/app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -U youtube-dl

# Expose port and define volume
EXPOSE 8080
VOLUME ["/downfolder"]

# Default command
CMD ["/bin/bash", "/run.sh"]