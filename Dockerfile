FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings_docker

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==26.2.0

COPY . .

# private_media: adjuntos de siniestros; el volumen nombrado hereda este dueño
RUN useradd --system --no-create-home app \
 && mkdir -p /app/private_media /app/.modelos \
 && chown -R app /app
USER app

EXPOSE 8000

# gthread: el bot procesa los mensajes en hilos dentro del mismo proceso (en_segundo_plano)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", \
     "--workers", "2", "--threads", "8", "--worker-class", "gthread", \
     "--access-logfile", "-", "--forwarded-allow-ips", "127.0.0.1"]
