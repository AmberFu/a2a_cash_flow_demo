# 你在 VPC-only Studio，請用你自己的 ECR 基底鏡像（修改成你有的 tag）
ARG BASE_IMAGE=182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/python-base/python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd -m appuser

# 安裝相依
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 複製程式
COPY app/ ./app

EXPOSE 50003

USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "50003"]
