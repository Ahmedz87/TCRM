# -*- coding: utf-8 -*-
"""
admin_ai_chat.py — the Reports-page AI chat for back-office admins (Abbas & co).

Back-and-forth Claude chat inside the CRM: ask questions, attach study photos / PDFs
(charts, receipts, analysis screenshots) for analysis, and request ANY report in plain
words — Claude calls the run_report tool, we execute it via report_builder and the table
renders inline in the chat with an Excel export. History persists per staff user.

Endpoints (staff auth):
  GET  /monthly-report/chat/history
  POST /monthly-report/chat          {message, attachments:[{name, media_type, data(b64)}]}
  POST /monthly-report/chat/clear
"""
import json
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from tickets_router import require_ticket_page  # Ticketing-page allowlist (Abbas/Ahmed/Laveen)
import models
import report_builder as rb

router = APIRouter(prefix="/monthly-report/chat", tags=["Admin AI chat"])


def _ensure_table(db):
    db.execute(text("""CREATE TABLE IF NOT EXISTS admin_ai_messages (
        id SERIAL PRIMARY KEY, user_id INT, role VARCHAR(12),
        content TEXT, attachments JSONB, reports JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW())"""))
    db.commit()


def _schema_prompt(db):
    sch = rb.get_schema(db)
    lines = []
    for k, v in sch.items():
        gbs = [g[0] for g in v["group_by"]]
        fs = []
        for f in v["filters"]:
            opts = [str(o[0]) for o in f["opts"]][:14]
            fs.append(f"{f['key']}=[{'|'.join(opts)}]")
        lines.append(f"* {k}: group_by={gbs}; filters: {'; '.join(fs) or '(none)'}")
    return "\n".join(lines)


TICKET_TOOL = {
    "name": "create_ticket",
    "description": ("File a ticket in the CRM ticketing center. Use when the admin asks for a "
                    "CHANGE, fix, new feature, data correction or any update to the CRM ('please "
                    "change X', 'add Y', 'this number looks wrong'). Confirm what was filed in "
                    "your reply. Do NOT use for report requests — use run_report for those."),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "one-line summary of the request"},
            "details": {"type": "string", "description": "full description incl. any numbers/pages mentioned"},
            "critical": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        },
        "required": ["title", "details"],
    },
}

REPORT_TOOL = {
    "name": "run_report",
    "description": ("Run a CRM report and get the table back. Use whenever the admin asks for "
                    "numbers, breakdowns, totals or lists from the CRM (deposits, withdrawals, "
                    "leads, clients, IB, sales agents, registrations/validation)."),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": ["validation", "leads", "clients", "ib",
                                                     "deposit", "withdraw", "sales"]},
            "group_by": {"type": "array", "items": {"type": "string"},
                         "description": "grouping dims, e.g. ['month'] or ['country','month']; ['none'] = one total row"},
            "period": {"type": "string",
                       "description": "this_month|last_month|last_3m|last_6m|this_year|last_year|all_time|custom"},
            "start": {"type": "string", "description": "YYYY-MM-DD (only with period=custom)"},
            "end": {"type": "string", "description": "YYYY-MM-DD (only with period=custom)"},
            "filters": {"type": "object", "description": "filter key -> list of option values (see schema)"},
            "title": {"type": "string", "description": "short human title for the table"},
        },
        "required": ["category"],
    },
}


def _compact(res, max_rows=30):
    """Small JSON view of a report for Claude (the full table goes to the UI)."""
    return {"title": res["title"], "columns": [c["label"] for c in res["columns"]],
            "rows": res["rows"][:max_rows], "total_row": res.get("total_row"),
            "n_rows_total": len(res["rows"]), "period": res.get("period")}


@router.get("/history")
def history(db: Session = Depends(get_db),
            current_user: models.User = Depends(require_ticket_page)):
    _ensure_table(db)
    rows = db.execute(text("""SELECT role, content, attachments, reports, created_at
        FROM admin_ai_messages WHERE user_id=:u ORDER BY id DESC LIMIT 60"""),
        {"u": current_user.id}).fetchall()
    out = []
    for r in reversed(rows):
        out.append({"role": r[0], "content": r[1] or "",
                    "attachments": [{"name": a.get("name", ""), "media_type": a.get("media_type", "")}
                                     for a in (r[2] or [])],
                    "reports": r[3] or [], "at": str(r[4])[:16]})
    return {"messages": out}


@router.post("/clear")
def clear(db: Session = Depends(get_db),
          current_user: models.User = Depends(require_ticket_page)):
    _ensure_table(db)
    db.execute(text("DELETE FROM admin_ai_messages WHERE user_id=:u"), {"u": current_user.id})
    db.commit()
    return {"ok": True}


@router.post("")
def send(payload: dict, db: Session = Depends(get_db),
         current_user: models.User = Depends(require_ticket_page)):
    """One chat turn -> {reply, reports:[{title, spec, result}]}. Claude may call
    run_report up to 3 times per turn; each result renders as a table in the chat."""
    import ai_config
    if not ai_config.is_configured():
        return {"error": "AI is not configured (backend/ai_config.py)."}
    import anthropic

    msg = (payload.get("message") or "").strip()
    atts = (payload.get("attachments") or [])[:4]
    if not msg and not atts:
        return {"error": "Empty message."}
    for a in atts:
        if len(a.get("data", "")) > 6_500_000:
            return {"error": f"Attachment {a.get('name', 'file')} is too large (max ~4.5MB)."}

    _ensure_table(db)
    # department/role scope: agent -> own clients, manager -> team, admin/director -> everything
    import rbac
    scope_ids = rbac.scope_agent_ids(db, current_user)
    scope_note = ("This user sees the WHOLE CRM (no scoping)." if scope_ids is None else
                  "IMPORTANT: every report is AUTOMATICALLY scoped to this user's department "
                  "(their own clients/team only) — phrase answers accordingly (e.g. 'your "
                  "clients deposited …'). Do not claim to show company-wide numbers.")
    sysp = (
        "You are the TNFX Broker-CRM AI assistant chatting with a staff member inside the CRM "
        f"Ticketing center. The user is {current_user.full_name or current_user.email} "
        f"(role: {current_user.role}). Be direct, numeric and concise; short paragraphs or "
        "bullets. You can analyse images/PDFs they attach (trading charts, study screenshots, "
        "receipts).\n"
        "- Report requests -> call run_report; never invent figures. After a tool result, give a "
        "short summary of the key numbers only (the full table renders automatically under your "
        "message; do not repeat it).\n"
        "- Change/update/fix requests ('please change X', 'add Y', 'this is wrong') -> call "
        "create_ticket so the request is filed for the team, then confirm the ticket number.\n"
        f"- {scope_note}\n\n"
        "run_report categories with group_by keys and filter options:\n"
        + _schema_prompt(db) +
        "\nPeriod presets: this_month, last_month, last_3m, last_6m, this_year, last_year, "
        "all_time, custom(start/end). Amounts are USD. Today: " + date.today().isoformat())

    # context: last 12 stored messages, text only (attachments live in the current turn only)
    hist = db.execute(text("""SELECT role, content FROM admin_ai_messages
        WHERE user_id=:u ORDER BY id DESC LIMIT 12"""), {"u": current_user.id}).fetchall()
    api_msgs = []
    for r in reversed(hist):
        if r[1]:
            role = "user" if r[0] == "user" else "assistant"
            if api_msgs and api_msgs[-1]["role"] == role:
                api_msgs[-1]["content"] += "\n" + r[1][:4000]
            else:
                api_msgs.append({"role": role, "content": r[1][:4000]})
    if api_msgs and api_msgs[0]["role"] != "user":
        api_msgs = api_msgs[1:]

    blocks = []
    for a in atts:
        mt = (a.get("media_type") or "").lower()
        if mt.startswith("image/"):
            blocks.append({"type": "image",
                           "source": {"type": "base64", "media_type": mt, "data": a.get("data", "")}})
        elif mt == "application/pdf":
            blocks.append({"type": "document",
                           "source": {"type": "base64", "media_type": mt, "data": a.get("data", "")}})
    blocks.append({"type": "text", "text": msg or "(see attachment)"})
    api_msgs.append({"role": "user", "content": blocks})

    client = anthropic.Anthropic(api_key=ai_config.ANTHROPIC_API_KEY)
    model = getattr(ai_config, "CHAT_MODEL", None) or "claude-opus-4-8"
    reports, tickets, reply = [], [], ""
    try:
        for _hop in range(4):
            resp = client.messages.create(model=model, max_tokens=1600, system=sysp,
                                           messages=api_msgs, tools=[REPORT_TOOL, TICKET_TOOL])
            texts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
            if texts:
                reply = "\n".join(texts).strip()
            tool_uses = [b for b in resp.content if getattr(b, "type", "") == "tool_use"]
            if not tool_uses or resp.stop_reason != "tool_use":
                break
            api_msgs.append({"role": "assistant", "content": resp.content})
            results_block = []
            for tu in tool_uses:
                spec = dict(tu.input or {})
                if tu.name == "create_ticket":
                    try:
                        tid = db.execute(text("""INSERT INTO tickets
                            (source, creator_type, creator_id, creator_name, section, note,
                             critical, route, page_url, status)
                            VALUES ('chat','staff',:uid,:un,'AI chat',:note,:crit,'review',
                                    '/tickets','under_review') RETURNING id"""),
                            {"uid": current_user.id,
                             "un": current_user.full_name or current_user.email,
                             "note": (spec.get("title", "") + "\n\n" + spec.get("details", "")).strip(),
                             "crit": spec.get("critical") or "medium"}).scalar()
                        db.commit()
                        tickets.append({"id": tid, "title": spec.get("title", "")})
                        content = json.dumps({"ok": True, "ticket_id": tid})
                    except Exception as e:
                        db.rollback()
                        content = json.dumps({"error": str(e)[:200]})
                else:
                    try:
                        res = rb.run_report(db, spec.get("category"), {
                            "group_by": spec.get("group_by") or ["none"],
                            "period": spec.get("period") or "this_month",
                            "start": spec.get("start"), "end": spec.get("end"),
                            "filters": spec.get("filters") or {},
                            "scope_agent_ids": scope_ids})
                        reports.append({"title": spec.get("title") or res["title"],
                                        "spec": spec, "result": res})
                        content = json.dumps(_compact(res), default=str)
                    except Exception as e:
                        db.rollback()
                        content = json.dumps({"error": str(e)[:200]})
                results_block.append({"type": "tool_result", "tool_use_id": tu.id,
                                      "content": content})
            api_msgs.append({"role": "user", "content": results_block})
    except Exception as e:
        return {"error": f"AI error: {str(e)[:180]}"}
    for t in tickets:                      # keep the ticket confirmation in the stored history
        tag = f"🎫 Ticket #{t['id']} filed: {t['title']}"
        if str(t["id"]) not in reply:
            reply = (reply + "\n" + tag).strip()

    if not reply:
        reply = "Here is the report." if reports else "(no reply)"

    # persist (attachment bytes NOT stored — name/type only)
    db.execute(text("""INSERT INTO admin_ai_messages (user_id, role, content, attachments)
        VALUES (:u,'user',:c,CAST(:a AS jsonb))"""),
        {"u": current_user.id, "c": msg,
         "a": json.dumps([{"name": a.get("name", ""), "media_type": a.get("media_type", "")}
                           for a in atts])})
    db.execute(text("""INSERT INTO admin_ai_messages (user_id, role, content, reports)
        VALUES (:u,'assistant',:c,CAST(:r AS jsonb))"""),
        {"u": current_user.id, "c": reply,
         "r": json.dumps([{"title": rp["title"], "spec": rp["spec"], "result": rp["result"]}
                           for rp in reports], default=str)})
    db.commit()
    return {"reply": reply, "reports": reports}
