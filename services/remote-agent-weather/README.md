# Weather Remote Agent

This service simulates a weather-specialised remote agent that can be orchestrated by the root agent. It does not call
external APIs; instead, it derives deterministic forecasts from a curated knowledge base so the demo can run without
network access.

## Features

- FastAPI application exposing a health check (`GET /`) and an advisory endpoint (`POST /weather/advice`).
- Deterministic forecast generator seeded by location and travel date.
- Preference-aware recommendations that can be used by downstream agents.

## Running locally

```bash
cd services/remote-agent-weather
python -m uvicorn app.main:APP --reload --host 0.0.0.0 --port 50010
```

The Dockerfile can be used to build a container image for Kubernetes deployments. Remember to update `BASE_IMAGE` with a
registry that is accessible from your environment.

## Example request

```bash
curl -X POST \
     http://localhost:50010/weather/advice \
     -H "Content-Type: application/json" \
     -d '{
           "location": "Taipei",
           "travel_date": "2024-07-01",
           "unit": "metric",
           "preferences": {
             "preferred_condition": "晴朗",
             "max_precipitation_percent": 40
           }
         }'
```

## Tests

Install the lightweight dev dependencies and execute pytest:

```bash
cd services/remote-agent-weather
pip install -r requirements-dev.txt
pytest
```

The test suite covers both the health check endpoint and the advisory generator, ensuring deterministic output for known
locations and appropriate validation for unsupported regions.
