from __future__ import annotations

import json
import mimetypes
import os
import queue
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent.loop import AgentLoop
from agent.memory import Memory
from agent.prompts import SYSTEM_PROMPT
from tools.base import build_default_registry

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
UPLOADS = RUNTIME / "uploads"
DB_PATH = RUNTIME / "web.sqlite3"
ALLOWED_IMAGES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
MAX_UPLOAD = 10 * 1024 * 1024
TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


class Store:
    def __init__(self, path: Path = DB_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self._init()

    def _init(self):
        with self.lock:
            self.conn.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions(
              id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS messages(
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
              attachments TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, task TEXT NOT NULL, images TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL, queue_position INTEGER, error TEXT, created_at REAL NOT NULL,
              started_at REAL, finished_at REAL);
            CREATE TABLE IF NOT EXISTS run_events(
              id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL, seq INTEGER NOT NULL,
              type TEXT NOT NULL, data TEXT NOT NULL, created_at REAL NOT NULL,
              UNIQUE(run_id, seq));
            CREATE TABLE IF NOT EXISTS approvals(
              id TEXT PRIMARY KEY, run_id TEXT NOT NULL, tool TEXT NOT NULL, arguments TEXT NOT NULL,
              status TEXT NOT NULL, created_at REAL NOT NULL, decided_at REAL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            self.conn.execute(
                "UPDATE runs SET status='interrupted', finished_at=? WHERE status IN ('queued','running','awaiting_approval')",
                (time.time(),),
            )
            defaults = {"model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                        "max_turns": "40"}
            self.conn.executemany("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", defaults.items())
            self.conn.commit()

    def execute(self, sql: str, args=()):
        with self.lock:
            cur = self.conn.execute(sql, args)
            self.conn.commit()
            return cur

    def all(self, sql: str, args=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def one(self, sql: str, args=()):
        with self.lock:
            row = self.conn.execute(sql, args).fetchone()
            return dict(row) if row else None

    def emit(self, run_id: str, kind: str, data: dict[str, Any]):
        with self.lock:
            seq = self.conn.execute(
                "SELECT COALESCE(MAX(seq),0)+1 FROM run_events WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            self.conn.execute(
                "INSERT INTO run_events(run_id,seq,type,data,created_at) VALUES(?,?,?,?,?)",
                (run_id, seq, kind, json.dumps(data, ensure_ascii=False), time.time()),
            )
            self.conn.commit()
        return seq


store = Store()
work_queue: queue.Queue[str] = queue.Queue()
cancel_events: dict[str, threading.Event] = {}
approval_waiters: dict[str, tuple[threading.Event, dict[str, bool]]] = {}
worker_stop = threading.Event()


def serialize(row: dict | None):
    if not row:
        return row
    result = dict(row)
    for key in ("attachments", "images", "data", "arguments"):
        if key in result and isinstance(result[key], str):
            try:
                result[key] = json.loads(result[key])
            except json.JSONDecodeError:
                pass
    return result


def make_backend():
    settings = {r["key"]: r["value"] for r in store.all("SELECT key,value FROM settings")}
    try:
        from backend.client import DeepSeekBackend
        return DeepSeekBackend(base_url=settings["base_url"], model=settings["model"])
    except Exception:
        from backend.fake_backend import FakeBackend
        return FakeBackend()


PUBLISH_TERMS = ("公众号", "微信", "推文", "草稿", "发布", "publish", "draft", "wechat")


def is_publish_task(task: str) -> bool:
    lowered = task.casefold()
    return any(term in lowered for term in PUBLISH_TERMS)


def latest_session_output(session_id: str, before: float) -> Path | None:
    rows = store.all(
        "SELECT id FROM runs WHERE session_id=? AND created_at<? AND status='completed' "
        "ORDER BY created_at DESC",
        (session_id, before),
    )
    for prior in rows:
        output_dir = ROOT / "output" / prior["id"]
        if output_dir.is_dir() and any(output_dir.iterdir()):
            return output_dir
    return None


def system_prompt(task: str = "", previous_output_dir: Path | None = None):
    text = SYSTEM_PROMPT
    try:
        from skills.loader import load_relevant_skills, load_skills, skills_catalog
        skills = load_skills()
        if is_publish_task(task):
            selected = [s for s in skills if s.name in {"wechat-publish", "gzh-design"}]
        else:
            selected = load_relevant_skills(task, skills)[:2]
        if selected:
            text += "\n\n# Skills required for this task\n" + skills_catalog(selected)
    except Exception:
        pass
    if previous_output_dir:
        artifacts = [
            str(path.resolve())
            for name in ("activity_plan.md", "wechat_article.md", "wechat_article.html", "event_project.json")
            if (path := previous_output_dir / name).is_file()
        ]
        if artifacts:
            text += "\n\n# Latest session artifacts\n" + "\n".join(f"- {path}" for path in artifacts)
            text += "\nUse these latest session artifacts instead of files under data/."
            if is_publish_task(task):
                text += (
                    "\nThis is a publish-only follow-up. Do not regenerate the activity plan, "
                    "do not call planning tools, and do not rewrite event_project.json or activity_plan.md. "
                    "Format the latest activity_plan.md with gzh-design and write the polished result to "
                    "wechat_article.html in the current run output directory. Validate that HTML, then use "
                    "mcp__create_draft_from_html_file. A request containing 草稿/draft means create a draft only: "
                    "set publish=false and do not call publish_draft. Only submit a live publication when the "
                    "user explicitly asks for 正式发布, 直接发布, 提交发布, or live publication."
                )
    recalled = Memory("MEMORY.md").recall()
    if recalled.strip():
        text += "\n\n# Project memory\n" + recalled
    return text


def refresh_positions():
    rows = store.all("SELECT id FROM runs WHERE status='queued' ORDER BY created_at")
    for index, row in enumerate(rows, 1):
        store.execute("UPDATE runs SET queue_position=? WHERE id=?", (index, row["id"]))


def run_job(run_id: str):
    row = store.one("SELECT * FROM runs WHERE id=?", (run_id,))
    if not row or row["status"] != "queued":
        return
    cancel = cancel_events.setdefault(run_id, threading.Event())
    if cancel.is_set():
        store.execute("UPDATE runs SET status='cancelled',finished_at=? WHERE id=?", (time.time(), run_id))
        store.emit(run_id, "run_failed", {"error": "cancelled", "cancelled": True})
        return
    store.execute("UPDATE runs SET status='running',started_at=?,queue_position=NULL WHERE id=?", (time.time(), run_id))
    refresh_positions()

    terminal_event: dict[str, Any] = {}

    def emit(kind: str, data: dict[str, Any]):
        if kind in {"run_finished", "run_failed"}:
            terminal_event.clear()
            terminal_event.update({"kind": kind, "data": data})
            return
        store.emit(run_id, kind, data)
        if kind == "approval_required":
            approval_id = uuid.uuid4().hex
            gate, decision = threading.Event(), {}
            approval_waiters[approval_id] = (gate, decision)
            store.execute(
                "INSERT INTO approvals(id,run_id,tool,arguments,status,created_at) VALUES(?,?,?,?,?,?)",
                (approval_id, run_id, data["tool"], json.dumps(data["arguments"], ensure_ascii=False), "pending", time.time()),
            )
            store.execute("UPDATE runs SET status='awaiting_approval' WHERE id=?", (run_id,))
            store.emit(run_id, "approval_pending", {"approval_id": approval_id, **data})

    def confirm(_name: str, _arguments: dict) -> bool:
        pending = store.one("SELECT id FROM approvals WHERE run_id=? AND status='pending' ORDER BY created_at DESC", (run_id,))
        if not pending:
            return False
        approval_id = pending["id"]
        gate, decision = approval_waiters[approval_id]
        while not gate.wait(.25):
            if cancel.is_set():
                return False
        store.execute("UPDATE runs SET status='running' WHERE id=?", (run_id,))
        approval_waiters.pop(approval_id, None)
        return decision.get("approved", False)

    settings = {r["key"]: r["value"] for r in store.all("SELECT key,value FROM settings")}
    mcp_clients = []
    registry = build_default_registry()
    wechat_appid = os.getenv("WECHAT_APPID", "")
    wechat_secret = os.getenv("WECHAT_APPSECRET", "")
    if wechat_appid and wechat_secret:
        try:
            import sys
            from mcp.client import MCPClient, register_mcp_tools
            wechat_mcp = MCPClient(
                [sys.executable, "-m", "mcp.wechat_mp_server"],
                env={"WECHAT_APPID": wechat_appid, "WECHAT_APPSECRET": wechat_secret},
            )
            wechat_mcp.start()
            register_mcp_tools(registry, wechat_mcp)
            mcp_clients.append(wechat_mcp)
        except Exception as exc:
            store.emit(run_id, "integration_warning", {"integration": "wechat", "error": str(exc)})
    output_dir = ROOT / "output" / run_id
    try:
        previous_output_dir = latest_session_output(row["session_id"], row["created_at"])
        agent = AgentLoop(
            make_backend(), registry, system_prompt(row["task"], previous_output_dir),
            max_turns=max(20, int(settings.get("max_turns", 40))), workdir=ROOT,
            confirm_callback=confirm, event_callback=emit, cancel_event=cancel,
            output_dir=output_dir,
        )
        history = store.all(
            "SELECT role,content FROM messages "
            "WHERE session_id=? AND created_at<? AND role IN ('user','assistant') "
            "ORDER BY created_at",
            (row["session_id"], row["created_at"]),
        )
        answer = agent.run(
            row["task"],
            json.loads(row["images"]),
            history_messages=history,
        )
        status = "cancelled" if cancel.is_set() else "completed"
        store.execute("UPDATE runs SET status=?,finished_at=? WHERE id=?", (status, time.time(), run_id))
        store.execute(
            "INSERT INTO messages(id,session_id,role,content,created_at) VALUES(?,?,?,?,?)",
            (uuid.uuid4().hex, row["session_id"], "assistant", answer, time.time()),
        )
        if status == "cancelled":
            payload = terminal_event.get("data") or {"error": "cancelled", "cancelled": True}
            store.emit(run_id, "run_failed", payload)
        else:
            payload = terminal_event.get("data") or {"answer": answer}
            store.emit(run_id, "run_finished", payload)
    except Exception as exc:
        store.execute("UPDATE runs SET status='failed',error=?,finished_at=? WHERE id=?", (str(exc), time.time(), run_id))
        store.emit(run_id, "run_failed", {"error": str(exc)})
    finally:
        for client in mcp_clients:
            try:
                client.stop()
            except Exception:
                pass
        cancel_events.pop(run_id, None)


def worker():
    while not worker_stop.is_set():
        try:
            run_id = work_queue.get(timeout=.25)
        except queue.Empty:
            continue
        try:
            run_job(run_id)
        finally:
            work_queue.task_done()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    worker_stop.clear()
    thread = threading.Thread(target=worker, daemon=True, name="agent-worker")
    thread.start()
    yield
    worker_stop.set()
    thread.join(timeout=2)


app = FastAPI(title="mini-OpenClaw Console", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def authorize(authorization: str | None = Header(default=None)):
    expected = os.getenv("MINIOPENCLAW_ACCESS_TOKEN", "")
    if not expected:
        raise HTTPException(503, "MINIOPENCLAW_ACCESS_TOKEN is not configured")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(401, "Invalid access token")


class SessionInput(BaseModel):
    title: str = Field(default="New session", min_length=1, max_length=100)


class SessionPatch(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class ApprovalInput(BaseModel):
    approved: bool


class SettingsInput(BaseModel):
    model: str | None = None
    base_url: str | None = None
    max_turns: int | None = Field(default=None, ge=20, le=200)


@app.get("/api/health")
def health(_: None = Depends(authorize)):
    return {"ok": True, "api_key_configured": bool(os.getenv("DEEPSEEK_API_KEY"))}


@app.post("/api/sessions")
def create_session(body: SessionInput, _: None = Depends(authorize)):
    now, session_id = time.time(), uuid.uuid4().hex
    store.execute("INSERT INTO sessions VALUES(?,?,?,?)", (session_id, body.title, now, now))
    return serialize(store.one("SELECT * FROM sessions WHERE id=?", (session_id,)))


@app.get("/api/sessions")
def list_sessions(q: str = "", _: None = Depends(authorize)):
    return store.all("SELECT * FROM sessions WHERE title LIKE ? ORDER BY updated_at DESC", (f"%{q}%",))


@app.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, body: SessionPatch, _: None = Depends(authorize)):
    if not store.one("SELECT id FROM sessions WHERE id=?", (session_id,)):
        raise HTTPException(404, "Session not found")
    store.execute("UPDATE sessions SET title=?,updated_at=? WHERE id=?", (body.title, time.time(), session_id))
    return store.one("SELECT * FROM sessions WHERE id=?", (session_id,))


@app.delete("/api/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, _: None = Depends(authorize)):
    active = store.one("SELECT id FROM runs WHERE session_id=? AND status IN ('queued','running','awaiting_approval')", (session_id,))
    if active:
        raise HTTPException(409, "Session has an active run")
    for table in ("messages", "runs"):
        store.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
    store.execute("DELETE FROM sessions WHERE id=?", (session_id,))


@app.get("/api/sessions/{session_id}/messages")
def messages(session_id: str, _: None = Depends(authorize)):
    return [serialize(r) for r in store.all("SELECT * FROM messages WHERE session_id=? ORDER BY created_at", (session_id,))]


@app.post("/api/sessions/{session_id}/runs")
async def create_run(
    session_id: str, task: str = Form(...), images: list[UploadFile] = File(default=[]),
    _: None = Depends(authorize),
):
    if not store.one("SELECT id FROM sessions WHERE id=?", (session_id,)):
        raise HTTPException(404, "Session not found")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    saved = []
    for image in images:
        if image.content_type not in ALLOWED_IMAGES:
            raise HTTPException(415, f"Unsupported image type: {image.content_type}")
        data = await image.read(MAX_UPLOAD + 1)
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Image exceeds 10 MB")
        suffix = mimetypes.guess_extension(image.content_type) or ".img"
        path = UPLOADS / f"{uuid.uuid4().hex}{suffix}"
        path.write_bytes(data)
        saved.append(str(path))
    now, run_id = time.time(), uuid.uuid4().hex
    store.execute(
        "INSERT INTO messages(id,session_id,role,content,attachments,created_at) VALUES(?,?,?,?,?,?)",
        (uuid.uuid4().hex, session_id, "user", task, json.dumps(saved), now),
    )
    store.execute(
        "INSERT INTO runs(id,session_id,task,images,status,created_at) VALUES(?,?,?,?,?,?)",
        (run_id, session_id, task, json.dumps(saved), "queued", now),
    )
    store.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
    cancel_events[run_id] = threading.Event()
    work_queue.put(run_id)
    refresh_positions()
    store.emit(run_id, "run_queued", {"run_id": run_id})
    return serialize(store.one("SELECT * FROM runs WHERE id=?", (run_id,)))


@app.get("/api/runs")
def runs(_: None = Depends(authorize)):
    return [serialize(r) for r in store.all("SELECT * FROM runs ORDER BY created_at DESC LIMIT 100")]


@app.get("/api/runs/{run_id}/events")
def events(run_id: str, after: int = 0, _: None = Depends(authorize)):
    if not store.one("SELECT id FROM runs WHERE id=?", (run_id,)):
        raise HTTPException(404, "Run not found")

    def stream():
        cursor = after
        idle = 0
        while True:
            rows = store.all("SELECT * FROM run_events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, cursor))
            if rows:
                idle = 0
                for row in rows:
                    cursor = row["seq"]
                    payload = {"seq": cursor, "type": row["type"], "data": json.loads(row["data"])}
                    yield f"id: {cursor}\nevent: {row['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                idle += 1
                yield ": keep-alive\n\n"
            run = store.one("SELECT status FROM runs WHERE id=?", (run_id,))
            if run and run["status"] in TERMINAL and idle >= 2:
                break
            time.sleep(.5)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.post("/api/runs/{run_id}/cancel")
def cancel(run_id: str, _: None = Depends(authorize)):
    row = store.one("SELECT status FROM runs WHERE id=?", (run_id,))
    if not row:
        raise HTTPException(404, "Run not found")
    if row["status"] in TERMINAL:
        return {"status": row["status"]}
    cancel_events.setdefault(run_id, threading.Event()).set()
    if row["status"] == "queued":
        store.execute("UPDATE runs SET status='cancelled',finished_at=? WHERE id=?", (time.time(), run_id))
        store.emit(run_id, "run_failed", {"error": "cancelled", "cancelled": True})
        refresh_positions()
    for approval_id, (gate, decision) in list(approval_waiters.items()):
        approval = store.one("SELECT run_id FROM approvals WHERE id=?", (approval_id,))
        if approval and approval["run_id"] == run_id:
            decision["approved"] = False
            gate.set()
    return {"status": "cancelling"}


@app.post("/api/approvals/{approval_id}")
def decide(approval_id: str, body: ApprovalInput, _: None = Depends(authorize)):
    row = store.one("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not row:
        raise HTTPException(404, "Approval not found")
    if row["status"] != "pending" or approval_id not in approval_waiters:
        raise HTTPException(409, "Approval already decided")
    status = "approved" if body.approved else "denied"
    store.execute("UPDATE approvals SET status=?,decided_at=? WHERE id=?", (status, time.time(), approval_id))
    gate, decision = approval_waiters[approval_id]
    decision["approved"] = body.approved
    gate.set()
    store.emit(row["run_id"], "approval_decided", {"approval_id": approval_id, "approved": body.approved})
    return {"status": status}


@app.get("/api/settings")
def settings(_: None = Depends(authorize)):
    values = {r["key"]: r["value"] for r in store.all("SELECT key,value FROM settings")}
    return {**values, "max_turns": int(values["max_turns"]),
            "api_key_configured": bool(os.getenv("DEEPSEEK_API_KEY"))}


@app.patch("/api/settings")
def update_settings(body: SettingsInput, _: None = Depends(authorize)):
    for key, value in body.model_dump(exclude_none=True).items():
        store.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
    return settings(_)


def safe_path(value: str) -> Path:
    candidate = (ROOT / value).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise HTTPException(403, "Path is outside the workspace")
    return candidate


@app.get("/api/files")
def files(path: str = "", _: None = Depends(authorize)):
    target = safe_path(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Directory not found")
    result = []
    for child in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name in {".git", ".runtime", "node_modules", "__pycache__"}:
            continue
        stat = child.stat()
        result.append({"name": child.name, "path": str(child.relative_to(ROOT)), "directory": child.is_dir(),
                       "size": stat.st_size, "modified_at": stat.st_mtime})
    return result


@app.get("/api/files/content")
def file_content(path: str, download: bool = False, _: None = Depends(authorize)):
    target = safe_path(path)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    if target.stat().st_size > 2 * 1024 * 1024:
        raise HTTPException(413, "Preview is limited to 2 MB")
    return FileResponse(target, filename=target.name if download else None)


WEB_DIST = ROOT / "web" / "dist"
if WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
