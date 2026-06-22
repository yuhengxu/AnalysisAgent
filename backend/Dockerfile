FROM python:3.12-slim

ENV TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY app ./app

RUN mkdir -p /app/data/raw /app/data/processed /app/data/exports /app/data/charts /app/db /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
