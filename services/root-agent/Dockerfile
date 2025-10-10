# 你在 VPC-only Studio，請用你自己的 ECR 基底鏡像（修改成你有的 tag）
ARG BASE_IMAGE=182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/python-base/python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd -m appuser

# 安裝系統套件（包含 curl）
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# 安裝相依
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 複製程式
COPY app/ .

EXPOSE 50000

USER appuser
# 因為我們在 main.py 裡已經呼叫 uvicorn.run(..., reload=True)，這裡直接跑 main.py
CMD ["python", "main.py"]
