FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Paksa Python flush output langsung — agar log muncul di Coolify
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin kode
COPY . .

# Buat direktori data (akan di-override oleh volume)
RUN mkdir -p data/images data/browser_session

# Jalankan bot dalam mode scheduled (Facebook only, auto-posting)
CMD ["python", "main.py"]
