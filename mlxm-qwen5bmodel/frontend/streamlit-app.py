import streamlit as st
import requests
import time
import markdown

st.set_page_config(page_title="QwenChat Pro", page_icon="🤖", layout="centered")

# Dark mode toggle
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

st.button("Toggle Dark Mode 🌙" if not st.session_state.dark_mode else "Toggle Light Mode ☀️", on_click=toggle_dark_mode)

dark_css = """
<style>
body {
    background-color: #0c111b;
    color: #c9d1d9;
}
.chat-container {
    max-width: 700px;
    margin: 20px auto;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.user-msg {
    background: #1e90ff;
    color: white;
    padding: 12px;
    border-radius: 18px 18px 0 18px;
    margin-left: auto;
    max-width: 70%;
    word-wrap: break-word;
    box-shadow: 0 4px 6px rgba(30, 144, 255, 0.4);
}
.bot-msg {
    background: #30363d;
    color: #c9d1d9;
    padding: 12px;
    border-radius: 18px 18px 18px 0;
    max-width: 70%;
    word-wrap: break-word;
    box-shadow: 0 4px 6px rgba(48,54,61,0.5);
}
</style>
"""

light_css = """
<style>
body {
    background-color: white;
    color: black;
}
.chat-container {
    max-width: 700px;
    margin: 20px auto;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.user-msg {
    background: #007bff;
    color: white;
    padding: 12px;
    border-radius: 18px 18px 0 18px;
    margin-left: auto;
    max-width: 70%;
    word-wrap: break-word;
    box-shadow: 0 4px 6px rgba(0,123,255,0.4);
}
.bot-msg {
    background: #f1f0f0;
    color: black;
    padding: 12px;
    border-radius: 18px 18px 18px 0;
    max-width: 70%;
    word-wrap: break-word;
    box-shadow: 0 4px 6px rgba(200,200,200,0.5);
}
</style>
"""

st.markdown(dark_css if st.session_state.dark_mode else light_css, unsafe_allow_html=True)

API_URL = "http://127.0.0.1:8000/chat"

if "messages" not in st.session_state:
    st.session_state.messages = []

def stream_response(messages):
    payload = {"messages": messages, "max_new_tokens": 200}
    try:
        response = requests.post(API_URL, json=payload, timeout=60)
        if response.status_code == 200:
            full_text = response.json().get("response", "")
            # Simulate typing effect
            for i in range(len(full_text)):
                yield full_text[:i+1]
                time.sleep(0.02)
        else:
            yield f"Error {response.status_code}: {response.text}"
    except Exception as e:
        yield f"Request error: {e}"

def render_message(role, content):
    if role == "user":
        st.markdown(f'<div class="user-msg">{content}</div>', unsafe_allow_html=True)
    else:
        # Render markdown safely for bot
        md_html = markdown.markdown(content, extensions=['fenced_code', 'codehilite'])
        st.markdown(f'<div class="bot-msg">{md_html}</div>', unsafe_allow_html=True)

with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area("Your message:", height=70)
    submitted = st.form_submit_button("Send")

if submitted and user_input.strip():
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Stream the bot response
    bot_msg_placeholder = st.empty()
    bot_response = ""
    for chunk in stream_response(st.session_state.messages):
        bot_response = chunk
        bot_msg_placeholder.markdown(f'<div class="bot-msg">{markdown.markdown(bot_response)}</div>', unsafe_allow_html=True)

    st.session_state.messages.append({"role": "assistant", "content": bot_response})

st.markdown("<div class='chat-container'>", unsafe_allow_html=True)
for msg in st.session_state.messages:
    render_message(msg["role"], msg["content"])
st.markdown("</div>", unsafe_allow_html=True)

# Auto scroll to bottom trick: Rerun when new message added
if submitted:
    st.rerun()

