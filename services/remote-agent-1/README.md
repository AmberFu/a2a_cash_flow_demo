# Remote Agent 1（Weather Remote Agent）

這個服務提供簡易的天氣摘要能力。每次呼叫時會透過「城市天氣變數產生器」
隨機建立一組氣溫、濕度、風速、降雨、空氣品質與可選的特殊天氣描述，並模擬
LLM 統整為繁體中文的行前提醒文字。此產生器會在未來串接 MCP 時替換為實際資
料來源，現在的目的是提供 Root Agent 可測試的 HTTP 介面。

## 目錄

- [環境需求](#環境需求)
- [啟動方式](#啟動方式)
- [API 介面](#api-介面)
- [測試指引](#測試指引)

## 環境需求

- Python 3.11+
- 依賴套件列在 `requirements.txt`
- 可選環境變數：
  - `PORT`（預設 `50001`）

## 啟動方式

### 1. 於本機啟動（適合直接測試）

```bash
cd services/remote-agent-1
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/main.py
```

服務預設會在 `http://127.0.0.1:50001` 提供 API。

### 2. 使用 Dockerfile 建置

```bash
cd services/remote-agent-1
docker build -t remote-agent-1:local .
docker run --rm -p 50001:50001 remote-agent-1:local
```

## API 介面

### `GET /`

- 功能：檢查服務狀態。
- 範例：

```bash
curl http://127.0.0.1:50001/
```

### `POST /weather/report`

- 功能：輸入城市、日期與時間區段，取得隨機天氣摘要。
- 請求範例：

```bash
curl -X POST http://127.0.0.1:50001/weather/report \
  -H "Content-Type: application/json" \
  -d '{
    "city": "台北",
    "date": "2024-09-15",
    "time_range": "上午"
  }'
```

- 回應範例：

```json
{
  "city": "台北",
  "date": "2024-09-15",
  "time_range": "上午",
  "variables": {
    "temperature_c": 30.4,
    "humidity_percent": 78,
    "wind_speed_kmh": 12.5,
    "precipitation_chance_percent": 42,
    "precipitation_mm": 6.3,
    "air_quality": "普通",
    "special_weather": "午後雷陣雨"
  },
  "summary": "氣溫 30.4 度，降雨機率 42%，相對濕度 78%，風速 12.5 公里/小時，預估降雨量 6.3 毫米，空氣品質 普通。留意特殊現象：午後雷陣雨。整體而言，在 2024-09-15 上午 整體天氣狀況是短暫陣雨。"
}
```

## 測試指引

1. **直接打 Weather Remote Agent**：
   - 依「啟動方式」啟動後，使用上述 `curl` 命令即可取得隨機天氣結果。
   - 重複呼叫即可看到氣象指標與摘要內容的隨機變化。

2. **透過 Root Agent 串接驗證**：
   - 在另一個終端啟動 Weather Remote Agent 並確保 `PORT=50001`（或在 Root Agent 中調整 `REMOTE1_URL`）。
   - 於專案根目錄啟動 Root Agent：
     ```bash
     cd services/root-agent
     python -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     export REMOTE1_URL="http://127.0.0.1:50001"
     python app/main.py
     ```
   - 送出 Root Agent 任務即可觸發對 Weather Remote Agent 的 HTTP 呼叫：
     ```bash
     curl -X POST http://127.0.0.1:50000/tasks \
       -H "Content-Type: application/json" \
       -d '{"loan_case_id": "demo-case-001"}'
     ```
   - 在 Root Agent 與 Weather Remote Agent 終端觀察日誌，可確認回呼行為與產出的天氣摘要文字。

以上步驟提供手動驗證方式；本次需求未新增自動化測試。
