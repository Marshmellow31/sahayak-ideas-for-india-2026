# -*- coding: utf-8 -*-
"""
Sahayak prototype backend — FastAPI + SQLite mock HRMS.
Run:  python -m uvicorn main:app --port 8000   (from the backend/ folder)

Transport seam (NFR-6): /api/chat is the single entry point. A Twilio
WhatsApp webhook adapter would translate inbound messages to the same call.
"""
import json
import sqlite3
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import engine

BASE = Path(__file__).parent
FRONTEND = BASE.parent / "frontend"
DB_PATH = BASE / "data" / "sahayak.db"

app = FastAPI(title="Sahayak Prototype")


# ---------------------------------------------------------------- database

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


SCHEMA = """
CREATE TABLE IF NOT EXISTS employees(
  id TEXT PRIMARY KEY, name TEXT, role TEXT, site TEXT, lang_pref TEXT);
CREATE TABLE IF NOT EXISTS leave_balances(
  emp_id TEXT PRIMARY KEY, casual INT, sick INT, earned INT);
CREATE TABLE IF NOT EXISTS leave_requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT, emp_id TEXT, type TEXT,
  from_date TEXT, to_date TEXT, reason TEXT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS shifts(
  emp_id TEXT, date TEXT, shift_code TEXT, start TEXT, end TEXT);
CREATE TABLE IF NOT EXISTS payslips(
  emp_id TEXT, month TEXT, gross INT, deductions INT, net INT);
CREATE TABLE IF NOT EXISTS attendance(
  emp_id TEXT, month TEXT, present INT, absent INT, leaves INT);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id TEXT, sender TEXT,
  text TEXT, meta TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS query_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id TEXT, ts TEXT, lang TEXT,
  intent TEXT, resolved INT, escalated INT, latency_ms INT, sop_id TEXT);
CREATE TABLE IF NOT EXISTS escalations(
  id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id TEXT, text TEXT, lang TEXT,
  priority INT, status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(
  id INTEGER PRIMARY KEY AUTOINCREMENT, worker_id TEXT, text TEXT,
  delivered INT DEFAULT 0, created_at TEXT);
"""

WORKERS = [
    ("W001", "Ramesh Solanki", "Housekeeping Staff — General Ward",
     "Seva Hospital, Bharuch", "hi"),
    ("W002", "Meena Vasava", "Lab Attendant — Pathology",
     "Seva Hospital, Bharuch", "gu"),
    ("W003", "Suresh Patel", "CNC Machine Operator",
     "Narmada Auto Components, Bharuch", "hi"),
]

SHIFT_PATTERNS = {
    "W001": [("A", "07:00", "15:00")] * 5 + [("OFF", "-", "-")] + [("A", "07:00", "15:00")],
    "W002": [("B", "13:00", "21:00")] * 3 + [("OFF", "-", "-")] + [("B", "13:00", "21:00")] * 3,
    "W003": [("N", "21:00", "05:00")] * 4 + [("OFF", "-", "-"), ("OFF", "-", "-")] + [("G", "09:00", "17:00")],
}


def seed():
    c = conn()
    c.executescript(SCHEMA)
    for tbl in ("employees", "leave_balances", "leave_requests", "shifts",
                "payslips", "attendance", "messages", "query_log",
                "escalations", "notifications"):
        c.execute(f"DELETE FROM {tbl}")
    c.executemany("INSERT INTO employees VALUES (?,?,?,?,?)", WORKERS)
    c.executemany("INSERT INTO leave_balances VALUES (?,?,?,?)",
                  [("W001", 7, 6, 11), ("W002", 9, 10, 15), ("W003", 3, 2, 8)])
    today = date.today()
    for wid, pattern in SHIFT_PATTERNS.items():
        for i in range(14):
            code, s, e = pattern[i % 7]
            c.execute("INSERT INTO shifts VALUES (?,?,?,?,?)",
                      (wid, (today + timedelta(days=i)).isoformat(), code, s, e))
    months = []
    for k in range(1, 4):
        m = today.replace(day=1) - timedelta(days=1)
        for _ in range(k - 1):
            m = m.replace(day=1) - timedelta(days=1)
        months.append(m.strftime("%b %Y"))
    gross = {"W001": 16500, "W002": 18200, "W003": 22400}
    for wid in gross:
        for i, mo in enumerate(months):
            g = gross[wid] + (0 if i else 500)
            ded = round(g * 0.132)
            c.execute("INSERT INTO payslips VALUES (?,?,?,?,?)",
                      (wid, mo, g, ded, g - ded))
    cur_m = today.strftime("%b %Y")
    c.executemany("INSERT INTO attendance VALUES (?,?,?,?,?)",
                  [("W001", cur_m, 15, 1, 1), ("W002", cur_m, 16, 0, 1),
                   ("W003", cur_m, 14, 2, 2)])

    def at(hh, mm):
        return datetime.combine(today, dtime(hh, mm)).isoformat()

    c.executemany(
        "INSERT INTO leave_requests(emp_id,type,from_date,to_date,reason,"
        "status,created_at) VALUES (?,?,?,?,?,?,?)", [
            ("W002", "sick", (today + timedelta(days=1)).isoformat(),
             (today + timedelta(days=1)).isoformat(),
             "તબિયત સારી નથી, તાવ છે", "approved", at(8, 12)),
            ("W003", "casual", (today + timedelta(days=3)).isoformat(),
             (today + timedelta(days=4)).isoformat(),
             "बहन की शादी है, दो दिन चाहिए", "pending", at(9, 40)),
        ])
    c.execute("INSERT INTO escalations(worker_id,text,lang,priority,status,"
              "created_at) VALUES (?,?,?,?,?,?)",
              ("W003", "पिछले महीने का ओवरटाइम पैसा नहीं आया, तीन बार बोला है",
               "hi", 2, "open", at(9, 55)))

    log = [
        ("W001", 7, 5, "hi", "sop_query", 1, 0, "HOSP-SF-02"),
        ("W001", 7, 31, "hi", "my_shifts", 1, 0, None),
        ("W001", 8, 2, "hi", "attendance", 1, 0, None),
        ("W002", 8, 12, "gu", "apply_leave", 1, 0, None),
        ("W002", 8, 30, "gu", "sop_query", 1, 0, "HOSP-SF-02"),
        ("W002", 9, 15, "gu", "payslip", 1, 0, None),
        ("W002", 11, 3, "en", "my_shifts", 1, 0, None),
        ("W003", 6, 48, "hi", "sop_query", 1, 0, "MFG-OP-01"),
        ("W003", 7, 20, "hi", "sop_query", 0, 0, "MFG-OP-01"),
        ("W003", 9, 40, "hi", "apply_leave", 1, 0, None),
        ("W003", 9, 55, "hi", "grievance", 0, 1, None),
        ("W003", 12, 10, "hi", "payslip", 1, 0, None),
    ]
    c.executemany(
        "INSERT INTO query_log(worker_id,ts,lang,intent,resolved,escalated,"
        "latency_ms,sop_id) VALUES (?,?,?,?,?,?,?,?)",
        [(w, at(h, m), lg, i, r, e, 900 + 130 * k, s)
         for k, (w, h, m, lg, i, r, e, s) in enumerate(log)])
    c.commit()
    c.close()
    engine.reset_sessions()


if not DB_PATH.exists():
    seed()
else:
    conn().executescript(SCHEMA)


# ------------------------------------------------------- Db facade for engine

class Db:
    def get_worker(self, wid):
        r = conn().execute("SELECT * FROM employees WHERE id=?", (wid,)).fetchone()
        return dict(r)

    def leave_balance(self, wid):
        r = conn().execute("SELECT casual, sick, earned FROM leave_balances "
                           "WHERE emp_id=?", (wid,)).fetchone()
        return dict(r)

    def create_leave_request(self, wid, ltype, from_date, reason):
        c = conn()
        cur = c.execute(
            "INSERT INTO leave_requests(emp_id,type,from_date,to_date,reason,"
            "status,created_at) VALUES (?,?,?,?,?,'pending',?)",
            (wid, ltype, from_date, from_date, reason, datetime.now().isoformat()))
        c.commit()
        return f"LR-{cur.lastrowid:04d}"

    def next_shifts(self, wid, days):
        rows = conn().execute(
            "SELECT date, shift_code, start, end FROM shifts WHERE emp_id=? "
            "AND date>=? ORDER BY date LIMIT ?",
            (wid, date.today().isoformat(), days)).fetchall()
        return [dict(r) for r in rows]

    def latest_payslip(self, wid):
        r = conn().execute("SELECT month, gross, deductions, net FROM payslips "
                           "WHERE emp_id=? ORDER BY rowid LIMIT 1", (wid,)).fetchone()
        return dict(r)

    def attendance(self, wid):
        r = conn().execute("SELECT present, absent, leaves FROM attendance "
                           "WHERE emp_id=?", (wid,)).fetchone()
        return dict(r)

    def create_escalation(self, wid, text, lang, priority):
        c = conn()
        cur = c.execute(
            "INSERT INTO escalations(worker_id,text,lang,priority,status,"
            "created_at) VALUES (?,?,?,?,'open',?)",
            (wid, text, lang, 1 if priority else 0, datetime.now().isoformat()))
        c.commit()
        return f"ES-{cur.lastrowid:04d}"


DB = Db()


# ---------------------------------------------------------------- API models

class ChatIn(BaseModel):
    worker_id: str
    text: str
    lang_hint: str | None = None


# ---------------------------------------------------------------- endpoints

@app.get("/")
def chat_page():
    return FileResponse(FRONTEND / "index.html")


@app.get("/dashboard")
def dash_page():
    return FileResponse(FRONTEND / "dashboard.html")


@app.get("/api/workers")
def workers():
    rows = conn().execute("SELECT * FROM employees").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/chat")
def chat(msg: ChatIn):
    t0 = time.time()
    reply = engine.answer(msg.worker_id, msg.text, msg.lang_hint, DB)
    latency = int((time.time() - t0) * 1000)
    now = datetime.now().isoformat()
    c = conn()
    c.execute("INSERT INTO messages(worker_id,sender,text,meta,ts) "
              "VALUES (?,?,?,?,?)", (msg.worker_id, "worker", msg.text, "{}", now))
    meta = json.dumps({"intent": reply["intent"], "lang": reply["lang"],
                       "citation": reply["citation"], "card": reply["card"]},
                      ensure_ascii=False)
    c.execute("INSERT INTO messages(worker_id,sender,text,meta,ts) "
              "VALUES (?,?,?,?,?)", (msg.worker_id, "sahayak", reply["text"], meta, now))
    c.execute("INSERT INTO query_log(worker_id,ts,lang,intent,resolved,"
              "escalated,latency_ms,sop_id) VALUES (?,?,?,?,?,?,?,?)",
              (msg.worker_id, now, reply["lang"], reply["intent"],
               1 if reply["resolved"] else 0, 1 if reply["escalated"] else 0,
               latency, (reply["citation"] or {}).get("doc_id")))
    c.commit()
    return reply


@app.get("/api/chat/history")
def history(worker_id: str):
    c = conn()
    notes = c.execute("SELECT id, text FROM notifications WHERE worker_id=? "
                      "AND delivered=0", (worker_id,)).fetchall()
    now = datetime.now().isoformat()
    for n in notes:
        c.execute("INSERT INTO messages(worker_id,sender,text,meta,ts) "
                  "VALUES (?,?,?,?,?)",
                  (worker_id, "sahayak", n["text"],
                   json.dumps({"intent": "notification"}), now))
        c.execute("UPDATE notifications SET delivered=1 WHERE id=?", (n["id"],))
    c.commit()
    rows = c.execute("SELECT sender, text, meta, ts FROM messages "
                     "WHERE worker_id=? ORDER BY id", (worker_id,)).fetchall()
    return [{"sender": r["sender"], "text": r["text"],
             "meta": json.loads(r["meta"] or "{}"), "ts": r["ts"]} for r in rows]


@app.get("/api/dashboard/summary")
def summary():
    c = conn()
    today = date.today().isoformat()
    q = lambda sql, *a: c.execute(sql, a).fetchone()[0]
    total = q("SELECT COUNT(*) FROM query_log WHERE ts LIKE ?", today + "%")
    resolved = q("SELECT COUNT(*) FROM query_log WHERE ts LIKE ? AND resolved=1",
                 today + "%")
    escal_open = q("SELECT COUNT(*) FROM escalations WHERE status='open'")
    active = q("SELECT COUNT(DISTINCT worker_id) FROM query_log WHERE ts LIKE ?",
               today + "%")
    langs = {r["lang"]: r["n"] for r in c.execute(
        "SELECT lang, COUNT(*) n FROM query_log WHERE ts LIKE ? GROUP BY lang",
        (today + "%",))}
    heat = [dict(r) for r in c.execute(
        "SELECT intent, COUNT(*) n FROM query_log WHERE ts LIKE ? "
        "GROUP BY intent ORDER BY n DESC", (today + "%",))]
    sop_heat = [dict(r) for r in c.execute(
        "SELECT sop_id, COUNT(*) n FROM query_log WHERE sop_id IS NOT NULL "
        "AND ts LIKE ? GROUP BY sop_id ORDER BY n DESC", (today + "%",))]
    return {
        "queries_today": total,
        "resolution_pct": round(100 * resolved / total) if total else 0,
        "deflection_pct": round(100 * resolved / total) if total else 0,
        "escalations_open": escal_open,
        "active_workers": active,
        "language_mix": langs,
        "intent_heatmap": heat,
        "sop_heatmap": sop_heat,
    }


@app.get("/api/dashboard/approvals")
def approvals():
    rows = conn().execute(
        "SELECT lr.id, lr.emp_id, e.name, e.role, lr.type, lr.from_date, "
        "lr.reason, lr.status, lr.created_at FROM leave_requests lr "
        "JOIN employees e ON e.id=lr.emp_id ORDER BY lr.id DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/approvals/{req_id}")
def decide(req_id: int, body: dict):
    action = body.get("action")
    if action not in ("approve", "reject"):
        return JSONResponse({"error": "action must be approve|reject"}, 400)
    c = conn()
    r = c.execute("SELECT * FROM leave_requests WHERE id=? AND status='pending'",
                  (req_id,)).fetchone()
    if not r:
        return JSONResponse({"error": "not found or already decided"}, 404)
    status = "approved" if action == "approve" else "rejected"
    c.execute("UPDATE leave_requests SET status=? WHERE id=?", (status, req_id))
    if status == "approved":
        c.execute(f"UPDATE leave_balances SET {r['type']}={r['type']}-1 "
                  "WHERE emp_id=?", (r["emp_id"],))
    w = c.execute("SELECT name, lang_pref FROM employees WHERE id=?",
                  (r["emp_id"],)).fetchone()
    note = engine.notification_text(status, w["name"], w["lang_pref"],
                                    r["type"], r["from_date"], f"LR-{req_id:04d}")
    c.execute("INSERT INTO notifications(worker_id,text,created_at) "
              "VALUES (?,?,?)", (r["emp_id"], note, datetime.now().isoformat()))
    c.commit()
    return {"ok": True, "status": status}


@app.get("/api/dashboard/escalations")
def escalations():
    rows = conn().execute(
        "SELECT es.id, es.worker_id, e.name, e.role, es.text, es.lang, "
        "es.priority, es.status, es.created_at FROM escalations es "
        "JOIN employees e ON e.id=es.worker_id "
        "ORDER BY es.status='open' DESC, es.priority DESC, es.id DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/escalations/{esc_id}/resolve")
def resolve(esc_id: int):
    c = conn()
    c.execute("UPDATE escalations SET status='resolved' WHERE id=?", (esc_id,))
    c.commit()
    return {"ok": True}


@app.post("/api/reset")
def reset():
    seed()
    return {"ok": True}


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
