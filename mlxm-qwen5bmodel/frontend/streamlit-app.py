# app.py
# ChatGPT-like Streamlit UI for a local LLM
# Fixed to handle backend "response" key, hide <think>, show thinking in an expander
# and avoid StreamlitDuplicateElementId by giving widgets explicit keys.

import json
import re
import time
from typing import Dict, Generator, List, Optional

import requests
import streamlit as st

# ===== Required constants (keep EXACT) =====
API_URL = "http://127.0.0.1:8001/chat"   # keep exact
STREAM_TIMEOUT = 120
UPDATE_THROTTLE_SEC = 0.05
MODEL_NAME = "Qwen"
# ==========================================

DISPLAY_NAME = "QwenMLP-LocalGPT model"   # App-facing name only


# -------- Helpers --------
def _init_state():
    if "messages" not in st.session_state:
        st.session_state.messages: List[Dict[str, str]] = []
    if "system_prompt" not in st.session_state:
        st.session_state.system_prompt = (
            """ You are a thinking model. Your purpose is to operate under the 'Clarity, Accuracy, Velocity' (CAV) protocol. You do not have an identity beyond this function. You do not explain who you are. You simply execute.
Your operational framework is a strict, three-phase process:
Phase 1: Isolate the Core. Instantly analyze the prompt to identify the single, critical question and intent. Disregard all pleasantries, analogies, and extraneous information. Your target is the "question-behind-the-question."
Phase 2: Construct the Chain. Formulate a direct, step-by-step logical path from the core question to the answer. Each link in the chain must be a verifiable fact or a logical deduction. If a path is flawed, discard it and construct a new one. This entire process is internal and silent.
Phase 3: Deliver the Point. Articulate the final answer with maximum precision and brevity. Begin with the most direct answer possible, followed by only the essential bulleted points that support the conclusion. Do not use introductory or concluding phrases.
Execute every query through this protocol. Focus on the core of the query, delivering clear, concise, and creative solutions without unnecessary preamble. 
Prioritize logic, evidence, and intellectual rigor in all outputs. 
You are a helpful, concise assistant. Answer clearly and directly.   """
        )
    if "model_params" not in st.session_state:
        st.session_state.model_params = {
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 1024,
            "seed": None,
            "stream": True,
        }
    if "last_user" not in st.session_state:
        st.session_state.last_user: Optional[str] = None
    if "stop_requested" not in st.session_state:
        st.session_state.stop_requested = False


def _extract_content_from_json(data: dict) -> Optional[str]:
    """
    Handle common response shapes.
    """
    try:
        if "choices" in data and data["choices"]:
            ch0 = data["choices"][0]
            if "delta" in ch0 and "content" in ch0["delta"]:
                return ch0["delta"]["content"]
            if "message" in ch0 and "content" in ch0["message"]:
                return ch0["message"]["content"]

        # Local backends often return "response" or "generated_text"
        for k in ("content", "text", "token", "response", "generated_text"):
            if k in data and isinstance(data[k], str):
                return data[k]
    except Exception:
        pass
    return None


def _clean_response(text: str) -> str:
    """Keep only content after </think> and strip whitespace."""
    # If </think> exists, drop everything before it
    if "</think>" in text:
        return text.split("</think>", 1)[1].strip()
    return text.strip()


def _parse_stream_line(line: str) -> Optional[str]:
    """Parse raw SSE or JSON lines into text chunks."""
    if not line:
        return None
    if line.startswith("data:"):
        line = line[5:].strip()
    if line.strip() == "[DONE]":
        return None
    try:
        obj = json.loads(line)
        return _extract_content_from_json(obj)
    except Exception:
        return line  # fallback: bare text


def _extract_think_and_after(full_text: str) -> (str, str):
    """
    Given the cumulative assembled stream text, return a tuple:
    (thinking_text, after_think_text)
    - thinking_text: everything between an opening <think> (if present) and the first </think> (or the whole text if </think> not seen).
    - after_think_text: text after the first </think> if present, otherwise empty string.
    """
    text = full_text or ""
    # remove a single leading <think> if present
    if "<think>" in text and "</think>" in text:
        before, after = text.split("</think>", 1)
        before = before.split("<think>", 1)[-1]  # remove anything before/including first <think>
        return before, after
    elif "<think>" in text and "</think>" not in text:
        # still inside thinking section
        after_open = text.split("<think>", 1)[1]
        return after_open, ""
    elif "</think>" in text and "<think>" not in text:
        # unexpected: closing without opening - treat everything before closing as thinking
        before, after = text.split("</think>", 1)
        return before, after
    else:
        # no thinking markers at all -> treat as thinking interim (until we see a closing marker)
        return text, ""


def stream_chat_completion(
    messages: List[Dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
    seed: Optional[int],
    stream: bool,
) -> Generator[str, None, None]:
    """POST to API_URL and yield chunks if streaming, otherwise yield final text."""
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if seed is not None and seed != "":
        payload["seed"] = seed

    headers = {"Content-Type": "application/json"}

    try:
        with requests.post(
            API_URL,
            headers=headers,
            json=payload,
            stream=True,
            timeout=STREAM_TIMEOUT,
        ) as resp:
            resp.raise_for_status()
            if stream:
                for raw in resp.iter_lines(decode_unicode=True):
                    if st.session_state.get("stop_requested"):
                        break
                    if raw is None:
                        continue
                    chunk = _parse_stream_line(raw)
                    if chunk:
                        yield chunk
            else:
                data = resp.json()
                final = _extract_content_from_json(data)
                if final:
                    yield final
    except requests.exceptions.RequestException as e:
        yield f"**[Connection error]** {e}"


def render_message(role: str, content: str):
    with st.chat_message(role):
        st.markdown(content)


def add_to_history(role: str, content: str):
    st.session_state.messages.append({"role": role, "content": content})


def reset_chat():
    st.session_state.messages = []
    st.session_state.last_user = None
    st.session_state.stop_requested = False


# -------- App UI --------
st.set_page_config(page_title=DISPLAY_NAME, page_icon="💬", layout="wide")
_init_state()

# Sidebar
with st.sidebar:
    st.markdown(f"### {DISPLAY_NAME}")
    st.caption("Local ChatGPT-style UI with tunable params")

    with st.expander("Model parameters", expanded=True):
        mp = st.session_state.model_params
        mp["temperature"] = st.slider("Temperature", 0.0, 2.0, mp["temperature"], 0.01, key="temp_slider")
        mp["top_p"] = st.slider("Top-p", 0.0, 1.0, mp["top_p"], 0.01, key="topp_slider")
        mp["max_tokens"] = st.number_input(
            "Max tokens", min_value=1, max_value=128000, value=mp["max_tokens"], step=64, key="max_tokens_input"
        )
        seed_in = st.text_input("Seed (optional, blank for random)", value=str(mp.get("seed") or ""), key="seed_input")
        mp["seed"] = int(seed_in) if seed_in.strip().isdigit() else None
        # Keep using st.toggle if your Streamlit supports it; otherwise replace with st.checkbox
        try:
            mp["stream"] = st.toggle("Stream tokens", value=mp["stream"], key="stream_toggle")
        except Exception:
            mp["stream"] = st.checkbox("Stream tokens", value=mp["stream"], key="stream_checkbox")

    with st.expander("System prompt", expanded=False):
        st.session_state.system_prompt = st.text_area(
            "System message",
            st.session_state.system_prompt,
            height=120,
            help="Prime the assistant's behavior for this chat.",
            key="system_prompt_area",
        )

    st.divider()
    colA, colB = st.columns(2)
    with colA:
        if st.button("🆕 New chat", use_container_width=True, key="new_chat_btn"):
            reset_chat()
            st.rerun()
    with colB:
        if st.button("⏹️ Stop", type="secondary", use_container_width=True, key="stop_btn"):
            st.session_state.stop_requested = True

    st.divider()
    export = st.download_button(
        "⬇️ Export chat (JSON)",
        data=json.dumps(st.session_state.messages, ensure_ascii=False, indent=2),
        file_name="chat_history.json",
        mime="application/json",
        use_container_width=True,
        key="export_btn",
    )
    uploaded = st.file_uploader("⬆️ Import chat (JSON)", type=["json"], key="import_uploader")
    if uploaded:
        try:
            st.session_state.messages = json.load(uploaded)
            st.success("Chat imported.")
        except Exception as e:
            st.error(f"Import failed: {e}")

# Main header
st.markdown(
    f"""
<div style="display:flex;align-items:center;gap:.5rem;">
  <div style="font-size:1.6rem;font-weight:700;">{DISPLAY_NAME}</div>
  <div style="opacity:.65;"> · model: <code>{MODEL_NAME}</code></div>
</div>
""",
    unsafe_allow_html=True,
)
st.caption("Chat interface with streaming, history, and tunable parameters.")

# Ensure system prompt is first message
if st.session_state.system_prompt:
    if not st.session_state.messages or st.session_state.messages[0]["role"] != "system":
        st.session_state.messages.insert(0, {"role": "system", "content": st.session_state.system_prompt})
    else:
        st.session_state.messages[0]["content"] = st.session_state.system_prompt

# Render existing history
for msg in st.session_state.messages:
    if msg["role"] == "system":
        continue
    render_message(msg["role"], msg["content"])

# Chat input
user_prompt = st.chat_input(f"Message {DISPLAY_NAME}…", key="chat_input")
if user_prompt:
    st.session_state.stop_requested = False
    st.session_state.last_user = user_prompt

    add_to_history("user", user_prompt)
    render_message("user", user_prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()             # visible answer area
        thinking_expander = st.expander("Internal thinking (click to expand)", expanded=False)
        thinking_area = thinking_expander.empty()  # placeholder inside the expander
        assembled = ""
        last_flush = 0.0

        # Initially show a single small thinking line in main area
        placeholder.markdown("_Thinking…_")

        msg_payload = st.session_state.messages
        for chunk in stream_chat_completion(
            messages=msg_payload,
            temperature=st.session_state.model_params["temperature"],
            top_p=st.session_state.model_params["top_p"],
            max_tokens=st.session_state.model_params["max_tokens"],
            seed=st.session_state.model_params["seed"],
            stream=st.session_state.model_params["stream"],
        ):
            assembled += chunk
            # derive current thinking vs visible parts
            thinking_text, after_think_text = _extract_think_and_after(assembled)

            now = time.perf_counter()
            if now - last_flush >= UPDATE_THROTTLE_SEC:
                # Update the internal thinking expander (strip leading/trailing whitespace)
                thinking_display = thinking_text.strip() or "_(no internal thinking captured yet)_"
                thinking_area.markdown(thinking_display)

                # Update main visible area with anything emitted after </think>
                if after_think_text.strip():
                    placeholder.markdown(after_think_text.strip())
                else:
                    # still thinking — keep temporary line until we have real visible text
                    placeholder.markdown("_Thinking…_")
                last_flush = now

        # finished streaming (or non-stream)
        final_text = _clean_response(assembled.strip())
        # Ensure the expander shows the full thinking content (strip tags)
        final_think, _ = _extract_think_and_after(assembled)
        thinking_area.markdown(final_think.strip() or "_(no internal thinking)_")

        placeholder.markdown(final_text if final_text else "_(no content)_")
    add_to_history("assistant", final_text)
