FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY immich_auto_tag.py .

ENTRYPOINT ["python3", "immich_auto_tag.py"]
