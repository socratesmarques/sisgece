FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir -r requirements.txt && useradd --system sisgece
COPY --chown=sisgece:sisgece backend backend
COPY --chown=sisgece:sisgece frontend frontend
COPY --chown=sisgece:sisgece db db
USER sisgece
EXPOSE 3000
HEALTHCHECK CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:3000/api/ready',timeout=3)"
CMD ["sh","-ec","python backend/manage.py migrate && exec waitress-serve --listen=*:3000 backend.app:app"]
