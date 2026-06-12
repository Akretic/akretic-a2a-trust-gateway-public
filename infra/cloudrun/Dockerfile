FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    AKRETIC_SERVICE_MODULE=demo_ui.main:app

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD python -m uvicorn ${AKRETIC_SERVICE_MODULE} --host 0.0.0.0 --port ${PORT}
