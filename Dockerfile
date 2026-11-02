FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm tesseract-ocr libglib2.0-0 libgl1 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt playwright && playwright install --with-deps chromium
COPY app ./app
RUN cd app/tools && npm install --omit=dev
ENV KAMUYOT_DATA=/srv/data
EXPOSE 8000
CMD ["sh","-c","uvicorn app.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
