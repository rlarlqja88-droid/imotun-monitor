# Playwright + Chromium + 모든 OS 의존성이 이미 포함된 공식 이미지
FROM mcr.microsoft.com/playwright/python:v1.46.0-jammy

WORKDIR /app

# 필요한 파이썬 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스
COPY server.py .

# Cloud Run 표준 포트
ENV PORT=8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
