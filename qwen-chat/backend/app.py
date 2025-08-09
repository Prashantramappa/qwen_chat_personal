from fastapi import FastAPI
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

app = FastAPI()

model_name = "Qwen/Qwen1.5-1.8B"  # 1.5B variant
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")

@app.on_event("startup")
def load_model():
    global model, tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16 if device.type == "mps" else torch.float32,
        device_map={"": device}
    )

@app.get("/chat")
def chat(q: str):
    inputs = tokenizer(q, return_tensors="pt").to(device)
    output = model.generate(**inputs, max_length=200)
    reply = tokenizer.decode(output[0], skip_special_tokens=True)
    return {"response": reply}
