# streamlit_app.py
import streamlit as st
import requests
import json
import re
import markdown
import time
from typing import Optional, Tuple

# ---------------- CONFIG (tweak these) ----------------
API_URL = "http://127.0.0.1:8001/chat"   # change to your streaming endpoint
STREAM_TIMEOUT = 120
MAX_NEW_TOKENS_STREAM = 1024             # token budget for stream
FINISH_TOKENS_INITIAL = 256              # initial tokens for finish attempt
FINISH_TOKENS_INCREMENT = 128            # increase tokens per retry
MAX_FINISH_RETRIES_DEFAULT = 2           # default number of auto-retries
MAX_NEW_TOKENS_SUMMARIZE = 180           # tokens for summarizer call
UPDATE_THROTTLE_SEC = 0.05               # throttle UI updates
# ----------------------------------------------------

st.set_page_config(page_title="ChatGPT-like Streaming (Stable + Retry + Badge)", page_icon="🤖", layout="centered")

# ---------------- UI theme & state ------------------
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = True

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

# Sidebar controls for debug & fallback behavior
with st.sidebar:
    st.title("Settings")
    st.button("☀️ Light Mode" if st.session_state.dark_mode else "🌙 Dark Mode", on_click=toggle_dark_mode)
    st.write("---")
    st.write("Streaming / Fallback")
    ui_stream_debug = st.checkbox("Show raw stream debug", value=False, key="ui_stream_debug")
    ui_model_summarize = st.checkbox("Use model summarizer fallback (extra call)", value=True, key="ui_model_summarize")
    st.write("Auto-finish retry policy")
    auto_retry = st.checkbox("Enable automatic finish retries", value=True, key="ui_auto_retry")
    max_finish_retries = st.slider("Max finish retries", 0, 5, MAX_FINISH_RETRIES_DEFAULT, key="ui_max_finish_retries")
    finish_tokens_initial = st.number_input("Finish tokens (initial)", min_value=64, max_value=2048, value=FINISH_TOKENS_INITIAL, step=64, key="ui_finish_tokens_initial")
    finish_tokens_increment = st.number_input("Finish tokens increment", min_value=0, max_value=1024, value=FINISH_TOKENS_INCREMENT, step=32, key="ui_finish_tokens_increment")

# CSS tuned closer to ChatGPT visuals
CSS = r"""
<style>
:root {
  --bg: #0b0f12;
  --card: #111315;
  --muted: #8b98a6;
  --accent: #10a37f;
  --blue: #0b5fff;
}
body, .main { font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial; }
.chat-container { max-width: 920px; margin: 12px auto 40px; padding: 10px 24px 80px; }
.message-row { display:flex; flex-direction:column; gap:12px; }
.message.user { align-self:flex-end; background: linear-gradient(180deg,#0b5fff,#0748c7); color: #fff; padding:14px 18px; border-radius:16px; max-width:75%; }
.thinking-card { background:#0f1720; color:#e6eef8; padding:18px; border-radius:14px; box-shadow:0 10px 30px rgba(2,6,23,0.6); max-width:75%; }
.thinking-header { font-size:16px; font-weight:700; color:#cfe7ff; margin-bottom:8px; display:flex; align-items:center; gap:8px; }
.thinking-body { font-size:18px; font-weight:600; color:#fff; line-height:1.35; margin-bottom:6px; }
.final-card { background:#0b1115; border:1px solid rgba(255,255,255,0.03); color:#d7dadc; padding:14px; border-radius:12px; max-width:75%; margin-top:6px; }
.badge { display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; background: rgba(255,255,255,0.04); color:#cfe7ff; margin-left:8px; }
.counter { font-size:12px; color:#9fb9ff; margin-left:6px; }
.typing-dots { display:inline-block; vertical-align:middle; margin-left:6px; }
.typing-dots span { display:inline-block; width:6px; height:6px; margin:0 3px; background:#9fb9ff; border-radius:50%; opacity:0.18; animation: dot 1s infinite linear; }
.typing-dots span:nth-child(1){ animation-delay: 0s; } .typing-dots span:nth-child(2){ animation-delay: 0.15s; } .typing-dots span:nth-child(3){ animation-delay: 0.3s; }
@keyframes dot { 0%{transform:translateY(0); opacity:0.18;} 50%{transform:translateY(-6px); opacity:1;} 100%{transform:translateY(0); opacity:0.18;} }
.debug { font-size:12px; white-space:pre-wrap; background:#071018; color:#bfe7ff; padding:8px; border-radius:6px; margin-top:10px; }
footer { display:none; }
textarea { width:100%; min-height:90px; padding:12px; border-radius:10px; border:none; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.02); background:#0b1013; color:#e6eef8; }
.send-btn { margin-top:10px; width:100%; padding:12px; border-radius:10px; background:linear-gradient(180deg,#0b5fff,#0748c7); color:white; border:none; font-weight:700; cursor:pointer; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ---------------- session initialization ----------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role":"system", "content": (
"""You are a reasoning assistant. When possible, emit labeled sections: 'Thought:', 'Reasoning:', and 'Final Answer:'. The client will present 'Thinking' (Thought + Reasoning) separately from the Final Answer. 

@Strictly ensure sentences are complete—never stop mid-word, mid-sentence, or mid-thought without closure. 

@While thinking, focus on logical, relevant reasoning—avoid randomness. Always grasp the context and the user's intent before starting your thought process. Optimize token use by thinking efficiently and concluding quickly; avoid overthinking or unnecessary depth.

Here are some example user prompts to guide reasoning style:
- Think step-by-step, stay focused, and deliver a clear conclusion.
- Extract key facts, reason clearly, then provide a brief final answer.
- Reason logically and avoid tangents; summarize with confidence.
- Break down the question smartly and come to the point fast.
- Use precise reasoning to reach a direct, well-supported conclusion.""") }    ]

# ---------------- parsing utilities ----------------
def parse_thinking_and_final(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (thinking_text, final_text). Thinking merges Thought + Reasoning."""
    if not text:
        return None, None
    s = text.strip()
    s = re.sub(r'^[\s\'"`,\.-]+', '', s)

    thought_pat = re.compile(r"Thought:\s*(.*?)(?=(?:Reasoning:|Final Answer:|inal Answer:|$))", re.I | re.S)
    reasoning_pat = re.compile(r"Reasoning:\s*(.*?)(?=(?:Final Answer:|inal Answer:|$))", re.I | re.S)
    final_pat = re.compile(r"(?:Final Answer:|inal Answer:)\s*(.*)$", re.I | re.S)

    thought_m = thought_pat.search(s)
    reasoning_m = reasoning_pat.search(s)
    final_m = final_pat.search(s)

    parts = []
    if thought_m:
        t = thought_m.group(1).strip()
        if t:
            parts.append(t)
    if reasoning_m:
        r = reasoning_m.group(1).strip()
        if r:
            parts.append(r)

    if final_m and not (thought_m or reasoning_m):
        pre = s[:final_m.start()].strip()
        if pre:
            parts = [pre]

    if not (thought_m or reasoning_m or final_m):
        parts = [s] if s else []

    thinking = "\n\n".join(parts).strip() if parts else None
    final_text = final_m.group(1).strip() if final_m else None
    return thinking, final_text

def is_buffer_truncated(buffer: str) -> bool:
    """Heuristic: returns True if buffer ends mid-word or without terminal punctuation."""
    if not buffer:
        return False
    b = buffer.rstrip()
    last_char = b[-1]
    if last_char.isalnum():
        # check for terminal punctuation in last 3 chars
        if not re.search(r'[.!?]\s*$', b[-3:]):
            return True
    return False

# ---------------- API helpers ----------------
def post_request(payload: dict, stream: bool = False, timeout: int = 30):
    """Wrapper for requests.post; returns response object if stream True, or JSON/dict if non-streaming."""
    if stream:
        return requests.post(API_URL, json=payload, stream=True, timeout=STREAM_TIMEOUT)
    else:
        resp = requests.post(API_URL, json=payload, timeout=timeout)
        try:
            return resp.json()
        except Exception:
            return {"response": resp.text}

def request_finish_from_model(buffer: str, max_new_tokens: int) -> Optional[str]:
    """
    Ask the model to finish the assistant output. Return text or None on failure.
    We send system + last user + assistant partial + user instruction to finish.
    """
    messages = []
    # include system if present
    for m in st.session_state.messages:
        if m["role"] == "system":
            messages.append(m)
            break
    # include last user
    last_user = None
    for m in reversed(st.session_state.messages):
        if m["role"] == "user":
            last_user = m
            break
    if last_user:
        messages.append(last_user)
    # assistant partial
    messages.append({"role":"assistant", "content": buffer})
    # instruction to finish with only Final Answer (no chain-of-thought)
    messages.append({
        "role":"user",
        "content": (
            "The assistant reply above may be cut off. Continue/finish it and provide ONLY the concise Final Answer "
            "(one short paragraph). Do NOT include your chain-of-thought."
        )
    })
    payload = {"messages": messages, "max_new_tokens": max_new_tokens}
    try:
        j = post_request(payload, stream=False, timeout=30)
        if isinstance(j, dict):
            candidate = j.get("response") or j.get("text") or ""
            if not candidate and "choices" in j and isinstance(j["choices"], list) and j["choices"]:
                c0 = j["choices"][0]
                candidate = c0.get("text") or (c0.get("message") or {}).get("content") or ""
            if candidate and isinstance(candidate, str):
                return candidate.strip()
        # otherwise if server returned stringish content
    except Exception:
        pass
    return None

def request_summarize_with_model(thinking_text: str, max_new_tokens: int) -> Optional[str]:
    """Ask the model (non-streaming) to synthesize Thinking into a concise final answer."""
    if not thinking_text:
        return None
    system_msg = {"role":"system", "content":"You are a concise assistant. Given Thinking text, output a single concise Final Answer paragraph and no chain-of-thought."}
    user_msg = {"role":"user", "content": f"Thinking text:\n\n{thinking_text}\n\nProduce a concise Final Answer (one short paragraph)."}
    payload = {"messages":[system_msg, user_msg], "max_new_tokens": max_new_tokens}
    try:
        j = post_request(payload, stream=False, timeout=30)
        if isinstance(j, dict):
            candidate = j.get("response") or j.get("text") or ""
            if not candidate and "choices" in j and isinstance(j["choices"], list) and j["choices"]:
                c0 = j["choices"][0]
                candidate = c0.get("text") or (c0.get("message") or {}).get("content") or ""
            if candidate and isinstance(candidate, str):
                return candidate.strip()
    except Exception:
        pass
    return None

# ---------------- rendering helpers ----------------
def render_history():
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for m in st.session_state.messages:
        if m["role"] == "system":
            continue
        if m["role"] == "user":
            st.markdown(f'<div class="message user">{markdown.markdown(m["content"])}</div>', unsafe_allow_html=True)
        else:
            thinking, final = parse_thinking_and_final(m["content"])
            if thinking:
                thinking_html = (
                    f'<div class="thinking-card"><div class="thinking-header">Thinking</div>'
                    f'<div class="thinking-body">{markdown.markdown(thinking, extensions=["fenced_code","codehilite"])}</div></div>'
                )
                st.markdown(thinking_html, unsafe_allow_html=True)
            if final:
                final_html = f'<div class="final-card"><strong>Final Answer</strong><div style="margin-top:8px">{markdown.markdown(final)}</div></div>'
                st.markdown(final_html, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

# ---------------- Page render ----------------
render_history()

# ---------------- Input form ----------------
with st.form("chat_form", clear_on_submit=True):
    user_input = st.text_area("Your message:", height=90, key="input")
    submitted = st.form_submit_button("Send")

if submitted and user_input and user_input.strip():
    st.session_state.messages.append({"role":"user", "content": user_input.strip()})

    # placeholders created only inside handler
    stream_ph = st.empty()
    debug_ph = st.empty() if st.session_state.get("ui_stream_debug", False) else None

    # initial thinking card with typing dots
    init_html = ('<div class="thinking-card"><div class="thinking-header">Thinking '
                 '<span class="typing-dots"><span></span><span></span><span></span></span></div>'
                 '<div class="thinking-body"></div></div>')
    stream_ph.markdown(init_html, unsafe_allow_html=True)

    buffer = ""
    last_thinking = None
    last_final = None
    last_update_time = 0.0
    raw_lines = []
    finish_attempts = 0
    final_source = "stream"  # will be updated to 'finish (n)', 'summarizer', or 'heuristic'

    payload = {"messages": st.session_state.messages, "max_new_tokens": MAX_NEW_TOKENS_STREAM, "stream": True}

    try:
        # start streaming request
        with post_request(payload, stream=True) as resp:
            if resp.status_code != 200:
                # fallback non-streaming
                try:
                    j = resp.json()
                    full_text = j.get("response") or j.get("text") or json.dumps(j)
                except Exception:
                    full_text = f"Error {resp.status_code}: {resp.text}"
                st.session_state.messages.append({"role":"assistant", "content": full_text})
                st.experimental_rerun()

            for raw_line in resp.iter_lines(decode_unicode=True):
                raw_lines.append(raw_line)
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if not line:
                    continue

                if debug_ph:
                    debug_text = "\n".join(raw_lines[-200:])
                    debug_ph.code(debug_text, language="text")

                # handle SSE 'data:' prefix (OpenAI-style)
                if line.startswith("data:"):
                    data = line[len("data:"):].strip()
                else:
                    data = line

                if data == "[DONE]":
                    break

                piece = ""
                try:
                    obj = json.loads(data)
                    choices = obj.get("choices")
                    if isinstance(choices, list) and choices:
                        c0 = choices[0]
                        delta = c0.get("delta") if isinstance(c0, dict) else {}
                        if isinstance(delta, dict):
                            piece = delta.get("content") or ""
                        if not piece:
                            piece = c0.get("text") or (c0.get("message") or {}).get("content") or ""
                    if not piece:
                        for k in ("response","content","text","data"):
                            if k in obj and obj[k]:
                                v = obj[k]
                                piece = v.get("content") if isinstance(v, dict) else str(v)
                                break
                except Exception:
                    piece = data

                if not piece:
                    continue

                buffer += piece

                thinking_text, final_text = parse_thinking_and_final(buffer)

                now = time.time()
                if (thinking_text != last_thinking) or (final_text != last_final):
                    if now - last_update_time >= UPDATE_THROTTLE_SEC:
                        # build thinking card (typing dots when final missing)
                        thinking_html = '<div class="thinking-card"><div class="thinking-header">Thinking'
                        if not final_text:
                            thinking_html += ' <span class="typing-dots"><span></span><span></span><span></span></span>'
                        thinking_html += '</div>'
                        thinking_html += f'<div class="thinking-body">{markdown.markdown(thinking_text or "", extensions=["fenced_code","codehilite"])}</div></div>'

                        # build final card with badge if present
                        if final_text:
                            badge = f'<span class="badge">source: stream</span>'
                            final_html = f'<div class="final-card"><div><strong>Final Answer</strong>{badge}</div><div style="margin-top:8px">{markdown.markdown(final_text, extensions=["fenced_code","codehilite"])}</div></div>'
                            html = thinking_html + final_html
                        else:
                            html = thinking_html

                        stream_ph.markdown(html, unsafe_allow_html=True)
                        last_thinking = thinking_text
                        last_final = final_text
                        last_update_time = now

                time.sleep(0.005)

        # streaming finished
        thinking_buffered = last_thinking or (buffer.strip() if buffer else None)
        final_buffered = last_final

        # 1) If no final and buffer looks truncated and auto_retry enabled -> try finish attempts
        if not final_buffered and st.session_state.get("ui_auto_retry", True) and buffer:
            max_retries = st.session_state.get("ui_max_finish_retries", MAX_FINISH_RETRIES_DEFAULT)
            tokens_initial = st.session_state.get("ui_finish_tokens_initial", FINISH_TOKENS_INITIAL)
            tokens_increment = st.session_state.get("ui_finish_tokens_increment", FINISH_TOKENS_INCREMENT)

            # do finish attempts only if buffer likely truncated or there's no final label
            if is_buffer_truncated(buffer) or not final_buffered:
                attempt = 0
                current_tokens = tokens_initial
                while attempt < max_retries:
                    attempt += 1
                    finish_attempts += 1
                    finished = request_finish_from_model(buffer, max_new_tokens=current_tokens)
                    # update badge and counter UI to show attempt in progress
                    badge_html = f'<span class="badge">source: finish (attempt {attempt})</span><span class="counter">tries: {attempt}</span>'
                    # show intermediate update (thinking + badge)
                    thinking_html = '<div class="thinking-card"><div class="thinking-header">Thinking'
                    thinking_html += '</div>'
                    thinking_html += f'<div class="thinking-body">{markdown.markdown(thinking_buffered or "", extensions=["fenced_code","codehilite"])}</div></div>'
                    final_preview = f'<div class="final-card"><div><strong>Final Answer</strong>{badge_html}</div><div style="margin-top:8px">finishing...</div></div>'
                    stream_ph.markdown(thinking_html + final_preview, unsafe_allow_html=True)

                    if finished:
                        # parse finished for final label
                        _, parsed_final = parse_thinking_and_final(finished)
                        if parsed_final:
                            final_buffered = parsed_final
                        else:
                            # treat the entire finished text as final if no label
                            final_buffered = finished.strip()
                        final_source = f"finish (attempt {attempt})"
                        break
                    else:
                        # increment tokens and try again
                        current_tokens += tokens_increment
                        attempt += 0  # just continue
                # end while
        # end finish attempts

        # 2) If still no final, optional summarizer
        if not final_buffered:
            use_model_summarizer = st.session_state.get("ui_model_summarize", True)
            if use_model_summarizer and thinking_buffered:
                # indicate summarizer is running
                badge_html = '<span class="badge">source: summarizer</span>'
                thinking_html = '<div class="thinking-card"><div class="thinking-header">Thinking</div>'
                thinking_html += f'<div class="thinking-body">{markdown.markdown(thinking_buffered or "", extensions=["fenced_code","codehilite"])}</div></div>'
                final_preview = f'<div class="final-card"><div><strong>Final Answer</strong>{badge_html}</div><div style="margin-top:8px">summarizing...</div></div>'
                stream_ph.markdown(thinking_html + final_preview, unsafe_allow_html=True)

                synthesized = request_summarize_with_model(thinking_buffered, max_new_tokens=MAX_NEW_TOKENS_SUMMARIZE)
                if synthesized:
                    final_buffered = synthesized
                    final_source = "summarizer"

        # 3) Fallback heuristic
        if not final_buffered:
            if thinking_buffered:
                sentences = re.split(r'(?<=[.!?])\s+', thinking_buffered.strip())
                sentences = [s.strip() for s in sentences if s.strip()]
                final_buffered = " ".join(sentences[-2:]) if sentences else (thinking_buffered.strip()[:512] + "...")
            else:
                final_buffered = "No response generated by model."
            final_source = final_source if 'final_source' in locals() else "heuristic"

        # Final UI update: show thinking + final with badge showing source
        badge_html = f'<span class="badge">source: {final_source}</span>'
        if finish_attempts > 0 and final_source.startswith("finish"):
            badge_html += f'<span class="counter">tries: {finish_attempts}</span>'

        thinking_html = '<div class="thinking-card"><div class="thinking-header">Thinking</div>'
        thinking_html += f'<div class="thinking-body">{markdown.markdown(thinking_buffered or "", extensions=["fenced_code","codehilite"])}</div></div>'
        final_html = f'<div class="final-card"><div><strong>Final Answer</strong>{badge_html}</div><div style="margin-top:8px">{markdown.markdown(final_buffered, extensions=["fenced_code","codehilite"])}</div></div>'
        stream_ph.markdown(thinking_html + final_html, unsafe_allow_html=True)

        # append assistant raw buffer (for traceability) to history
        assistant_content_to_store = buffer.strip() or final_buffered
        st.session_state.messages.append({"role":"assistant", "content": assistant_content_to_store})

        # Re-render the page so history is stable and input is bottom
        st.rerun()

    except Exception as e:
        st.session_state.messages.append({"role":"assistant", "content": f"Streaming error: {e}"})
        st.rerun()
