FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY services ./services
COPY storage ./storage
COPY utils ./utils
COPY admin ./admin

RUN mkdir -p /app/data /app/downloads

CMD ["python", "-m", "bot.main"]
