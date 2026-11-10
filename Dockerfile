FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --system sisgece
COPY backend backend
COPY frontend frontend
COPY db db
USER sisgece
EXPOSE 3000
HEALTHCHECK CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:3000/api/ready',timeout=3)"
CMD ["sh","-ec","python backend/manage.py migrate && exec waitress-serve --listen=*:3000 backend.app:app"]
