FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY dashboard/requirements.txt /tmp/requirements.txt
RUN apt-get -o Acquire::ForceIPv4=true update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

EXPOSE 9898

CMD ["uvicorn", "dashboard.main:app", "--host", "0.0.0.0", "--port", "9898"]
