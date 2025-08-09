# app.py
import threading
import uvicorn
import webview
from backend import app as fastapi_app

def start_backend():
    uvicorn.run(fastapi_app, host="127.0.0.1", port=8000)

if __name__ == "__main__":
    threading.Thread(target=start_backend, daemon=True).start()
    webview.create_window("Local Qwen Chat", "frontend/index.html", width=800, height=600)
    webview.start()
