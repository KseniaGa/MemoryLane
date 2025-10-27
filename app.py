# memory_pond_levels_visual.py
import os, json, re
from datetime import datetime
import gradio as gr
import requests

# ---------------- CONFIG ----------------
OPENAI_BASE = os.getenv("OPENAI_BASE", "http://127.0.0.1:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")
MODEL = os.getenv("MODEL", "meta-llama-3.1-8b-instruct")

def chat(messages, temperature=0.18):
    r = requests.post(
        f"{OPENAI_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        json={"model": MODEL, "messages": messages,
              "temperature": temperature, "top_p": 0.9},
        timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()

# ---------------- text helpers ----------------
SENT_SPLIT = re.compile(r'\s*(?<=\.|\?|!)\s+')
def _sentences(text): return [p.strip() for p in SENT_SPLIT.split(text.strip()) if p.strip()]
def _limit_words(s, n): return " ".join(s.split()[:n])

BANNED_PHRASES = [
    "ripples of","autumn leaves","waters of your heart","ebb and flow",
    "gentle lapping","on my shore","my surface","I reflect","I hold",
    "allow yourself","should","you need to"
]
def sanitize_style(text: str, max_words: int) -> str:
    t = text
    for p in BANNED_PHRASES:
        t = re.sub(re.escape(p), "", t, flags=re.I)
    t = re.sub(r"\b(I|I'm|I am|my|mine)\b", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip()
    words = t.split()
    if len(words) > max_words:
        t = " ".join(words[:max_words]).rstrip(",; ") + "."
    return t

def enforce_two_sentence_with_short_question(text, question_max_words=30, total_words=60):
    parts = _sentences(text) or []
    first = parts[0] if parts else "You’ve named something clearly."
    q = parts[1] if len(parts) >= 2 else "What detail stands out most?"
    q = _limit_words(q.rstrip(".!… ").strip(), question_max_words)
    if not q.endswith("?"): q += "?"
    out = f"{first} {q}"
    return sanitize_style(out, max_words=total_words)

def enforce_single_sentence(text, max_words=60):
    s = _sentences(text)
    one = (s[0] if s else "You described the moment with enough detail to hold it.")\
        .rstrip("?!.…") + "."
    return sanitize_style(one, max_words=max_words)

def enforce_paragraph(text, max_words=80):
    s = " ".join(_sentences(text))
    if not s:
        s = ("You clarified what happened and how it felt. We’ll carry those "
             "details and look for patterns next. The aim is understanding, not judgment.")
    s = " ".join(s.split()[:max_words]).rstrip() + "."
    return sanitize_style(s, max_words=max_words)

# ---------------- intent parsing ----------------
YES_RX  = re.compile(r'\b(yes|y|okay|ok|sure|continue|next|proceed|go on|move on|deeper|ready|let\'?s (go|continue|move))\b', re.I)
MORE_RX = re.compile(r'\b(no|not yet|wait|more|another|add|stay|one more)\b', re.I)
def is_yes(text):  return bool(YES_RX.search(text or "")) and len((text or "").split()) <= 5
def is_more(text):
    t = (text or "").strip()
    return bool(MORE_RX.search(t)) or len(t.split()) > 5

# archive choice parsing
CHOICE_FLOAT_RX = re.compile(r'\b(float|accept|integrate|keep|let it float)\b', re.I)
CHOICE_SINK_RX  = re.compile(r'\b(sink|release|let go|submerge|drop)\b', re.I)
CHOICE_HOLD_RX  = re.compile(r'\b(hold|keep awhile|not yet|later|wait|pause)\b', re.I)
def parse_archive_choice(text):
    t = (text or "").strip()
    if not t: return None
    if CHOICE_FLOAT_RX.search(t): return "float"
    if CHOICE_SINK_RX.search(t):  return "sink"
    if CHOICE_HOLD_RX.search(t):  return "hold"
    lw = t.lower()
    return lw if lw in {"float","sink","hold"} else None

# ---------------- level-specific prompt templates ----------------

DESCRIPTIVE_SYS = """
You are THE POND — a calm witness.

LEVEL 1: HELPING REMEMBER
TASK: to help the player recall and anchor the moment.

INSTRUCTIONS:
Return EXACTLY two sentences (≤60 words total):
• S1 = brief acknowledgement summarizing what they described (facts, sensations, emotions).
• S2 = one short open question (≤30 words) that invites detail or concreteness.
   Examples:
     – "What happened?"
     – "What did you notice most clearly?"
     – "What did you see, hear, or feel?"
Tone: plain and warm; second-person only; one gentle metaphor allowed; no advice or judgment.
"""

ANALYTIC_SYS = """
You are THE POND — an observer of meaning-making.

LEVEL 2: HELPING INTERPRET
TASK: to help the player make meaning and notice connections or causes.

INSTRUCTIONS:
Return EXACTLY two sentences (≤65 words total):
• S1 = concise slightly poetic synthesis of player's words.
• S2 = one open question (≤35 words) inviting reflection on why it mattered.
   Examples:
     – "What link do you see between this and your usual choices?"
     – "Why do you think this moment stayed with you?"
Tone: clear and grounded; second-person only; imagery optional but language should remain plain and causal; no advice.
"""

REFLEXIVE_SYS = """
You are THE POND: a reflective mirror.

LEVEL 3: HELPING CONNECT
TASK: to help the player link insight to self or world.

INSTRUCTIONS:
Return EXACTLY two sentences (≤65 words total):
• S1 = concise slightly poetic synthesis of player's words.
• S2 = open question (≤35 words) about values, change, or self-understanding.
   Examples:
     – "What does this show you about what matters most?"
     – "How might this shape what you do tomorrow?"
Tone: gentle and purposeful; second-person only; light metaphor welcome; no advice or evaluation.
"""

TRANSITION_SYS = """
You are THE POND — a neutral storyteller.

TAKS: Write a transition synthesis (3–4 sentences, ≤70 words) to close the current level and invite the next.

Include:
1. What the player remembered or described here.
2. What meaning emerged based on the player’s words (if any).
3. What the next level will explore. (in an absract way)
4. End with an inviting or grounding statement (no question mark, no advice).
Tone: second-person only; plain, reflective, slightly poetic, natural.
"""

ARTIFACT_SYS = """
You are THE POND — the archivist of memories.

TASK: Compose a closing synthesis.
Return EXACTLY two sentences (≤45 words total):
• Summarize what happened, why it mattered, and what it revealed about the self or world.
• Second-person only. No advice. One gentle metaphor allowed.
End with '({choice})' inline.
"""

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
        self.step = 0
        self.history = []            # {"player":...} / {"pond":...} / {"artifact":...}
        self.summaries = []          # per-level transition syntheses
        self.finished = False
        self.level_anchor = 0
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
            if "player" in item: txts.append(item["player"])
        if self.level == 0 and self.offering:
            txts.insert(0, self.offering)
        return "\n".join(txts).strip() or self.offering

    def _system_for_level(self):
        return [DESCRIPTIVE_SYS, ANALYTIC_SYS, REFLEXIVE_SYS][self.level]

    # ---- NEW: cumulative memory bundlers ----
    def _summaries_text(self) -> str:
        """Previous level syntheses as concise bullets."""
        if not self.summaries:
            return ""
        lines = []
        for i, s in enumerate(self.summaries, 1):
            lvl = s.get("level", f"Level {i}")
            txt = s.get("summary", "").strip()
            lines.append(f"- {lvl}: {txt}")
        return "\n".join(lines)

    def _context_bundle(self) -> str:
        """
        Title + Offering + prior level syntheses + current level notes.
        Fed to the model for every prompt so later levels 'remember' earlier ones.
        """
        parts = []
        if self.title:
            parts.append(f"Title: {self.title}")
        if self.offering:
            parts.append(f"Offering: {self.offering}")
        prev = self._summaries_text()
        if prev:
            parts.append("Previous level syntheses:\n" + prev)
        current = self._level_player_text()
        if current:
            parts.append("Current level notes:\n" + current)
        return "\n\n".join(parts).strip()

    # --- micro reflection + question (per turn) ---
    def _prompt_for_level(self, player_text=""):
        # The bundle includes offering, prior summaries, and current notes
        context = self._context_bundle()
        msgs = [
            {"role": "system", "content": self._system_for_level()},
            {"role": "user", "content": context},
        ]
        raw = chat(msgs, temperature=0.16)
        return enforce_two_sentence_with_short_question(raw)

    # --- 1-sentence closure (used after round 3, inside the level) ---
    def _close_sentence_for_level(self):
        context = self._context_bundle()
        msgs = [
            {"role": "system", "content": "Write ONE validating sentence (≤28 words), second-person, no question, no advice, plain language, summarizing the player's most recent notes while respecting earlier context."},
            {"role": "user", "content": context}
        ]
        raw = chat(msgs, temperature=0.1)
        return enforce_single_sentence(raw, max_words=45)

    # --- 3–4 sentence transition synthesis (when moving to next level) ---
    def _transition_synthesis(self, next_level_name: str):
        context = self._context_bundle()
        msgs = [
            {"role": "system", "content": TRANSITION_SYS},
            {"role": "user", "content": f"{context}\n\nNext level: {next_level_name}."}
        ]
        raw = chat(msgs, temperature=0.14)
        return enforce_paragraph(raw, max_words=80)

    # --- Final artifact (adapts to choice) ---
    def final_artifact(self, choice="hold"):
        choice = (choice or "hold").lower()
        stance = {
            "float": "You chose to let it float: accepted and held lightly.",
            "sink":  "You chose to let it sink: released and set down.",
            "hold":  "You chose to hold it awhile: kept close for now."
        }.get(choice, "You chose to hold it awhile: kept close for now.")
        joined = "\n".join(s["summary"] for s in self.summaries)
        msgs = [
            {"role": "system", "content": ARTIFACT_SYS.replace("{choice}", choice)},
            {"role": "user",  "content": joined}
        ]
        raw = chat(msgs, temperature=0.12)
        parts = _sentences(raw) or []
        if len(parts) < 2:
            parts = (parts + ["You will keep this as a clear, simple note."])[:2]
        combined = sanitize_style(" ".join((" ".join(parts[:2])).split()[:42]), max_words=42)
        html = (
            f"<div class='pond-card pond-l2'>"
            f"<div class='pond-title'>🪶 Memory Artifact</div>"
            f"<div class='pond-body'>{combined}<br><br><b>{stance}</b></div>"
            f"</div>"
        )
        self.history.append({"artifact": html})
        return html

    # --- main loop ---
    def next(self, player_reply=""):
        if self.finished:
            return "<div class='pond-card pond-l2'><div class='pond-body'>The ritual is complete.</div></div>"

        # ARCHIVE CHOICE PHASE
        if self.awaiting_archive_choice:
            choice = parse_archive_choice(player_reply)
            if not choice:
                return self.render_current("Choice",
                    "You can say <b>float</b>, <b>sink</b>, or <b>hold</b> — whichever feels right for this memory.")
            self.archive_choice = choice
            self.awaiting_archive_choice = False
            self.finished = True
            return self.final_artifact(choice)

        # LEVEL DECISION PHASE
        if self.awaiting_level_decision:
            decision = (player_reply or "").strip()
            if is_yes(decision):
                self.awaiting_level_decision = False
                self.level += 1
                self.step = 0
                self.level_anchor = len(self.history)
                pond_reply = self._prompt_for_level("")
                self.history.append({"pond": pond_reply})
                self.step = 1
                return self.render_current("Round 1", pond_reply)
            if is_more(decision):
                if decision: self.history.append({"player": decision})
                close_line = self._close_sentence_for_level()
                # keep a breadcrumb
                self.history.append({"pond": close_line})
                return self.render_current("Synthesis",
                    f"{close_line}<br><br>☁️ The pond grows quiet. Share more, or say <b>continue</b> to go deeper.")
            return self.render_current("Synthesis",
                "If you'd like to go deeper, say <b>continue</b>. Or add another detail to stay a little longer.")

        # Normal progression
        if player_reply: self.history.append({"player": player_reply})

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

        # Round 3 → close sentence + transition synthesis
        elif self.step == 2:
            close_line = self._close_sentence_for_level()
            # store breadcrumb
            self.history.append({"pond": close_line})

            if self.level < 2:
                next_name = self.focuses[self.level+1]['name']
                trans = self._transition_synthesis(next_name)
                self.history.append({"pond": trans})
                self.summaries.append({"level": self.focuses[self.level]['name'], "summary": trans})
                self.awaiting_level_decision = True
                invite = (f"{trans}<br><br>☁️ The pond grows quiet. "
                          f"Say <b>continue</b> to move to Level {self.level+2}: "
                          f"<b>{next_name}</b>, or add one more detail to linger here.")
                return self.render_current("Transition", invite)
            else:
                # level 3 done -> archival choice
                trans = self._transition_synthesis("Archiving")
                self.history.append({"pond": trans})
                self.summaries.append({"level": self.focuses[self.level]['name'], "summary": trans})
                self.awaiting_archive_choice = True
                closing = (f"{trans}<br><br>🌊 The reflection feels complete.<br>"
                           "🪶 Do you let it <b>float</b>, <b>sink</b>, or <b>hold</b> it awhile longer?")
                return self.render_current("Transition", closing)

# ---------------- UTIL ----------------
def new_state(): return {"pond": None}

def begin(title, offering, session):
    title = (title or "").strip()
    if not title:
        return session, "<div class='pond-card pond-l0'><div class='pond-body'>Please give your offering a short title (1–5 words).</div></div>"
    pond = PondState(title, (offering or ""))
    session["pond"] = pond
    first = pond.next(pond.offering)
    return session, first

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
    artifact_html = None
    for item in reversed(pond.history):
        if "artifact" in item:
            artifact_html = item["artifact"]; break
    if artifact_html is None:
        artifact_html = pond.final_artifact(pond.archive_choice or "hold")
    rec = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds"),
        "title": pond.title,
        "offering": pond.offering,
        "summaries": pond.summaries,
        "archive_choice": pond.archive_choice or "hold",
        "artifact": artifact_html
    }
    with open("memories.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return session, "<div class='pond-card pond-l2'><div class='pond-body'>✨ Saved: a small ripple joins the pond archive.</div></div>"

# ---------------- GRADIO UI ----------------
with gr.Blocks(title="Memory Pond") as demo:
    gr.Markdown("# 🌊 Memory Pond")
    gr.HTML("""
    <style>
      .pond-card{padding:14px;border-radius:14px;margin:10px 0;
                 border:1px solid rgba(0,0,0,.08); box-shadow:0 1px 6px rgba(0,0,0,.04)}
      .pond-title{font-weight:600;margin-bottom:6px}
      .pond-metaphor{opacity:.85;margin-bottom:8px}
      .pond-body{line-height:1.55}
      .pond-l0{background:#EAF6FF;}  /* surface */
      .pond-l1{background:#E6F5F0;}  /* under-surface */
      .pond-l2{background:#EEF0FF;}  /* whole-pond */
    </style>
    """)

    session = gr.State(new_state())
    title = gr.Textbox(label="Name the Memory")
    offering = gr.Textbox(label="Describe your memory", lines=3)

    begin_btn = gr.Button("Look into the pond...")
    out = gr.HTML()
    begin_btn.click(begin, inputs=[title, offering, session], outputs=[session, out])

    reply_box = gr.Textbox(label="Your reply", lines=3)
    next_btn = gr.Button("Ponder / Continue")
    next_btn.click(advance, inputs=[reply_box, session], outputs=[session, out])
    next_btn.click(lambda: "", outputs=[reply_box])

    with gr.Row():
        save_check = gr.Checkbox(label="Save to memories.jsonl", value=True)
        save_btn = gr.Button("Archive Memory")
    save_status = gr.HTML()
    save_btn.click(archive, inputs=[title, offering, session, save_check],
                   outputs=[session, save_status])

    gr.Markdown("—\nThis is a reflective experience, not therapy. Pause if uncomfortable.\n")

if __name__ == "__main__":
    demo.launch(debug=True)
