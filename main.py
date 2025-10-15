import json
import re
import time
from typing import Dict, Any
import streamlit as st
from openai import OpenAI

# ---------- CONFIG ----------
st.set_page_config(page_title="World History Quiz", page_icon="🌍", layout="centered")

# ---------- CSS STYLE ----------
st.markdown("""
<style>
body, [data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at 10% 10%, #0f1624 0%, #0b1120 50%, #080c18 100%) !important;
    color: #e6edff !important;
}
h1,h2,h3,h4 { color: #e6edff !important; }
.quiz-card {
    background: rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 1.2rem;
    margin-top: 1rem;
}
.score-chip {
    background: rgba(255,255,255,0.1);
    border-radius: 20px;
    padding: 6px 12px;
    display:inline-block;
    margin-bottom:10px;
}
</style>
""", unsafe_allow_html=True)

st.title("🌍 World History Quiz")
st.caption("An AI-powered quiz with colorful design and GPT-4o-mini intelligence.")

# ---------- OPENAI CLIENT ----------
API_KEY = st.secrets.get("OPENAI_API_KEY")
if not API_KEY:
    st.error("❌ Missing OPENAI_API_KEY in your Streamlit Secrets.")
    st.stop()

client = OpenAI(api_key=API_KEY)
MODEL_LIST = ["gpt-4o-mini", "gpt-4o-mini-2024-07-18", "gpt-4o", "gpt-4o-2024-08-06"]
DEBUG = True

# ---------- HELPER FUNCTIONS ----------
def extract_json_block(text: str) -> str:
    if not text:
        raise ValueError("Empty response from model.")
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fence:
        return fence.group(1)
    obj = re.search(r"(\{(?:[^{}]|(?1))*\})", text, flags=re.S)
    if obj:
        return obj.group(1)
    return text.strip()

def validate_question(obj: Dict[str, Any]) -> Dict[str, Any]:
    if not all(k in obj for k in ("question", "options", "correct_index", "explanation")):
        raise ValueError("Missing required fields in JSON.")

    if not isinstance(obj["options"], list) or len(obj["options"]) < 2:
        raise ValueError("Invalid options list.")
    obj["options"] = [str(x).strip() for x in obj["options"][:4]]

    if not isinstance(obj["correct_index"], int) or not (0 <= obj["correct_index"] < len(obj["options"])):
        raise ValueError("Invalid correct_index.")
    return obj

SYSTEM_JSON_SCHEMA = """You are a quiz author. Produce ONLY a single JSON object with fields:
- "question": string (concise historical question)
- "options": array of 4 short plausible answers
- "correct_index": integer 0..3 (correct option index)
- "explanation": string (1–2 sentence factual explanation)
Do not include markdown or commentary. Return raw JSON only.
"""

def generate_question(theme: str, era: str, difficulty: str) -> Dict[str, Any]:
    user_msg = f"""
Create one WORLD HISTORY multiple-choice question.
Theme: {theme}
Era/Region: {era or "Any"}
Difficulty: {difficulty}
Avoid duplicates from previous questions.
"""
    asked = st.session_state.get("asked_questions", [])
    if asked:
        user_msg += "\nAlready asked:\n" + "\n".join(f"- {q}" for q in asked[-10:])

    last_error = None
    for model in MODEL_LIST:
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.7,
                messages=[
                    {"role": "system", "content": SYSTEM_JSON_SCHEMA},
                    {"role": "user", "content": user_msg}
                ],
                timeout=30
            )
            raw = resp.choices[0].message.content
            json_text = extract_json_block(raw)
            obj = json.loads(json_text)
            return validate_question(obj)
        except Exception as e:
            last_error = e
            if DEBUG:
                st.info(f"Model `{model}` failed: {e}")
            continue
    raise RuntimeError(f"OpenAI call failed: {last_error}")

# ---------- SESSION STATE ----------
for k, v in {
    "quiz": [],
    "current": 0,
    "score": 0,
    "answered": False,
    "selected": None,
    "asked_questions": [],
    "start_time": time.time(),
}.items():
    st.session_state.setdefault(k, v)

# ---------- SIDEBAR SETTINGS ----------
with st.sidebar:
    st.header("⚙️ Settings")
    theme = st.selectbox("Theme", [
        "General World History", "Ancient Civilizations", "Medieval Period",
        "Renaissance & Exploration", "Industrial Era", "20th Century (World Wars)",
        "Non-Western Empires & History"
    ], index=0)
    era = st.text_input("Specific Era / Region", placeholder="e.g., Mesopotamia, Ming Dynasty")
    difficulty = st.select_slider("Difficulty", options=["Easy", "Medium", "Hard"], value="Medium")
    total_q = st.slider("Number of Questions", 3, 15, 8)
    st.markdown("---")
    st.caption("💡 Tip: Press **R** to rerun after changing settings.")

# ---------- QUIZ FUNCTIONS ----------
def reset_quiz():
    for key in ("quiz", "current", "score", "answered", "selected", "asked_questions"):
        if key == "quiz":
            st.session_state[key] = []
        elif key == "asked_questions":
            st.session_state[key] = []
        else:
            st.session_state[key] = 0
    st.session_state.start_time = time.time()
    st.rerun()

def ensure_quiz_built():
    needed = total_q - len(st.session_state.quiz)
    if needed <= 0:
        return
    with st.spinner("Generating questions..."):
        for _ in range(needed):
            q = generate_question(theme, era, difficulty)
            st.session_state.quiz.append(q)
            st.session_state.asked_questions.append(q["question"])

# ---------- MAIN LOGIC ----------
col1, col2 = st.columns(2)
with col1:
    if st.button("🔁 New Quiz"):
        reset_quiz()
with col2:
    if st.button("➕ Add 1 Question"):
        ensure_quiz_built()

ensure_quiz_built()

elapsed = int(time.time() - st.session_state.start_time)
mins, secs = divmod(elapsed, 60)
st.markdown(f"<p class='score-chip'>⏱️ {mins}m {secs}s | Theme: {theme} | Difficulty: {difficulty}</p>", unsafe_allow_html=True)

# ---------- DISPLAY QUIZ ----------
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
st.markdown(f"<div class='quiz-card'><b>{q['question']}</b></div>", unsafe_allow_html=True)

choice = st.radio("Choose your answer:", [f"{i+1}. {opt}" for i, opt in enumerate(q["options"])], index=None)
colA, colB = st.columns(2)
feedback = st.empty()

if colA.button("✅ Submit") and not st.session_state.answered:
    if choice is None:
        st.warning("Select an answer first.")
    else:
        selected_idx = int(choice.split(".")[0]) - 1
        correct_idx = q["correct_index"]
        if selected_idx == correct_idx:
            st.session_state.score += 1
            feedback.success(f"✅ Correct! {q['explanation']}")
        else:
            feedback.error(f"❌ Wrong. Correct: **{q['options'][correct_idx]}**\n\n{q['explanation']}")
        st.session_state.answered = True

if colB.button("⏭️ Skip") and not st.session_state.answered:
    correct_idx = q["correct_index"]
    feedback.info(f"Skipped. Correct answer: **{q['options'][correct_idx]}**\n\n{q['explanation']}")
    st.session_state.answered = True

if st.session_state.answered:
    if st.button("Next ➡️"):
        st.session_state.current += 1
        st.session_state.answered = False
        st.session_state.selected = None
        st.rerun()

st.markdown("<br><p style='text-align:center;color:gray'>Powered by OpenAI • Model: GPT-4o-mini • Streamlit</p>", unsafe_allow_html=True)
