# ./api/Dockerfile
FROM python:3.11-slim

# ติดตั้ง system deps ที่ Pillow / tesseract / mysql client อาจต้องการ
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmariadb-dev-compat \
    libmariadb-dev \
    tesseract-ocr \
    tesseract-ocr-tha \
    libjpeg-dev \
    zlib1g-dev \
    libtiff5-dev \
    libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy requirements แล้วติดตั้ง
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r /app/requirements.txt

# copy project
COPY . /app

# ถ้เรียกด้วย uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
