import streamlit as st
import requests
import re
import markdown

st.set_page_config(page_title="ChatGPT UI Clone with Reasoning", page_icon="🤖", layout="centered")

# Initialize dark mode in session_state
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

# Sidebar toggle for dark/light mode
with st.sidebar:
    st.title("Settings")
    mode_text = "🌙 Dark Mode" if not st.session_state.dark_mode else "☀️ Light Mode"
    st.button(mode_text, on_click=toggle_dark_mode)

# CSS styles (same as your original for dark/light modes)
dark_css = """
<style>
body, .main {
    background-color: #202123;
    color: #d7dadc;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
}
.chat-container {
    max-width: 700px;
    margin: 0 auto 40px;
    padding: 10px 20px 80px;
    overflow-wrap: break-word;
}
.message {
    display: flex;
    max-width: 75%;
    padding: 12px 16px;
    border-radius: 20px;
    margin: 6px 0;
    font-size: 15px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    flex-direction: column;
}
.user {
    background-color: #0b5fff;
    color: white;
    margin-left: auto;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 10px rgb(11 95 255 / 0.3);
}
.assistant {
    background-color: #343541;
    color: #d7dadc;
    border-bottom-left-radius: 4px;
    box-shadow: 0 2px 10px rgb(52 53 65 / 0.7);
}
.section-label {
    font-weight: 700;
    margin-top: 8px;
    margin-bottom: 4px;
    font-size: 14px;
    color: #8ab4f8;
}
textarea {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 15px;
    padding: 12px;
    border-radius: 8px;
    border: none;
    resize: none;
    width: 100%;
    background-color: #333541;
    color: #d7dadc;
    outline: none;
}
textarea:focus {
    border: 1px solid #0b5fff;
}
button {
    background-color: #0b5fff;
    color: white;
    padding: 12px 20px;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    margin-top: 8px;
    width: 100%;
}
button:hover {
    background-color: #0748c7;
}
footer {
    display: none;
}
</style>
"""

light_css = """
<style>
body, .main {
    background-color: #fff;
    color: #202123;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
}
.chat-container {
    max-width: 700px;
    margin: 0 auto 40px;
    padding: 10px 20px 80px;
    overflow-wrap: break-word;
}
.message {
    display: flex;
    max-width: 75%;
    padding: 12px 16px;
    border-radius: 20px;
    margin: 6px 0;
    font-size: 15px;
    line-height: 1.5;
    white-space: pre-wrap;
    word-break: break-word;
    flex-direction: column;
}
.user {
    background-color: #0366d6;
    color: white;
    margin-left: auto;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 10px rgb(3 102 214 / 0.3);
}
.assistant {
    background-color: #f5f5f5;
    color: #202123;
    border-bottom-left-radius: 4px;
    box-shadow: 0 2px 10px rgb(245 245 245 / 0.7);
}
.section-label {
    font-weight: 700;
    margin-top: 8px;
    margin-bottom: 4px;
    font-size: 14px;
    color: #0366d6;
}
textarea {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 15px;
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #ccc;
    resize: none;
    width: 100%;
    background-color: white;
    color: #202123;
    outline: none;
}
textarea:focus {
    border: 1px solid #0366d6;
}
button {
    background-color: #0366d6;
    color: white;
    padding: 12px 20px;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    margin-top: 8px;
    width: 100%;
}
button:hover {
    background-color: #024a9f;
}
footer {
    display: none;
}
</style>
"""

# Apply chosen CSS based on dark_mode state
st.markdown(dark_css if st.session_state.dark_mode else light_css, unsafe_allow_html=True)

API_URL = "http://127.0.0.1:8000/chat"  # Your reasoning model API endpoint

# Initialize chat history with system prompt instructing the reasoning output format
if "messages" not in st.session_state or not st.session_state.messages:
    st.session_state.messages = [
        {
            "role": "system",
            "content": (
                "You are a reasoning assistant. For every user query, "
                "answer with three sections labeled exactly: "
                "'Thought:', 'Reasoning:', and 'Final Answer:'. "
                "Provide your detailed chain-of-thought in the 'Thought:' section, "
                "your step-by-step explanation in 'Reasoning:', "
                "and your concise final answer in 'Final Answer:'."
            )
        }
    ]

def render_message(role, content):
    """Render user or assistant message with custom styling and markdown."""
    if role == "user":
        st.markdown(f'<div class="message user">{content}</div>', unsafe_allow_html=True)
    else:
        # Parse the assistant's content for Thought, Reasoning, Final Answer sections
        thought = reasoning = final = None
        
        # Use regex to extract sections; make it case-insensitive and robust
        thought_match = re.search(r"Thought:(.*?)(?:Reasoning:|$)", content, re.S | re.I)
        reasoning_match = re.search(r"Reasoning:(.*?)(?:Final Answer:|$)", content, re.S | re.I)
        final_match = re.search(r"Final Answer:(.*)", content, re.S | re.I)

        thought = thought_match.group(1).strip() if thought_match else None
        reasoning = reasoning_match.group(1).strip() if reasoning_match else None
        final = final_match.group(1).strip() if final_match else content.strip()

        # Render each section with label
        sections = []
        if thought:
            sections.append(f'<div class="section-label">Thought:</div>{markdown.markdown(thought, extensions=["fenced_code", "codehilite"])}')
        if reasoning:
            sections.append(f'<div class="section-label">Reasoning:</div>{markdown.markdown(reasoning, extensions=["fenced_code", "codehilite"])}')
        if final:
            sections.append(f'<div class="section-label">Final Answer:</div>{markdown.markdown(final, extensions=["fenced_code", "codehilite"])}')

        full_html = '<div class="message assistant">' + "".join(sections) + "</div>"
        st.markdown(full_html, unsafe_allow_html=True)

# Render chat container and previous messages
st.markdown('<div class="chat-container">', unsafe_allow_html=True)
for msg in st.session_state.messages:
    render_message(msg["role"], msg["content"])
st.markdown('</div>', unsafe_allow_html=True)

# Chat input form
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area("Your message:", height=80, key="input")
    submitted = st.form_submit_button("Send")

if submitted and user_input.strip():
    # Append user input
    st.session_state.messages.append({"role": "user", "content": user_input})

    # Send to backend API - no streaming for simplicity and better parsing
    try:
        payload = {"messages": st.session_state.messages, "max_new_tokens": 200}
        response = requests.post(API_URL, json=payload, timeout=60)
        if response.status_code == 200:
            full_text = response.json().get("response", "").strip()
        else:
            full_text = f"Error {response.status_code}: {response.text}"
    except Exception as e:
        full_text = f"Request error: {e}"

    # Append assistant reply to session
    st.session_state.messages.append({"role": "assistant", "content": full_text})

    # Refresh UI with new messages
    st.rerun()
