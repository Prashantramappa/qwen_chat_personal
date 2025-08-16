# app.py
# ChatGPT-like Streamlit UI for a local LLM
# Fixed to handle backend "response" key, hide <think>, and show temporary thinking line.

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
            "You are a thinking model. Your purpose is to analyze, synthesize, and evaluate information to provide insightful and well-reasoned responses. Focus on the core of the query, delivering clear, concise, and creative solutions without unnecessary preamble. Prioritize logic, evidence, and intellectual rigor in all outputs.You are a helpful, concise assistant. Answer clearly and directly."
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
    """Strip hidden reasoning (<think>...</think>) and trim output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


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
        mp["temperature"] = st.slider("Temperature", 0.0, 2.0, mp["temperature"], 0.01)
        mp["top_p"] = st.slider("Top-p", 0.0, 1.0, mp["top_p"], 0.01)
        mp["max_tokens"] = st.number_input(
            "Max tokens", min_value=1, max_value=128000, value=mp["max_tokens"], step=64
        )
        seed_in = st.text_input("Seed (optional, blank for random)", value=str(mp.get("seed") or ""))
        mp["seed"] = int(seed_in) if seed_in.strip().isdigit() else None
        mp["stream"] = st.toggle("Stream tokens", value=mp["stream"])

    with st.expander("System prompt", expanded=False):
        st.session_state.system_prompt = st.text_area(
            "System message",
            st.session_state.system_prompt,
            height=120,
            help="Prime the assistant's behavior for this chat.",
        )

    st.divider()
    colA, colB = st.columns(2)
    with colA:
        if st.button("🆕 New chat", use_container_width=True):
            reset_chat()
            st.rerun()
    with colB:
        if st.button("⏹️ Stop", type="secondary", use_container_width=True):
            st.session_state.stop_requested = True

    st.divider()
    export = st.download_button(
        "⬇️ Export chat (JSON)",
        data=json.dumps(st.session_state.messages, ensure_ascii=False, indent=2),
        file_name="chat_history.json",
        mime="application/json",
        use_container_width=True,
    )
    uploaded = st.file_uploader("⬆️ Import chat (JSON)", type=["json"])
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
user_prompt = st.chat_input(f"Message {DISPLAY_NAME}…")
if user_prompt:
    st.session_state.stop_requested = False
    st.session_state.last_user = user_prompt

    add_to_history("user", user_prompt)
    render_message("user", user_prompt)

    with st.chat_message("assistant"):
        placeholder = st.empty()
        thinking_placeholder = st.empty()
        assembled = ""
        last_flush = 0.0

        # Show temporary "thinking..."
        thinking_placeholder.markdown("_Thinking…_")

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
            now = time.perf_counter()
            if now - last_flush >= UPDATE_THROTTLE_SEC:
                placeholder.markdown(assembled)
                last_flush = now

        thinking_placeholder.empty()  # remove once response is done

        final_text = _clean_response(assembled.strip())
        placeholder.markdown(final_text if final_text else "_(no content)_")
    add_to_history("assistant", final_text)

# Regenerate last reply
if st.session_state.last_user and st.button("🔁 Regenerate response", type="secondary"):
    if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
        st.session_state.messages.pop()
    st.rerun()







# # app.py
# # ChatGPT-like Streamlit UI for a local LLM
# # Uses your exact constants and a ChatGPT-style layout.

# import json
# import time
# from typing import Dict, Generator, List, Optional

# import requests
# import streamlit as st

# # ===== Required constants (keep EXACT) =====
# API_URL = "http://127.0.0.1:8001/chat"   # keep exact
# STREAM_TIMEOUT = 120
# UPDATE_THROTTLE_SEC = 0.05
# MODEL_NAME = "Qwen"
# # ==========================================

# DISPLAY_NAME = "QwenMLP-LocalGPT model"   # App-facing name only

# # -------- Helpers --------
# def _init_state():
#     if "messages" not in st.session_state:
#         st.session_state.messages: List[Dict[str, str]] = []
#     if "system_prompt" not in st.session_state:
#         st.session_state.system_prompt = (
#             "You are a helpful, concise assistant. Answer clearly and directly."
#         )
#     if "model_params" not in st.session_state:
#         st.session_state.model_params = {
#             "temperature": 0.7,
#             "top_p": 0.95,
#             "max_tokens": 1024,
#             "seed": None,
#             "stream": True,
#         }
#     if "last_user" not in st.session_state:
#         st.session_state.last_user: Optional[str] = None
#     if "stop_requested" not in st.session_state:
#         st.session_state.stop_requested = False


# def _extract_content_from_json(data: dict) -> Optional[str]:
#     """
#     Handle common response shapes:
#     - OpenAI-style: choices[0].message.content (final) or choices[0].delta.content (streaming chunk)
#     - Generic: data['content'] / data['text'] / data['token']
#     """
#     try:
#         if "choices" in data and data["choices"]:
#             ch0 = data["choices"][0]
#             if "delta" in ch0 and "content" in ch0["delta"]:
#                 return ch0["delta"]["content"]
#             if "message" in ch0 and "content" in ch0["message"]:
#                 return ch0["message"]["content"]
#         for k in ("content", "text", "token"):
#             if k in data and isinstance(data[k], str):
#                 return data[k]
#     except Exception:
#         pass
#     return None


# def _parse_stream_line(line: str) -> Optional[str]:
#     """
#     Accepts raw SSE or newline-delimited JSON tokens.
#     - Strips optional 'data:' prefix
#     - Returns a content chunk or None
#     - Skips '[DONE]'
#     """
#     if not line:
#         return None
#     if line.startswith("data:"):
#         line = line[5:].strip()
#     if line.strip() == "[DONE]":
#         return None
#     # Try JSON; fall back to raw text
#     try:
#         obj = json.loads(line)
#         return _extract_content_from_json(obj)
#     except Exception:
#         # If server streams bare text tokens
#         return line


# def stream_chat_completion(
#     messages: List[Dict[str, str]],
#     temperature: float,
#     top_p: float,
#     max_tokens: int,
#     seed: Optional[int],
#     stream: bool,
# ) -> Generator[str, None, None]:
#     """
#     POST to API_URL and yield chunks if streaming, otherwise yield final text.
#     Robust to different provider payloads (OpenAI-like or generic).
#     """
#     payload = {
#         "model": MODEL_NAME,
#         "messages": messages,
#         "temperature": temperature,
#         "top_p": top_p,
#         "max_tokens": max_tokens,
#         "stream": stream,
#     }
#     if seed is not None and seed != "":
#         payload["seed"] = seed

#     headers = {"Content-Type": "application/json"}

#     try:
#         with requests.post(
#             API_URL,
#             headers=headers,
#             json=payload,
#             stream=True,  # keep streaming True so we can handle chunks iteratively
#             timeout=STREAM_TIMEOUT,
#         ) as resp:
#             resp.raise_for_status()
#             if stream:
#                 for raw in resp.iter_lines(decode_unicode=True):
#                     if st.session_state.get("stop_requested"):
#                         break
#                     if raw is None:
#                         continue
#                     chunk = _parse_stream_line(raw)
#                     if chunk:
#                         yield chunk
#             else:
#                 data = resp.json()
#                 final = _extract_content_from_json(data)
#                 if final:
#                     yield final
#     except requests.exceptions.RequestException as e:
#         yield f"**[Connection error]** {e}"


# def render_message(role: str, content: str):
#     with st.chat_message(role):
#         st.markdown(content)


# def add_to_history(role: str, content: str):
#     st.session_state.messages.append({"role": role, "content": content})


# def reset_chat():
#     st.session_state.messages = []
#     st.session_state.last_user = None
#     st.session_state.stop_requested = False


# # -------- App UI --------
# st.set_page_config(page_title=DISPLAY_NAME, page_icon="💬", layout="wide")
# _init_state()

# # Sidebar – Model parameters & tools
# with st.sidebar:
#     st.markdown(f"### {DISPLAY_NAME}")
#     st.caption("Local ChatGPT-style UI with tunable params")

#     with st.expander("Model parameters", expanded=True):
#         mp = st.session_state.model_params
#         mp["temperature"] = st.slider("Temperature", 0.0, 2.0, mp["temperature"], 0.01)
#         mp["top_p"] = st.slider("Top-p", 0.0, 1.0, mp["top_p"], 0.01)
#         mp["max_tokens"] = st.number_input(
#             "Max tokens", min_value=1, max_value=128000, value=mp["max_tokens"], step=64
#         )
#         seed_in = st.text_input("Seed (optional, blank for random)", value=str(mp.get("seed") or ""))
#         mp["seed"] = int(seed_in) if seed_in.strip().isdigit() else None
#         mp["stream"] = st.toggle("Stream tokens", value=mp["stream"])

#     with st.expander("System prompt", expanded=False):
#         st.session_state.system_prompt = st.text_area(
#             "System message",
#             st.session_state.system_prompt,
#             height=120,
#             help="Prime the assistant's behavior for this chat.",
#         )

#     st.divider()
#     colA, colB = st.columns(2)
#     with colA:
#         if st.button("🆕 New chat", use_container_width=True):
#             reset_chat()
#             st.rerun()
#     with colB:
#         if st.button("⏹️ Stop", type="secondary", use_container_width=True):
#             st.session_state.stop_requested = True

#     st.divider()
#     # Export / Import
#     export = st.download_button(
#         "⬇️ Export chat (JSON)",
#         data=json.dumps(st.session_state.messages, ensure_ascii=False, indent=2),
#         file_name="chat_history.json",
#         mime="application/json",
#         use_container_width=True,
#     )
#     uploaded = st.file_uploader("⬆️ Import chat (JSON)", type=["json"])
#     if uploaded:
#         try:
#             st.session_state.messages = json.load(uploaded)
#             st.success("Chat imported.")
#         except Exception as e:
#             st.error(f"Import failed: {e}")

# # Main header
# st.markdown(
#     f"""
# <div style="display:flex;align-items:center;gap:.5rem;">
#   <div style="font-size:1.6rem;font-weight:700;">{DISPLAY_NAME}</div>
#   <div style="opacity:.65;"> · model: <code>{MODEL_NAME}</code></div>
# </div>
# """,
#     unsafe_allow_html=True,
# )
# st.caption("Chat interface with streaming, history, and tunable parameters.")

# # Ensure system prompt is first message (if set and not yet added)
# if st.session_state.system_prompt:
#     if not st.session_state.messages or st.session_state.messages[0]["role"] != "system":
#         st.session_state.messages.insert(0, {"role": "system", "content": st.session_state.system_prompt})
#     else:
#         st.session_state.messages[0]["content"] = st.session_state.system_prompt

# # Render existing history
# for msg in st.session_state.messages:
#     if msg["role"] == "system":
#         # Hide system message inline; ChatGPT keeps it hidden.
#         continue
#     render_message(msg["role"], msg["content"])

# # Chat input at bottom
# user_prompt = st.chat_input(f"Message {DISPLAY_NAME}…")
# if user_prompt:
#     st.session_state.stop_requested = False
#     st.session_state.last_user = user_prompt

#     # Append + render user message
#     add_to_history("user", user_prompt)
#     render_message("user", user_prompt)

#     # Assistant streaming response
#     with st.chat_message("assistant"):
#         placeholder = st.empty()
#         assembled = ""
#         last_flush = 0.0

#         # Build message list (system + full history)
#         msg_payload = st.session_state.messages

#         for chunk in stream_chat_completion(
#             messages=msg_payload,
#             temperature=st.session_state.model_params["temperature"],
#             top_p=st.session_state.model_params["top_p"],
#             max_tokens=st.session_state.model_params["max_tokens"],
#             seed=st.session_state.model_params["seed"],
#             stream=st.session_state.model_params["stream"],
#         ):
#             assembled += chunk
#             now = time.perf_counter()
#             if now - last_flush >= UPDATE_THROTTLE_SEC:
#                 placeholder.markdown(assembled)
#                 last_flush = now

#         # Final flush
#         placeholder.markdown(assembled if assembled.strip() else "_(no content)_")
#     add_to_history("assistant", assembled.strip())

# # Regenerate last reply (like ChatGPT)
# if st.session_state.last_user and st.button("🔁 Regenerate response", type="secondary"):
#     # Remove last assistant message if present, resend last user prompt
#     if st.session_state.messages and st.session_state.messages[-1]["role"] == "assistant":
#         st.session_state.messages.pop()
#     st.rerun()
