import json
import re
import time
from typing import List, Dict, Any

import streamlit as st
from openai import OpenAI


st.set_page_config(
    page_title="World History Quiz",
    page_icon="🌍",
    layout="centered"
)


st.markdown("""
<style>
:root { --brand:#3b82f6; --bg:#0b1020; --card:#111936; --muted:#9aa4b2; --accent:#22c55e; --warn:#f59e0b; --error:#ef4444; }
html, body, [data-testid="stAppViewContainer"] { background: radial-gradient(1200px 600px at 10% 10%, #0d1430 0%, #0a0f1f 45%, #070b16 100%) !important; }
h1,h2,h3,h4 { color: #e6edff !important; }
section.main > div { padding-top: 1.5rem; }
.block-container { max-width: 820px; }
div.stButton > button { border-radius: 10px; font-weight: 600; }
.quiz-card { background: var(--card); border: 1px solid rgba(255,255,255,0.06); padding: 1.25rem 1.1rem; border-radius: 14px; box-shadow: 0 10px 24px rgba(0,0,0,0.35); }
.meta { color: var(--muted); font-size: 0.9rem; }
.score-chip { display:inline-block; padding: 6px 10px; background:#1f2a44; color:#cfe0ff; border-radius: 20px; border:1px solid rgba(255,255,255,0.08); }
.badge { display:inline-block; padding:4px 8px; border-radius:8px; background:#132042; color:#a3b6ff; border:1px solid rgba(255,255,255,.08); }
.success { color: #86efac; }
.warning { color: #fbbf24; }
.error { color: #fca5a5; }
.kbd { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; background:#101826; border:1px solid #25314a; border-bottom-color:#1b253d; padding:2px 6px; border-radius:6px; }
</style>
""", unsafe_allow_html=True)

st.markdown("### 🌍 World History Quiz")
st.caption("A colorful, AI-powered quiz. Pick a theme & difficulty, then challenge your knowledge!")


API_KEY = st.secrets.get("OPENAI_API_KEY")
if not API_KEY:
    st.error("Missing OPENAI_API_KEY in Streamlit Secrets. Add it to `.streamlit/secrets.toml`.")
    st.stop()

client = OpenAI(api_key=API_KEY)
MODEL_NAME = "gpt-4o-mini"  # as requested


def extract_json_block(text: str) -> str:
    """
    Try to safely extract a JSON object from a model response.
    Handles ```json ... ``` fences or plain JSON strings.
    """
    if not text:
        raise ValueError("Empty response from model.")
    # Try fenced ```json ... ```
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        return fence.group(1)
    # Try first {...} block
    obj = re.search(r"(\{(?:[^{}]|(?1))*\})", text, flags=re.S)
    if obj:
        return obj.group(1)
    # Fall back to raw
    return text.strip()

def validate_question(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the question JSON has required fields and safe values.
    Expected schema:
    {
      "question": str,
      "options": [str, str, str, str],
      "correct_index": int (0-3),
      "explanation": str
    }
    """
    required = ["question", "options", "correct_index", "explanation"]
    for k in required:
        if k not in obj:
            raise ValueError(f"Missing field: {k}")

    if not isinstance(obj["question"], str) or len(obj["question"].strip()) < 5:
        raise ValueError("Invalid 'question'.")

    if not isinstance(obj["options"], list) or len(obj["options"]) < 2:
        raise ValueError("Invalid 'options' list.")
    # Normalize to 4 options: pad or trim
    options = [str(x).strip() for x in obj["options"] if str(x).strip()]
    if len(options) < 2:
        raise ValueError("Not enough valid options.")
    if len(options) > 4:
        options = options[:4]
    elif len(options) < 4:

        while len(options) < 4:
            options.append(f"None of the above {len(options)}")

    ci = obj["correct_index"]
    if not isinstance(ci, int) or not (0 <= ci < len(options)):
        raise ValueError("Invalid 'correct_index' position.")

    if not isinstance(obj["explanation"], str) or len(obj["explanation"].strip()) < 5:
        raise ValueError("Invalid 'explanation'.")

    obj["options"] = options
    obj["correct_index"] = ci
    return obj

SYSTEM_JSON_SCHEMA = """You are a quiz author. Produce ONLY a single JSON object with fields:
- "question": string (concise, clear, single-sentence prompt)
- "options": array of 4 short, distinct, plausible options (strings)
- "correct_index": integer 0..3 (index of the correct option in "options")
- "explanation": string (1-2 sentences, factual, neutral tone)

Rules:
- Output JSON ONLY. No commentary.
- Do NOT repeat the question text inside explanation.
- Use globally accepted historical facts; avoid controversies unless widely settled.
"""

def generate_question(theme: str, era: str, difficulty: str) -> Dict[str, Any]:
    """
    Ask the model for one world-history question.
    """
    user_msg = (
        f"Create one WORLD HISTORY multiple-choice question.\n"
        f"Theme: {theme}\n"
        f"Era/Region focus: {era}\n"
        f"Difficulty: {difficulty}\n"
        f"Avoid topics already asked in this session (if provided below).\n"
    )


    asked = st.session_state.get("asked_questions", [])
    if asked:
        user_msg += "\nAlready asked (avoid duplicates):\n"
        for q in asked[-10:]:  # last 10
            user_msg += f"- {q}\n"

    try:
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0.7,
            messages=[
                {"role": "system", "content": SYSTEM_JSON_SCHEMA},
                {"role": "user", "content": user_msg}
            ]
        )
        raw = resp.choices[0].message.content
        block = extract_json_block(raw)
        obj = json.loads(block)
        return validate_question(obj)
    except Exception as e:
        raise RuntimeError(f"Model error: {e}")


if "quiz" not in st.session_state:
    st.session_state.quiz = []
if "current" not in st.session_state:
    st.session_state.current = 0
if "score" not in st.session_state:
    st.session_state.score = 0
if "answered" not in st.session_state:
    st.session_state.answered = False
if "selected" not in st.session_state:
    st.session_state.selected = None
if "asked_questions" not in st.session_state:
    st.session_state.asked_questions = []
if "start_time" not in st.session_state:
    st.session_state.start_time = time.time()


with st.sidebar:
    st.header("⚙️ Settings")
    theme = st.selectbox("Theme", [
        "General World History",
        "Ancient Civilizations",
        "Medieval Period",
        "Renaissance & Early Modern",
        "Age of Exploration",
        "Industrial Era",
        "20th Century (World Wars, Cold War)",
        "Non-Western Empires & History"
    ], index=0)

    era = st.text_input("Specific Era/Region (optional)", placeholder="e.g., Mesopotamia, Ming Dynasty, WWI Europe")

    difficulty = st.select_slider("Difficulty", options=["Easy", "Medium", "Hard"], value="Medium")

    total_q = st.slider("Number of Questions", 3, 15, 8)

    st.markdown("---")
    st.markdown("**Pro tip:** Press <span class='kbd'>R</span> to rerun after changing settings.", unsafe_allow_html=True)


def ensure_quiz_built():
    """
    Build/refresh the quiz to match the requested length.
    """
    needed = total_q - len(st.session_state.quiz)
    if needed <= 0:
        return
    with st.spinner("Generating questions from OpenAI…"):
        for _ in range(needed):
            q = generate_question(theme, era or "Any", difficulty)
            st.session_state.quiz.append(q)
            st.session_state.asked_questions.append(q["question"])

def reset_quiz():
    st.session_state.quiz = []
    st.session_state.current = 0
    st.session_state.score = 0
    st.session_state.answered = False
    st.session_state.selected = None
    st.session_state.start_time = time.time()

colA, colB = st.columns([1,1])
with colA:
    if st.button("🔁 New Quiz"):
        reset_quiz()
with colB:
    if st.button("➕ Add 1 Question"):
        ensure_quiz_built()

ensure_quiz_built()


elapsed = int(time.time() - st.session_state.start_time)
mins = elapsed // 60
secs = elapsed % 60
st.markdown(
    f"<div class='meta'>Theme: <span class='badge'>{theme}</span> &nbsp; "
    f"Difficulty: <span class='badge'>{difficulty}</span> &nbsp; "
    f"Questions: <span class='badge'>{len(st.session_state.quiz)}</span> &nbsp; "
    f"Time: <span class='badge'>{mins}m {secs}s</span></div>",
    unsafe_allow_html=True
)


if st.session_state.current >= len(st.session_state.quiz):
    # RESULTS
    total = len(st.session_state.quiz)
    score = st.session_state.score
    ratio = score / total if total else 0
    st.markdown("## Results")
    st.markdown(f"<span class='score-chip'>Score: {score}/{total}</span>", unsafe_allow_html=True)
    if ratio == 1:
        st.markdown("<p class='success'>Perfect! You’re a history machine. 🏆</p>", unsafe_allow_html=True)
        st.balloons()
    elif ratio >= 0.8:
        st.markdown("<p class='success'>Excellent work! 🔥</p>", unsafe_allow_html=True)
    elif ratio >= 0.5:
        st.markdown("<p class='warning'>Not bad — a bit more reading and you’ll ace it! 📚</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p class='error'>Tough round. Fancy another try? 💪</p>", unsafe_allow_html=True)

    if st.button("Play Again"):
        reset_quiz()
        ensure_quiz_built()
    st.stop()


q = st.session_state.quiz[st.session_state.current]
st.markdown("#### Question")
st.markdown(f"<div class='quiz-card'><b>{q['question']}</b></div>", unsafe_allow_html=True)

choice = st.radio(
    "Choose your answer:",
    options=[f"{i+1}. {opt}" for i, opt in enumerate(q["options"])],
    index=None,
    key=f"choice_{st.session_state.current}"
)

col1, col2 = st.columns([1,1])
with col1:
    submit = st.button("✅ Submit")
with col2:
    skip = st.button("⏭️ Skip")

feedback_placeholder = st.empty()

if submit and choice is None:
    st.warning("Pick an option first 🙂")

if submit and choice is not None and not st.session_state.answered:
    selected_idx = int(choice.split(".")[0]) - 1
    st.session_state.selected = selected_idx
    st.session_state.answered = True

    correct_idx = q["correct_index"]
    correct_text = q["options"][correct_idx]

    if selected_idx == correct_idx:
        st.session_state.score += 1
        feedback_placeholder.success(f"Correct! ✅  \n{q['explanation']}")
    else:
        feedback_placeholder.error(f"Wrong. ❌ Correct answer: **{correct_text}**  \n{q['explanation']}")

if skip and not st.session_state.answered:
    st.session_state.selected = None
    st.session_state.answered = True
    correct_idx = q["correct_index"]
    feedback_placeholder.info(f"Skipped. Correct answer: **{q['options'][correct_idx]}**  \n{q['explanation']}")


if st.session_state.answered:
    if st.button("Next ➡️"):
        st.session_state.current += 1
        st.session_state.answered = False
        st.session_state.selected = None
        st.rerun()


st.markdown("<br><div class='meta'>Powered by OpenAI • Model: gpt-4o-mini • Streamlit</div>", unsafe_allow_html=True)
