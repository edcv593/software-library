FROM python:3.12-slim

LABEL maintainer="software-library"
LABEL description="Software Library - searchable categorized web interface for NAS"

WORKDIR /app

# Copy app.py INTO the image (self-contained, no volume needed for app)
COPY app.py /app/app.py

# Environment variables
ENV LIB_ROOT_DIR=/data \
    LIB_PORT=8899 \
    LIB_DATA_DIR=/app/data \
    LIB_WATCH_INTERVAL=3600 \
    PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8899

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8899/index.html')" || exit 1

# Run with watch mode (auto-rescan)
CMD ["python", "app.py", "--watch"]
