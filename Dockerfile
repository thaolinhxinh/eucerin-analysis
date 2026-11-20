FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin appuser
COPY app ./app
COPY models ./models
COPY reference/Validation_Metrics.csv reference/Holdout_Metrics.csv ./reference/
COPY start_server.py ./start_server.py
RUN mkdir -p /app/storage && chown -R appuser:appuser /app/storage
EXPOSE 10000
CMD ["python", "start_server.py"]
