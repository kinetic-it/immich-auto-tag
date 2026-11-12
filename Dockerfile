FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && useradd --system --uid 10001 --no-create-home app

COPY immich_auto_tag.py .

# Das Skript schreibt keine Dateien; es spricht nur die Immich-API an.
USER 10001
ENTRYPOINT ["python3", "immich_auto_tag.py"]
