import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mlx_lm import load, generate
from fastapi.middleware.cors import CORSMiddleware

MODEL_NAME = "mlx-community/Qwen3-4B-Thinking-2507-5bit"

app = FastAPI(title="Qwen MLX Chat API", version="1.0")

# Allow CORS for localhost (for Streamlit to call API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],  # Streamlit default port
    allow_methods=["GET"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    messages: list[dict]
    max_new_tokens: int = 200

model = None
tokenizer = None

@app.on_event("startup")
async def startup_event():
    global model, tokenizer
    try:
        print(f"🚀 Loading model: {MODEL_NAME}")
        model, tokenizer = load(MODEL_NAME)
        print("✅ Model loaded and ready.")
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        raise e

@app.post("/chat")
async def chat(req: ChatRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=500, detail="Model not loaded yet.")

    try:
        prompt = req.messages
        if tokenizer.chat_template is not None:
            prompt = tokenizer.apply_chat_template(
                req.messages, add_generation_prompt=True
            )

        output = generate(
            model,
            tokenizer,
            prompt=prompt,
            verbose=False,
            max_tokens=req.max_new_tokens
        )

        return {"response": output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "Qwen MLX Chat API is running. Use POST /chat to interact."}
