FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir \
    flask psycopg2-binary python-dotenv reportlab

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
