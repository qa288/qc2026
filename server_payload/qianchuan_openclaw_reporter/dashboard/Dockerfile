FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY dashboard/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

EXPOSE 9898

CMD ["sh", "-c", "uvicorn dashboard.main:app --host 0.0.0.0 --port 9898 --workers ${UVICORN_WORKERS:-2}"]
