# Remote Agent 2 - Transport Planner

本文件說明如何在本地環境啟動並測試 Remote Agent 2（交通資訊生成服務）。

## 1. 安裝相依套件

```bash
cd services/remote-agent-2
pip install -r requirements.txt
```

## 2. 使用 Uvicorn 啟動服務

```bash
uvicorn app.main:app --host 0.0.0.0 --port 50002
```

啟動後，FastAPI 服務會監聽 `http://localhost:50002`，同時暴露 `/metrics` 供 Prometheus 讀取。

## 3. 建立測試請求

使用 `curl` 傳送測試資料，注意 `arrival_time` 代表使用者預期抵達時間，生成的班次會確保在該時間前抵達。

```bash
curl -X POST "http://localhost:50002/transport/plans" \
  -H "Content-Type: application/json" \
  -d '{
    "destination": "台南",
    "arrival_time": "16:30:00",
    "date": "2024-07-01",
    "results": 3
  }'
```

回應範例：

```json
{
  "destination": "台南",
  "requested_arrival_time": "16:30:00",
  "date": "2024-07-01",
  "plans": [
    {
      "stations": {
        "origin": "嘉義",
        "destination": "台南"
      },
      "time": {
        "departure": "14:25:00",
        "arrival": "15:50:00"
      },
      "date": "2024-07-01",
      "pricing_and_service": {
        "price": 585,
        "service_number": "T408"
      }
    }
  ]
}
```

## 4. 確認 `/metrics` 可用

```bash
curl -I http://localhost:50002/metrics
```

若返回 `HTTP/1.1 200 OK`，表示 Prometheus metrics 端點正常。

