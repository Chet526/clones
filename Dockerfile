# GeoBrief LE — production container image
FROM python:3.12-slim

# Run as a non-root user; keep case data on a mounted volume.
RUN useradd --create-home --uid 1000 geobrief
ENV GEOBRIEF_HOME=/data \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /data && chown geobrief:geobrief /data
VOLUME /data
USER geobrief
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

CMD ["python", "-m", "geobrief", "serve", "--host", "0.0.0.0", "--port", "8000"]
