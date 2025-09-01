# Python 베이스 이미지
FROM python:3.11-slim

# Playwright(Chromium) 실행에 필요한 OS 라이브러리 설치
RUN apt-get update && apt-get install -y \
    wget gnupg unzip curl git \
    libnss3 libx11-xcb1 libxcomposite1 libxcursor1 \
    libxdamage1 libxi6 libxtst6 libcups2 libxrandr2 \
    libasound2 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 \
    libdrm2 libgbm1 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉터리
WORKDIR /app

# 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright + Chromium 설치 (의존성 포함)
RUN playwright install --with-deps chromium

# 앱 소스 복사
COPY server.py .

# Cloud Run 표준 포트
ENV PORT=8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
