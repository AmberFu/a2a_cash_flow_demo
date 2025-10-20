# Remote Agent 1（Weather Remote Agent）

這個服務提供決定性的台灣主要城市天氣建議，方便 Root Agent
在不依賴外部氣象 API 的情況下執行旅遊規劃。回應會根據地點、旅遊日期與
呼叫者傳入的偏好條件，產生簡潔的行前提醒文字。

## 目錄

- [環境需求](#環境需求)
- [啟動方式](#啟動方式)
- [API 介面](#api-介面)
- [測試指引](#測試指引)

## 環境需求

- Python 3.11+
- 依賴套件列在 `requirements.txt`
- 必要環境變數：
  - `PORT`（預設 `50001`）
  - `LLM_PROVIDER`（預設 `bedrock`）
  - `LLM_MODEL_ID`（預設 `anthropic.claude-3-sonnet-20240229-v1:0`）

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

- 功能：檢查服務狀態並列出支援的地點。
- 範例：

```bash
curl http://127.0.0.1:50001/
```

### `POST /weather/advice`

- 功能：依照地點與日期回傳建議。
- 請求範例：

```bash
curl -X POST http://127.0.0.1:50001/weather/advice \
  -H "Content-Type: application/json" \
  -d '{
    "location": "taipei",
    "travel_date": "2024-09-15",
    "unit": "metric",
    "preferences": {
      "preferred_condition": "晴朗",
      "max_precipitation_percent": 40
    }
  }'
```

- 回應範例（節錄）：

```json
{
  "location": "taipei",
  "travel_date": "2024-09-15",
  "temperature": 29.0,
  "unit": "°C",
  "condition": "晴時多雲",
  "precipitation_chance": 48,
  "advisory": "...",
  "provider": "bedrock",
  "model": "anthropic.claude-3-sonnet-20240229-v1:0"
}
```

## 測試指引

1. **直接打 Weather Remote Agent**：
   - 依「啟動方式」啟動後，使用上方 `curl` 範例即可快速驗證。
   - 可更換 `location`（taipei、taichung、tainan 等）與 `unit`（metric/imperial）觀察輸出差異。

2. **透過 Root Agent 串接驗證**：
   - 於專案根目錄建立並啟動 Root Agent：
     ```bash
     cd services/root-agent
     python -m venv .venv
     source .venv/bin/activate
     pip install -r requirements.txt
     export REMOTE1_URL="http://127.0.0.1:50001"
     python app/main.py
     ```
   - 另開終端啟動 Weather Remote Agent（確保 `PORT=50001` 或調整 `REMOTE1_URL`）。
   - 呼叫 Root Agent 的 `POST /tasks`，可觸發內部流程並查詢任務：
     ```bash
     curl -X POST http://127.0.0.1:50000/tasks \
       -H "Content-Type: application/json" \
       -d '{"loan_case_id": "demo-case-001"}'
     ```
   - Root Agent 執行後會依流程向 Remote Agent 請求天氣建議，再配合其他 Agent 生成最終結果。可持續觀察 Root Agent 的日誌以確認呼叫成功。

以上步驟提供手動驗證方式；本次需求未新增自動化測試。
