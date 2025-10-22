# Summary Agent Service

Summary Agent 整合了 Weather Remote Agent 與 Transport Remote Agent 的結果，根據使用者提供的出發地、目的地、旅遊日期與偏好，產出具體的乘車建議與天氣提醒。

## 專案結構

- `app/config.py`：讀取環境變數並建立設定物件。
- `app/models.py`：定義與 Remote Agent 對應的 Pydantic 模型（包含 `date` 與 `time` 欄位）。
- `app/summarizer.py`：整理交通資訊並挑選三個最佳班次，依據天氣數據產生提醒。
- `app/main.py`：FastAPI 入口，提供健康檢查與 `/summaries` API。
- `requirements.txt`：服務所需的依賴。

## 環境變數

| 變數 | 說明 | 預設值 |
| --- | --- | --- |
| `PORT` | 服務監聽的埠號 | `50003` |
| `LLM_PROVIDER` | 模型提供者名稱（例如 `bedrock`、`openai`） | `bedrock` |
| `LLM_MODEL_ID` | 指定使用的模型 ID | `anthropic.claude-3-haiku-20240307-v1:0` |

## API 介面

### `GET /`

回傳服務狀態與目前使用的模型設定。

### `POST /summaries`

請求格式如下，所有日期皆採 `YYYY-MM-DD` 格式，時間採 24 小時制：

```json
{
  "task_id": "demo-task",
  "user_requirement": {
    "origin": "台北",
    "destination": "高雄",
    "travel_date": "2024-08-25",
    "desired_arrival_time": "14:30",
    "transport_note": "希望靠近下午會議"
  },
  "weather_report": {
    "city": "高雄",
    "date": "2024-08-25",
    "time_range": "下午",
    "summary": "午後高溫且有局部短暫陣雨",
    "variables": {
      "temperature_c": 32.1,
      "humidity_percent": 70,
      "wind_speed_kmh": 18.5,
      "precipitation_chance_percent": 55,
      "precipitation_mm": 4.3,
      "air_quality": "普通",
      "special_weather": "午後雷陣雨"
    }
  },
  "transport": {
    "destination": "高雄",
    "requested_arrival_time": "14:30",
    "date": "2024-08-25",
    "plans": [
      {
        "stations": { "origin": "台北", "destination": "高雄" },
        "time": { "departure": "08:10", "arrival": "12:20" },
        "date": "2024-08-25",
        "pricing_and_service": { "price": 1490, "service_number": "T123" }
      }
    ]
  }
}
```

成功回傳會包含：

- `overview`：旅程摘要與注意事項。
- `recommended_plans`：三個最佳班次（旅程最短、票價最省、抵達時間最接近）。
- `weather_summary`：Weather Agent 的摘要。
- `weather_reminders`：依據溫度、降雨機率等資訊產出的提醒（例如攜帶雨具、防曬、補充水分）。

## 本地啟動

```bash
uvicorn app.main:app --host 0.0.0.0 --port 50003 --reload
```

啟動後可用下列指令測試：

```bash
curl -X POST http://127.0.0.1:50003/summaries \
  -H "Content-Type: application/json" \
  -d @payload.json
```

請將上述 JSON 內容存成 `payload.json` 再執行測試。

