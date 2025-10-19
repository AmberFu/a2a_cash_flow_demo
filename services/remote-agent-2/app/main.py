from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import os

app = FastAPI()
PORT = int(os.environ.get("PORT", 50002))
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "bedrock")
LLM_MODEL_ID = os.environ.get("LLM_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")


@app.get("/")
def status():
    return JSONResponse(
        {
            "status": "OK",
            "agent": "Remote Agent 2",
            "port": PORT,
            "llm_provider": LLM_PROVIDER,
            "llm_model_id": LLM_MODEL_ID,
        }
    )


if __name__ == "__main__":
    # 這裡就用你指定的寫法；注意：reload 在容器內要搭配掛載原始碼才看得到變更
    uvicorn.run(app="main:app", host="0.0.0.0", port=PORT, reload=True)
