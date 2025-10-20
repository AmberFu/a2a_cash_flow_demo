# Build image for the weather remote agent. Replace BASE_IMAGE with a registry
# available in your environment.
ARG BASE_IMAGE=182399696164.dkr.ecr.ap-southeast-1.amazonaws.com/python-base/python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd -m appuser

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app/ ./

EXPOSE 50010

USER appuser
CMD ["python", "main.py"]
