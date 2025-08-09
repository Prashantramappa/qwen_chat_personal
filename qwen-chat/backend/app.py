# app.py
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from mlx_lm import load, generate
import os
from typing import List, Dict

# === Config ===
MODEL_NAME = "mlx-community/Qwen3-4B-Thinking-2507-5bit"
CACHE_DIR = "./models"
HF_TOKEN = os.getenv("HF_TOKEN")  # set this in environment or .env

# === FastAPI App ===
app = FastAPI()

# Global vars
model = None
tokenizer = None

# Request schema
class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    max_new_tokens: int = 200

@app.on_event("startup")
async def startup_event():
    global model, tokenizer
    print(f"🚀 Loading model: {MODEL_NAME}")
    model, tokenizer = load(
        MODEL_NAME,
        # MLX automatically uses ~/.cache by default, but we'll use local folder
        local_files_only=False,
    )
    print("✅ Model loaded and ready.")

def stream_generate(prompt: str, max_new_tokens: int):
    """Generator that yields tokens one-by-one."""
    for chunk in generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_new_tokens,
        verbose=False,
        stream=True  # important for token streaming
    ):
        yield chunk

@app.post("/chat")
async def chat(req: ChatRequest):
    prompt = tokenizer.apply_chat_template(
        req.messages,
        add_generation_prompt=True
    )
    return StreamingResponse(
        stream_generate(prompt, req.max_new_tokens),
        media_type="text/plain"
    )
