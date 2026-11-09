FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --system --uid 10001 --no-create-home appuser
USER 10001
EXPOSE 8080
# ONE worker process with threads: the request counters of prometheus_client live in the memory of a process.
# With several workers every scrape would hit a random one and see a different (smaller) counter, so rate()
# and the alerts would be wrong. --worker-tmp-dir /dev/shm lets the container run with a read-only root filesystem.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --worker-tmp-dir /dev/shm --access-logfile - 'app.main:create_app()'"]
