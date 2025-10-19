# Summary Agent Service

這個資料夾提供 Summary Agent 的示範程式碼。Service 會接收 Weather Agent 與 Train Agent 的結果，並以環境變數指定的 LLM 模型產生摘要。此版本使用 FastAPI stub，主要目的是展示如何為每個 agent 指定獨立模型設定。

## 主要檔案

- `Dockerfile`：建立容器映像，預設啟動 `uvicorn`。
- `requirements.txt`：Python 依賴 (FastAPI + Uvicorn)。
- `app/main.py`：FastAPI 進入點，包含健康檢查與 `/summaries` API。

## 環境變數

| 變數 | 說明 | 預設值 |
| --- | --- | --- |
| `PORT` | 服務監聽的埠號 | `50003` |
| `LLM_PROVIDER` | 模型提供者名稱（例如 `bedrock`、`openai`） | `bedrock` |
| `LLM_MODEL_ID` | 具體模型 ID | `anthropic.claude-3-haiku-20240307-v1:0` |

部署到 Kubernetes 後，可透過 ConfigMap（範例：`kubernetes/configmap-agent-models.yaml`）為 Summary Agent 指定不同的模型。

## API 說明

- `GET /`：健康檢查，回傳目前使用的模型資訊。
- `POST /summaries`：接收 task_id、weather/train 建議與預算等資訊，回傳整理後的建議文字。

## 本地測試

```bash
uvicorn app.main:APP --reload --port 50003
```

然後使用 curl 測試：

```bash
curl -X POST http://127.0.0.1:50003/summaries \
  -H 'Content-Type: application/json' \
  -d '{
        "task_id": "demo-task",
        "weather_advice": "明天高雄小雨，建議攜帶雨具",
        "train_options": ["07:30 自強號", "09:10 普悠瑪"],
        "budget": "1000"
      }'
```
