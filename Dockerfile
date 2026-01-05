FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y sbcl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . /app

RUN pip install flask requests gunicorn

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "app:app"]
