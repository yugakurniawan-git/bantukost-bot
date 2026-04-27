FROM python:3.11-slim

# Dependensi sistem untuk Playwright Chromium
RUN apt-get update && apt-get install -y \
    wget curl gnupg ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libatspi2.0-0 libgl1 fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps dulu (layer ini di-cache kalau requirements tidak berubah)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install browser Chromium untuk Playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# Salin kode
COPY . .

# Buat direktori data (akan di-override oleh volume)
RUN mkdir -p data/images data/browser_session

# Jalankan bot dalam mode scheduled (Facebook only, auto-posting)
CMD ["python", "main.py"]
