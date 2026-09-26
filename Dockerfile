FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN python -m venv /venv
COPY requirements.txt .
RUN /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.12-slim
ENV PATH="/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app && mkdir -p /app/uploads /app/staticfiles && chown -R app:app /app
COPY --from=builder /venv /venv
COPY --chown=app:app . .
RUN chmod +x /app/entrypoint.sh
USER app
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn","service_portal.wsgi:application","--bind","0.0.0.0:8000","--workers","3","--timeout","60","--access-logfile","-"]
