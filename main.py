# main.py
import json
import re
import time
from typing import Dict, Any, Optional

import streamlit as st
from openai import OpenAI

# ============== APP CONFIG ==============
st.set_page_config(page_title="World History Quiz", page_icon="🌍", layout="centered")
DEBUG = True  # βάλ' το False όταν τελειώσουμε

# ============== THEME / CSS ==============
st.markdown("""
<style>
...
</style>
""", unsafe_allow_html=True)
html, body, [data-testid="stAppViewContainer"] {
  background: linear-gradient(160deg, #1a2540 0%, #0d1733 70%, #0a0f1f 100%) !important;
  color: #f3f5ff !important;
}
h1,h2,h3,h4 { color: #ffffff !important; }
.quiz-card {
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.15);
  border-radius: 14px;
  padding: 1.2rem;
  box-shadow: 0 4px 12px rgba(0,0,0,0.4);
}
.badge {
  background:#21335c; color:#d9e4ff;
  border:1px solid rgba(255,255,255,.15);
}
.score-chip {
  background:#1c2b53; color:#f1f4ff;
}
div.stButton > button {
  border-radius: 10px;
  font-weight: 600;
  color: white !important;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
  border: none;
}
div.stButton > button:hover {
  background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%) !important;
}
[data-baseweb="toast"] {
  border-radius: 10px !important;
  font-weight: 500 !important;
  color: white !important;
}
[data-baseweb="toast"][kind="positive"] { background-color: #22c55e !important; }
[data-baseweb="toast"][kind="negative"] { background-color: #ef4444 !important; }
[data-baseweb="toast"][kind="warning"]  { background-color: #f59e0b !important; }

                              

# ============== OPENAI CLIENT ==============
API_KEY = st.secrets.get("OPENAI_API_KEY")
if not API_KEY:
    st.error("❌ Missing OPENAI_API_KEY in Streamlit Secrets.")
    st.stop()

client = OpenAI(api_key=API_KEY)
MODEL_CANDIDATES = ["gpt-4o-mini", "gpt-4o", "gpt-4o-mini-2024-07-18", "gpt-4o-2024-08-06"]

# ============== HELPERS ==============
def extract_json_block(text: str) -> str:
    """
    Robust extraction of a JSON object from LLM text.
    - Tries fenced ```json blocks
    - Tries plain JSON
    - Falls back to balanced-braces scanning
    """
    if not text:
        raise ValueError("Empty model response.")

    txt = text.strip()

    # 1) fenced ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", txt, flags=re.S | re.I)
    if m:
        return m.group(1)
    m = re.search(r"```\s*(\{.*?\})\s*```", txt, flags=re.S | re.I)
    if m:
        return m.group(1)

    # 2) try direct JSON
    try:
        json.loads(txt)
        return txt
    except Exception:
        pass

    # 3) balanced braces scan (χωρίς recursion)
    start = txt.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model response.")
    stack = 0
    end: Optional[int] = None
    for i, ch in enumerate(txt[start:], start=start):
        if ch == "{":
            stack += 1
        elif ch == "}":
            stack -= 1
            if stack == 0:
                end = i + 1
                break
    if end is None:
        raise ValueError("Unbalanced JSON braces in model response.")
    return txt[start:end]


def validate_question(obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Expected:
    {
      "question": str,
      "options": [str, str, str, str],
      "correct_index": int (0..3),
      "explanation": str
    }
    """
    for k in ("question", "options", "correct_index", "explanation"):
        if k not in obj:
            raise ValueError(f"Missing field: {k}")

    q = str(obj["question"]).strip()
    options = [str(x).strip() for x in obj["options"] if str(x).strip()]
    if len(options) < 2:
        raise ValueError("Not enough options.")
    # normalize to exactly 4 options
    if len(options) > 4:
        options = options[:4]
    while len(options) < 4:
        options.append(f"None of the above {len(options)}")

    ci = obj["correct_index"]
    if not isinstance(ci, int) or not (0 <= ci < len(options)):
        raise ValueError("Invalid correct_index.")

    exp = str(obj["explanation"]).strip()
    if len(exp) < 3:
        exp = "No explanation provided."

    return {"question": q, "options": options, "correct_index": ci, "explanation": exp}


SYSTEM_SCHEMA = """You are a quiz author. Output ONLY one JSON object with fields:
- "question": string (concise, single-sentence)
- "options": array of 4 short, plausible, distinct answers (strings)
- "correct_index": integer 0..3 (index in "options")
- "explanation": string (1–2 sentences, factual, neutral)
No markdown, no code fences, no commentary. JSON only.
"""

def call_openai_for_question(theme: str, era: str, difficulty: str) -> Dict[str, Any]:
    user_msg = (
        f"Create ONE WORLD HISTORY multiple-choice question.\n"
        f"Theme: {theme}\n"
        f"Era/Region: {era or 'Any'}\n"
        f"Difficulty: {difficulty}\n"
        f"Avoid duplicates from previous session questions if provided."
    )

    asked = st.session_state.get("asked_questions", [])
    if asked:
        user_msg += "\nAlready asked (avoid these topics):\n" + "\n".join(f"- {q}" for q in asked[-10:])

    last_err = None
    for model in MODEL_CANDIDATES:
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.6,
                messages=[
                    {"role": "system", "content": SYSTEM_SCHEMA},
                    {"role": "user", "content": user_msg}
                ],
                timeout=30
            )
            raw = resp.choices[0].message.content
            json_text = extract_json_block(raw)
            obj = json.loads(json_text)
            return validate_question(obj)
        except Exception as e:
            last_err = e
            if DEBUG:
                st.info(f"Model {model} failed: {e}")
            continue
    raise RuntimeError(f"OpenAI call failed. Last error: {last_err}")


# ============== SESSION STATE ==============
defaults = {
    "quiz": [],
    "current": 0,
    "score": 0,
    "answered": False,
    "selected": None,
    "asked_questions": [],
    "start_time": time.time(),
}
for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# ============== SIDEBAR ==============
with st.sidebar:
    st.header("⚙️ Settings")
    theme = st.selectbox("Theme", [
        "General World History",
        "Ancient Civilizations",
        "Medieval Period",
        "Renaissance & Exploration",
        "Industrial Era",
        "20th Century (World Wars / Cold War)",
        "Non-Western Empires & History"
    ], index=0)
    era = st.text_input("Specific Era / Region (optional)", placeholder="e.g., Mesopotamia, Ming Dynasty, WWI Europe")
    difficulty = st.select_slider("Difficulty", options=["Easy", "Medium", "Hard"], value="Medium")
    total_q = st.slider("Number of Questions", 3, 15, 8)
    st.markdown("---")
    st.caption("Tip: Press **R** to rerun after changing settings.")

# ============== QUIZ BUILDERS ==============
def reset_quiz():
    st.session_state.quiz = []
    st.session_state.current = 0
    st.session_state.score = 0
    st.session_state.answered = False
    st.session_state.selected = None
    st.session_state.asked_questions = []
    st.session_state.start_time = time.time()
    st.rerun()

def ensure_quiz_built():
    need = total_q - len(st.session_state.quiz)
    if need <= 0:
        return
    with st.spinner("Generating questions from OpenAI…"):
        for _ in range(need):
            q = call_openai_for_question(theme, era, difficulty)
            st.session_state.quiz.append(q)
            st.session_state.asked_questions.append(q["question"])

# ============== UI CONTROLS ==============
colA, colB = st.columns(2)
with colA:
    if st.button("🔁 New Quiz"):
        reset_quiz()
with colB:
    if st.button("➕ Add 1 Question"):
        ensure_quiz_built()

ensure_quiz_built()

# meta header
elapsed = int(time.time() - st.session_state.start_time)
mins, secs = divmod(elapsed, 60)
st.markdown(
    f"<span class='badge'>Theme: {theme}</span>"
    f"<span class='badge'>Difficulty: {difficulty}</span>"
    f"<span class='badge'>Questions: {len(st.session_state.quiz)}</span>"
    f"<span class='badge'>Time: {mins}m {secs}s</span>",
    unsafe_allow_html=True
)

# ============== QUIZ FLOW ==============
if st.session_state.current >= len(st.session_state.quiz):
    total = len(st.session_state.quiz)
    score = st.session_state.score
    ratio = score / total if total else 0
    st.markdown("## 🏁 Results")
    st.markdown(f"<div class='score-chip'>Score: {score}/{total}</div>", unsafe_allow_html=True)
    if ratio == 1:
        st.success("Perfect! 🏆")
        st.balloons()
    elif ratio >= 0.8:
        st.success("Excellent work! 🔥")
    elif ratio >= 0.5:
        st.warning("Not bad — a bit more reading and you’ll ace it! 📚")
    else:
        st.info("Tough round. Try again! 💪")
    if st.button("Play Again"):
        reset_quiz()
    st.stop()

q = st.session_state.quiz[st.session_state.current]

st.markdown("#### Question")
st.markdown(f"<div class='quiz-card'><b>{q['question']}</b></div>", unsafe_allow_html=True)

choice = st.radio(
    "Choose your answer:",
    options=[f"{i+1}. {opt}" for i, opt in enumerate(q['options'])],
    index=None,
    key=f"q_{st.session_state.current}"
)

col1, col2 = st.columns(2)
feedback = st.empty()

if col1.button("✅ Submit") and not st.session_state.answered:
    if choice is None:
        st.warning("Select an option first 🙂")
    else:
        sel = int(choice.split(".")[0]) - 1
        if sel == q["correct_index"]:
            st.session_state.score += 1
            feedback.success(f"Correct! ✅\n\n{q['explanation']}")
        else:
            feedback.error(f"Wrong. ❌ Correct answer: **{q['options'][q['correct_index']]}**\n\n{q['explanation']}")
        st.session_state.answered = True

if col2.button("⏭️ Skip") and not st.session_state.answered:
    feedback.info(f"Skipped. Correct answer: **{q['options'][q['correct_index']]}**\n\n{q['explanation']}")
    st.session_state.answered = True

if st.session_state.answered:
    if st.button("Next ➡️"):
        st.session_state.current += 1
        st.session_state.answered = False
        st.session_state.selected = None
        st.rerun()

st.markdown("<br><p style='text-align:center;color:#9aa4b2'>Powered by OpenAI • Model: gpt-4o-mini • Streamlit</p>", unsafe_allow_html=True)


