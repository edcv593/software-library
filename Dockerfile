FROM python:3.12-slim

LABEL maintainer="software-library"
LABEL description="Software Library v7 - searchable categorized web interface for NAS"

WORKDIR /app

COPY app.py /app/app.py
COPY v7.py /app/v7.py

# app.py imports requests, so install the runtime dependency in the image.
RUN pip install --no-cache-dir --disable-pip-version-check requests

ENV LIB_ROOT_DIR=/data \
    LIB_PORT=8899 \
    LIB_DATA_DIR=/app/data \
    LIB_UPLOAD_DIR=/app/data/uploads \
    LIB_WATCH_INTERVAL=3600 \
    PYTHONUNBUFFERED=1

RUN mkdir -p /app/data /app/data/uploads

EXPOSE 8899

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8899/index.html')" || exit 1

CMD ["python", "v7.py", "--watch"]
