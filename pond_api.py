# pond_api.py
import os, json
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- import your existing logic ---
from app import (
    begin as pond_begin,
    advance as pond_advance,
    archive as pond_archive,
    new_state,
    PondState,   # needed for (de)serialization
)

app = FastAPI(title="Memory Pond API", version="0.1.2")

# Allow Unity Editor & local play to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # lock down later if needed
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# 🪶 SESSION PERSISTENCE SECTION
# ------------------------------
SESSIONS_FILE = "sessions.json"

def _session_to_json(sess: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    pond = sess.get("pond")
    if pond is not None and isinstance(pond, PondState):
        out["pond"] = pond.to_dict()
    else:
        out["pond"] = None
    return out

def _session_from_json(data: Dict[str, Any]) -> Dict[str, Any]:
    pond_data = data.get("pond")
    if pond_data:
        try:
            pond = PondState.from_dict(pond_data)
        except Exception:
            pond = None
    else:
        pond = None
    return {"pond": pond}

def load_sessions() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {sid: _session_from_json(sdata) for sid, sdata in raw.items()}
        except Exception as e:
            print(f"[Warning] Could not load sessions: {e}")
    return {}

def save_sessions():
    try:
        serializable = {sid: _session_to_json(sess) for sid, sess in SESSIONS.items()}
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Warning] Could not save sessions: {e}")

# Global in-memory store (reloaded at startup)
SESSIONS: Dict[str, Dict[str, Any]] = load_sessions()

def get_session(session_id: str) -> Dict[str, Any]:
    """Return an existing session or create a new one, then persist."""
    if session_id not in SESSIONS:
        SESSIONS[session_id] = new_state()
        save_sessions()
    return SESSIONS[session_id]

# ------------------------------
# 📬 REQUEST / RESPONSE MODELS
# ------------------------------
class BeginReq(BaseModel):
    session_id: str
    title: str
    offering: str

class AdvanceReq(BaseModel):
    session_id: str
    reply: str

class ArchiveReq(BaseModel):
    session_id: str
    title: Optional[str] = ""
    offering: Optional[str] = ""
    save: bool = True

class ResetReq(BaseModel):
    session_id: str

class PondResp(BaseModel):
    html: str
    finished: bool = False
    archive_choice: Optional[str] = None
    timestamp: str = datetime.utcnow().isoformat(timespec="seconds")

# ------------------------------
# 🧠 INTERNAL HELPERS
# ------------------------------
def _extract_status(session: Dict[str, Any]) -> Dict[str, Any]:
    pond = session.get("pond")
    if not pond:
        return {"finished": False, "archive_choice": None}
    return {
        "finished": bool(getattr(pond, "finished", False)),
        "archive_choice": getattr(pond, "archive_choice", None),
    }

# ------------------------------
# 🪞 API ENDPOINTS
# ------------------------------
@app.post("/begin", response_model=PondResp)
def api_begin(req: BeginReq):
    session = get_session(req.session_id)
    session, html = pond_begin(req.title, req.offering, session)
    save_sessions()
    status = _extract_status(session)
    return PondResp(html=html, **status)

@app.post("/advance", response_model=PondResp)
def api_advance(req: AdvanceReq):
    session = get_session(req.session_id)
    session, html = pond_advance(req.reply, session)
    save_sessions()
    status = _extract_status(session)
    return PondResp(html=html, **status)

@app.post("/archive", response_model=PondResp)
def api_archive(req: ArchiveReq):
    session = get_session(req.session_id)
    session, html = pond_archive(req.title or "", req.offering or "", session, req.save)
    save_sessions()
    status = _extract_status(session)
    return PondResp(html=html, **status)

@app.post("/reset", response_model=dict)
def api_reset(req: ResetReq):
    SESSIONS[req.session_id] = new_state()
    save_sessions()
    return {"ok": True, "session_id": req.session_id}
