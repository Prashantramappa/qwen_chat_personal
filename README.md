# Qwen MLX Chat App (Streamlit + FastAPI)- in MAC local

This project connects a FastAPI backend (Qwen model) with a Streamlit frontend to create a lightweight local chatbot.

🚀 Features

Runs Qwen3-4B-Thinking-2507-5bit locally with mlx_lm.

FastAPI backend serving /chat endpoint.

Streamlit frontend UI for chatting.

Simple rule-based responses for basic questions (hello, who are you?, etc.) to keep it responsive.

CORS enabled so Streamlit can call the API.

📦 Installation

Clone this repo

git clone https://github.com/Prashantramappa/qwen_chat_personal.git
cd <your-repo-name>


Create & activate virtual environment

python3 -m venv .venv
source .venv/bin/activate   # macOS/Linux
.venv\Scripts\activate      # Windows


Install dependencies

pip install -r requirements.txt


Example requirements.txt:

fastapi
uvicorn
pydantic
streamlit
mlx-lm

▶️ Run the Backend (FastAPI)

Start the API server:

uvicorn app:app --reload --port 8000


API will be live at: http://localhost:8000

Test with curl:

curl -X POST "http://localhost:8000/chat" \
-H "Content-Type: application/json" \
-d '{"messages":[{"role":"user","content":"Hello"}]}'

💻 Run the Frontend (Streamlit)

In a separate terminal:

streamlit run streamlit_app.py --server.port 8501


Open browser: http://localhost:8501

✅ Example Usage

User: Hello

Assistant: "Hi there! How can I help you today?"

User: Who are you?

Assistant: "I’m your local Qwen MLX assistant running with FastAPI + Streamlit."

User: Tell me something else

Assistant: [Model-generated response]

That’s it 🎯.
You just run FastAPI (backend) + Streamlit (frontend), and they’ll talk to each other.
