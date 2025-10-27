# memory_pond_levels_visual.py
import os, json, re
from datetime import datetime
import gradio as gr
import requests

# ---------------- CONFIG ----------------
OPENAI_BASE = os.getenv("OPENAI_BASE", "http://127.0.0.1:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")
MODEL = os.getenv("MODEL", "meta-llama-3.1-8b-instruct")

def chat(messages, temperature=0.2):
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": MODEL, "messages": messages,
              "temperature": temperature, "top_p": 0.9},
        timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

# ---------------- Text guardrails ----------------
SENT_SPLIT = re.compile(r'\s*(?<=\.|\?|!)\s+')

def _sentences(text):
    return [p.strip() for p in SENT_SPLIT.split(text.strip()) if p.strip()]

def _limit_words(s, n):
    return " ".join(s.split()[:n])

def enforce_two_sentence_with_short_question(text, question_max_words=12):
    parts = _sentences(text)
    if not parts:
        return "I hear you. What detail stands out most?"
    first = parts[0]
    q = parts[1] if len(parts) >= 2 else "What detail stands out most?"
    q = _limit_words(q.rstrip(".!… ").strip(), question_max_words)
    if not q.endswith("?"):
        q += "?"
    return f"{first} {q}"

def enforce_two_sentence_synthesis(text, max_words_total=50):
    parts = _sentences(text)
    if not parts:
        return "I understand what you shared. The water holds it gently."
    parts = parts[:2]
    parts = [p.rstrip("?").strip() for p in parts]
    joined = " ".join(parts)
    words = joined.split()
    if len(words) > max_words_total:
        joined = " ".join(words[:max_words_total])
        if not joined.endswith("."):
            joined += "."
    else:
        if not joined.endswith((".", "!", "…")):
            joined += "."
    return joined

# ---------------- intent parsing ----------------
YES_RX = re.compile(r'\b(yes|y|okay|ok|sure|continue|next|proceed|go on|move on|deeper|ready|let\'?s (go|continue|move))\b', re.I)
MORE_RX = re.compile(r'\b(no|not yet|wait|more|another|add|stay|one more)\b', re.I)

def is_yes(text):
    return bool(YES_RX.search(text or "")) and len((text or "").split()) <= 5

def is_more(text):
    t = (text or "").strip()
    return bool(MORE_RX.search(t)) or len(t.split()) > 5

# archive choice parsing
CHOICE_FLOAT_RX = re.compile(r'\b(float|accept|integrate|keep|let it float)\b', re.I)
CHOICE_SINK_RX  = re.compile(r'\b(sink|release|let go|submerge|drop)\b', re.I)
CHOICE_HOLD_RX  = re.compile(r'\b(hold|keep awhile|not yet|later|wait|pause)\b', re.I)

def parse_archive_choice(text):
    t = (text or "").strip()
    if not t:
        return None
    if CHOICE_FLOAT_RX.search(t): return "float"
    if CHOICE_SINK_RX.search(t):  return "sink"
    if CHOICE_HOLD_RX.search(t):  return "hold"
    lw = t.lower()
    if lw in {"float","sink","hold"}: return lw
    return None

# ---------------- POND STATE ----------------
class PondState:
    focuses = [
        {"name": "Descriptive", "hint": "what happened",
         "icon": "🌤", "metaphor": "You’re looking at the surface; ripples reflect what just passed."},
        {"name": "Analytic", "hint": "why it mattered",
         "icon": "🌊", "metaphor": "You lean closer, peering under the surface where patterns form."},
        {"name": "Reflexive", "hint": "what it reveals about self or the world",
         "icon": "🌌", "metaphor": "You see the whole pond — surface and depth together, connected."}
    ]

    def __init__(self, title, offering):
        self.title = (title or "").strip()
        self.offering = (offering or "").strip()
        self.level = 0
        self.step = 0                    # 0–2 within level
        self.history = []                # {"player":...} / {"pond":...} / {"artifact":...}
        self.summaries = []              # per-level synthesis
        self.finished = False
        self.level_anchor = 0            # index where current level began
        self.awaiting_level_decision = False
        self.awaiting_archive_choice = False
        self.archive_choice = None

    # ----- visual/textual rendering -----
    def render_current(self, round_name: str, body_html: str) -> str:
        f = self.focuses[self.level]
        return (
            f"<div class='pond-card pond-l{self.level}'>"
            f"  <div class='pond-title'>{f['icon']} <b>Level {self.level+1} — {f['name']}</b> · {round_name}</div>"
            f"  <div class='pond-metaphor'><em>{f['metaphor']}</em></div>"
            f"  <div class='pond-body'>{body_html}</div>"
            f"</div>"
        )

    # ----- helpers -----
    def _level_player_text(self):
        txts = []
        for item in self.history[self.level_anchor:]:
            if "player" in item:
                txts.append(item["player"])
        if self.level == 0 and self.offering:
            txts.insert(0, self.offering)
        return "\n".join(txts).strip() or self.offering

    # --- Prompt: normal turn (ack + short question) ---
    def _prompt_for_level(self, player_text=""):
        focus = self.focuses[self.level]["name"]
        hint = self.focuses[self.level]["hint"]
        msgs = [
            {"role": "system", "content": f"""
You are THE POND — calm, patient, reflective. A mindful conversation partner.

STYLE:
- Use 1–2 sentences (≤50 words total).
- Plain, natural language with gentle warmth; light imagery optional.
- No advice or judgment.
- End with a brief, open question about {focus.lower()} ({hint}).

EXAMPLES:
Descriptive → "You described the moment and how it felt. What detail stays with you?"
Analytic → "This seems to linger for a reason. What meaning do you find in it?"
Reflexive → "You've looked at what happened and why. What does it show you about what matters to you?"
"""},
            {"role": "user", "content": player_text or self.offering},
        ]
        raw = chat(msgs, temperature=0.18)
        return enforce_two_sentence_with_short_question(raw, question_max_words=12)

    # --- Prompt: level synthesis (NO question) ---
    def _synthesis_for_level(self):
        focus = self.focuses[self.level]["name"]
        transcript = self._level_player_text()
        msgs = [
            {"role": "system", "content": f"""
You are THE POND that archives memories — calm and reflective.
Write a brief synthesis to close the {focus} level.

RULES:
- 2 sentences, ≤50 words total.
- Grounded, gentle language; light nature metaphor optional.
- DO NOT ask a question. No advice or judgment.
- Tone: validation + gentle closure (small pause before going deeper).
"""},
            {"role": "user", "content": transcript}
        ]
        raw = chat(msgs, temperature=0.14)
        return enforce_two_sentence_synthesis(raw, max_words_total=50)

    # --- Final artifact (adapts to choice) ---
    def final_artifact(self, choice="hold"):
        choice = choice or "hold"
        choice_note = {
            "float":  "You chose to let it float — accepted, held lightly.",
            "sink":   "You chose to let it sink — released into the deep.",
            "hold":   "You chose to hold it awhile — kept close with care."
        }[choice]

        joined = "\n".join(s["summary"] for s in self.summaries)
        msgs = [
            {"role": "system", "content": f"""
You are the Pond that archives memories.
Compose a closing synthesis combining what was seen, understood, and felt.
3–4 sentences max. Tone calm, grounded, accepting. Light nature metaphor allowed.
Mention the archival stance briefly at the end: ({choice}).
Keep language simple.
"""},
            {"role": "user", "content": joined}
        ]
        artifact = chat(msgs, temperature=0.12)
        self.history.append({"artifact": artifact})
        return f"<div class='pond-card pond-l2'><div class='pond-title'>🪶 Memory Artifact</div><div class='pond-body'>{artifact}<br><br><b>{choice_note}</b></div></div>"

    # --- Main loop ---
    def next(self, player_reply=""):
        if self.finished:
            return "<div class='pond-card pond-l2'><div class='pond-body'>The ritual is complete.</div></div>"

        # ARCHIVE CHOICE PHASE (after Level 3)
        if self.awaiting_archive_choice:
            choice = parse_archive_choice(player_reply)
            if not choice:
                return self.render_current(
                    "Choice",
                    "You can say <b>float</b>, <b>sink</b>, or <b>hold</b> — whichever feels right for this memory."
                )
            self.archive_choice = choice
            self.awaiting_archive_choice = False
            self.finished = True
            return self.final_artifact(choice)

        # LEVEL DECISION PHASE (after R3 of level 1/2)
        if self.awaiting_level_decision:
            decision = (player_reply or "").strip()
            if is_yes(decision):
                self.awaiting_level_decision = False
                self.level += 1
                self.step = 0
                self.level_anchor = len(self.history)
                pond_reply = self._prompt_for_level("")  # start next level Q1
                self.history.append({"pond": pond_reply})
                self.step = 1
                return self.render_current("Round 1", pond_reply)

            if is_more(decision):
                if decision:
                    self.history.append({"player": decision})
                pond_reply = self._synthesis_for_level()
                self.history.append({"pond": pond_reply})
                return self.render_current(
                    "Synthesis",
                    f"{pond_reply}<br><br>☁️ The pond grows quiet. Share more, or say <b>continue</b> to go deeper."
                )

            return self.render_current(
                "Synthesis",
                "If you'd like to go deeper, say <b>continue</b>. Or add another detail to stay a little longer."
            )

        # Normal progression
        if player_reply:
            self.history.append({"player": player_reply})

        # Round 1
        if self.step == 0:
            self.level_anchor = len(self.history)
            pond_reply = self._prompt_for_level(player_text=player_reply)
            self.history.append({"pond": pond_reply})
            self.step = 1
            return self.render_current("Round 1", pond_reply)

        # Round 2
        elif self.step == 1:
            pond_reply = self._prompt_for_level(player_text=player_reply)
            self.history.append({"pond": pond_reply})
            self.step = 2
            return self.render_current("Round 2", pond_reply)

        # Round 3 → synthesis then wait for decision / archive
        elif self.step == 2:
            pond_reply = self._synthesis_for_level()
            self.history.append({"pond": pond_reply})
            self.summaries.append({"level": self.focuses[self.level]['name'], "summary": pond_reply})

            if self.level < 2:
                self.awaiting_level_decision = True
                invite = (f"{pond_reply}<br><br>☁️ The pond grows quiet. "
                          f"Say <b>continue</b> to move to Level {self.level+2}: "
                          f"<b>{self.focuses[self.level+1]['name']}</b>, or add one more detail to linger here.")
                return self.render_current("Synthesis", invite)
            else:
                # Level 3 completed -> archival choice phase
                self.awaiting_archive_choice = True
                closing = (f"{pond_reply}<br><br>🌊 The reflection feels complete.<br>"
                           "🪶 Do you let it <b>float</b>, <b>sink</b>, or <b>hold</b> it awhile longer?")
                return self.render_current("Synthesis", closing)

# ---------------- UTIL ----------------
def new_state():
    return {"pond": None}

def begin(title, offering, session):
    title = (title or "").strip()
    if not title:
        return session, "<div class='pond-card pond-l0'><div class='pond-body'>Please give your offering a short title (1–5 words).</div></div>"
    pond = PondState(title, (offering or ""))
    session["pond"] = pond
    # Immediately trigger Level 1 — Round 1
    first = pond.next(pond.offering)
    return session, first  # already rendered as a card

def advance(player_text, session):
    pond: PondState = session.get("pond")
    if not pond:
        return session, "<div class='pond-card pond-l0'><div class='pond-body'>Click <b>Begin Ritual</b> first.</div></div>"
    reply = pond.next(player_text or "")
    return session, reply

def archive(title, offering, session, save):
    pond: PondState = session.get("pond")
    if not pond or not pond.finished:
        return session, "<div class='pond-card pond-l2'><div class='pond-body'>Finish the ritual first.</div></div>"
    if not save:
        return session, "<div class='pond-card pond-l2'><div class='pond-body'>🌫 Nothing stored — the pond remains still.</div></div>"

    # if artifact already built, reuse; otherwise build with stored choice
    artifact_text = None
    for item in reversed(pond.history):
        if "artifact" in item:
            artifact_text = item["artifact"]
            break
    if artifact_text is None:
        artifact_text = pond.final_artifact(pond.archive_choice or "hold")

    rec = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "title": pond.title,
        "offering": pond.offering,
        "summaries": pond.summaries,
        "archive_choice": pond.archive_choice or "hold",
        "artifact": artifact_text
    }
    with open("memories.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return session, "<div class='pond-card pond-l2'><div class='pond-body'>✨ Saved: a small ripple joins the pond archive.</div></div>"

# ---------------- GRADIO UI ----------------
with gr.Blocks(title="Memory Pond — Three-Level Ritual") as demo:
    gr.Markdown("# 🌊 Memory Pond — Three-Level Ritual")
    gr.HTML("""
    <style>
      .pond-card{padding:14px;border-radius:14px;margin:10px 0;
                 border:1px solid rgba(0,0,0,.08); box-shadow:0 1px 6px rgba(0,0,0,.04)}
      .pond-title{font-weight:600;margin-bottom:6px}
      .pond-metaphor{opacity:.85;margin-bottom:8px}
      .pond-body{line-height:1.55}
      .pond-l0{background:#EAF6FF;}   /* surface */
      .pond-l1{background:#E6F5F0;}   /* under-surface */
      .pond-l2{background:#EEF0FF;}   /* whole-pond */
    </style>
    """)

    session = gr.State(new_state())
    title = gr.Textbox(label="Offering")
    offering = gr.Textbox(label="Describe your offering", lines=3)

    begin_btn = gr.Button("Begin Ritual")
    out = gr.HTML()  # HTML so our cards render nicely
    begin_btn.click(begin, inputs=[title, offering, session], outputs=[session, out])

    reply_box = gr.Textbox(label="Your reply", lines=3)
    next_btn = gr.Button("Send / Continue")
    next_btn.click(advance, inputs=[reply_box, session], outputs=[session, out])
    next_btn.click(lambda: "", outputs=[reply_box])

    with gr.Row():
        save_check = gr.Checkbox(label="Save to memories.jsonl", value=True)
        save_btn = gr.Button("Archive Artifact")
    save_status = gr.HTML()
    save_btn.click(archive, inputs=[title, offering, session, save_check],
                   outputs=[session, save_status])

    gr.Markdown("—\nThis is a reflective experience, not therapy. Pause if uncomfortable.\n")

if __name__ == "__main__":
    demo.launch(debug=True)
