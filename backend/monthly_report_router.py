# -*- coding: utf-8 -*-
"""
monthly_report_router.py — Monthly / Quarterly / Half-year report.

Extends the legacy "Monthly Report.xlsx" with the months never filled in. Figures are
computed fresh from the live DB (see monthly_report_core.py for definitions). Endpoints:
  GET /monthly-report?year=2026&through=6   -> JSON (months + quarter + half rollups)
  GET /monthly-report/export?year=2026&through=6 -> .xlsx download (NEW sheets only; the
      original Monthly Report.xlsx on disk is copied and left untouched)
"""
import io
import os
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from auth import get_current_user
from perf_cache import cached
from pydantic import BaseModel
import models
import monthly_report_core as core
import report_builder as rb

router = APIRouter(prefix="/monthly-report", tags=["Monthly Report"])

ORIGINAL_XLSX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Monthly Report.xlsx")

# column order + headers for the exported / displayed table
COLUMNS = [
    ("label",        "Month"),
    ("reg_accounts", "Reg. Accounts"),
    ("verified",     "Verified"),
    ("kyc_pending",  "KYC Pending"),
    ("no_kyc",       "No KYC"),
    ("nda",          "NDA (new depositors)"),
    ("dep_clients",  "Depositing clients"),
    ("wd_clients",   "Withdrawing clients"),
    ("deposits",     "Deposits $"),
    ("withdrawals",  "Withdrawals $"),
    ("net",          "Net deposits $"),
    ("dep_count",    "Deposit count"),
    ("wd_count",     "Withdrawal count"),
    ("volume_lots",  "Volume (lots)"),
    ("markup",       "Markup revenue $"),
]
MONEY_FIELDS = {"deposits", "withdrawals", "net", "markup"}
FLOAT_FIELDS = {"volume_lots"}


def _make_execq(db: Session):
    def execq(sql, params):
        return db.execute(text(sql), params).fetchall()
    return execq


def _compute(db: Session, year: int, through: int):
    return core.build_report(_make_execq(db), year, through)


@router.get("")
def get_monthly_report(
    year: int = Query(None),
    through: int = Query(None, description="last month to include (1-12); defaults to current month"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    today = date.today()
    year = year or today.year
    through = through or (today.month if year == today.year else 12)
    through = max(1, min(12, through))
    data = cached(f"monthly_report:{year}:{through}", 600, lambda: _compute(db, year, through))
    data["columns"] = [{"key": k, "label": l} for k, l in COLUMNS]
    return data


@router.get("/export")
def export_monthly_report(
    year: int = Query(None),
    through: int = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    today = date.today()
    year = year or today.year
    through = through or (today.month if year == today.year else 12)
    through = max(1, min(12, through))
    data = _compute(db, year, through)

    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    # start from the original workbook so the existing sheets/data are preserved untouched
    if os.path.exists(ORIGINAL_XLSX):
        wb = openpyxl.load_workbook(ORIGINAL_XLSX)
    else:
        wb = openpyxl.Workbook()
        wb.remove(wb.active)

    hdr_fill = PatternFill("solid", fgColor="1F4E78")
    hdr_font = Font(bold=True, color="FFFFFF", size=11)
    roll_fill = PatternFill("solid", fgColor="DDEBF7")
    part_fill = PatternFill("solid", fgColor="FFF2CC")
    bold = Font(bold=True)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def write_sheet(title, rows, note=None):
        if title in wb.sheetnames:
            del wb[title]
        ws = wb.create_sheet(title)
        r0 = 1
        if note:
            ws.cell(r0, 1, note).font = Font(italic=True, color="808080", size=9)
            r0 += 2
        # header
        for ci, (k, label) in enumerate(COLUMNS, 1):
            cell = ws.cell(r0, ci, label)
            cell.fill = hdr_fill; cell.font = hdr_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
        # data
        for ri, row in enumerate(rows, r0 + 1):
            is_roll = row.get("_rollup")
            is_part = row.get("partial")
            for ci, (k, label) in enumerate(COLUMNS, 1):
                v = row.get(k)
                if k in MONEY_FIELDS and isinstance(v, (int, float)):
                    v = round(v, 2)
                elif k in FLOAT_FIELDS and isinstance(v, (int, float)):
                    v = round(v, 2)
                cell = ws.cell(ri, ci, v)
                cell.border = border
                if k in MONEY_FIELDS:
                    cell.number_format = '#,##0.00'
                elif k in FLOAT_FIELDS:
                    cell.number_format = '#,##0.00'
                elif k != "label":
                    cell.number_format = '#,##0'
                if is_roll:
                    cell.fill = roll_fill; cell.font = bold
                elif is_part and ci == 1:
                    cell.fill = part_fill
        # widths
        ws.column_dimensions['A'].width = 22
        for ci in range(2, len(COLUMNS) + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 15
        ws.freeze_panes = ws.cell(r0 + 1, 2)
        return ws

    note = (f"Auto-generated {data['generated_at']} from live broker_crm DB. "
            f"Definitions documented in monthly_report_core.py. Months after the last "
            f"hand-filled entry. Partial month highlighted. Does NOT alter original sheets.")

    # Monthly sheet (Jan..through)
    write_sheet(f"{year} Monthly (auto)", data["months"], note)
    # Quarterly sheet
    qrows = [{**q, "_rollup": True} for q in data["quarters"]]
    write_sheet(f"{year} Quarterly (auto)", qrows,
                "Quarterly rollups — each is a true distinct count over the quarter (not a sum of months).")
    # Half-year sheet
    hrows = [{**h, "_rollup": True} for h in data["halves"]]
    write_sheet(f"{year} Half-Year (auto)", hrows,
                "Half-year rollups — true distinct counts over the half-year range.")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"Monthly Report {year} (with auto months).xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Report builder (tabs) ─────────────────────────────────────────────────────
class ReportRequest(BaseModel):
    category: str
    group_by: list[str] | str | None = None  # multi-select: list of group dimensions
    period: str = "all_time"
    start: str | None = None
    end: str | None = None
    filters: dict = {}  # {key: [option, ...]} — multi-select, OR within a key


@router.get("/schema")
def report_schema(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """Filter + group-by schema for every report-builder tab (drives the UI controls).
    Sales team-leader + country option lists are pulled live from the DB."""
    return rb.get_schema(db)


@router.post("/run")
def run_builder(req: ReportRequest, db: Session = Depends(get_db),
                current_user: models.User = Depends(get_current_user)):
    return rb.run_report(db, req.category, req.dict())


def _build_report_xlsx(result: dict):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = result["category"][:28]
    hdr_fill = PatternFill("solid", fgColor="1F4E78")
    hdr_font = Font(bold=True, color="FFFFFF")
    bold = Font(bold=True)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    cols = result["columns"]
    # title + meta
    pr = result.get("period", {})
    ws.cell(1, 1, result["title"]).font = Font(bold=True, size=14)
    meta = f"Group by: {result.get('group_by')}  |  Period: {pr.get('preset')}"
    if pr.get("start"):
        meta += f" ({pr.get('start')} → {pr.get('end')})"
    ws.cell(2, 1, meta).font = Font(italic=True, color="808080", size=9)
    r0 = 4
    for ci, c in enumerate(cols, 1):
        cell = ws.cell(r0, ci, c["label"])
        cell.fill = hdr_fill; cell.font = hdr_font; cell.border = border
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    money_fmt = '#,##0.00'; int_fmt = '#,##0'
    for ri, row in enumerate(result["rows"], r0 + 1):
        for ci, c in enumerate(cols, 1):
            cell = ws.cell(ri, ci, row[ci - 1])
            cell.border = border
            if c["type"] in ("money", "float"):
                cell.number_format = money_fmt
            elif c["type"] == "int":
                cell.number_format = int_fmt
    if result.get("total_row"):
        rr = r0 + 1 + len(result["rows"])
        for ci, c in enumerate(cols, 1):
            cell = ws.cell(rr, ci, result["total_row"][ci - 1])
            cell.font = bold; cell.border = border
            if c["type"] in ("money", "float"):
                cell.number_format = money_fmt
            elif c["type"] == "int":
                cell.number_format = int_fmt
    ws.column_dimensions['A'].width = 26
    for ci in range(2, len(cols) + 1):
        ws.column_dimensions[get_column_letter(ci)].width = 16
    ws.freeze_panes = ws.cell(r0 + 1, 1)
    buf = io.BytesIO(); wb.save(buf); buf.seek(0)
    return buf


@router.post("/run/export")
def export_builder(req: ReportRequest, db: Session = Depends(get_db),
                   current_user: models.User = Depends(get_current_user)):
    result = rb.run_report(db, req.category, req.dict())
    buf = _build_report_xlsx(result)
    fname = f"{result['category']}_report.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Conversation box: natural language -> report spec -> table ─────────────────
import json as _json


def _schema_for_prompt(db):
    sch = rb.get_schema(db)
    lines = []
    for k, v in sch.items():
        gbs = [g[0] for g in v["group_by"]]
        fs = []
        for f in v["filters"]:
            opts = [str(o[0]) for o in f["opts"]][:14]
            fs.append(f"{f['key']}=[{'|'.join(opts)}]")
        lines.append(f"* {k}: group_by={gbs}; filters: {'; '.join(fs) or '(none)'}")
    return "\n".join(lines), [p[0] for p in rb.PERIOD_OPTS]


def _extract_json(s: str):
    i, j = s.find("{"), s.rfind("}")
    return s[i:j + 1] if (i >= 0 and j > i) else s


def _keyword_spec(q: str):
    ql = q.lower()
    cat = "clients"
    if "lead" in ql: cat = "leads"
    elif "withdraw" in ql: cat = "withdraw"
    elif "deposit" in ql: cat = "deposit"
    elif "sales" in ql or "agent" in ql: cat = "sales"
    elif "partner" in ql or " ib" in ql or ql.startswith("ib"): cat = "ib"
    elif "registration" in ql or "validation" in ql or "kyc" in ql: cat = "validation"
    elif "client" in ql: cat = "clients"
    gb = []
    for kw, d in [("by country", "country"), ("per country", "country"), ("by city", "city"),
                  ("by month", "month"), ("monthly", "month"), ("by source", "source"),
                  ("by method", "method"), ("by campaign", "campaign"), ("by level", "level")]:
        if kw in ql and d not in gb:
            gb.append(d)
    if not gb:
        gb = ["month"] if cat in ("deposit", "withdraw", "validation") else ["none"]
    period = "this_month"
    for kw, p in [("last month", "last_month"), ("last 3", "last_3m"), ("last 6", "last_6m"),
                  ("this year", "this_year"), ("last year", "last_year"), ("all time", "all_time"),
                  ("this month", "this_month")]:
        if kw in ql:
            period = p; break
    filters = {}
    if "verified" in ql and cat == "leads": filters["status"] = ["verified"]
    if "facebook" in ql: filters.setdefault("source", []).append("facebook")
    if "instagram" in ql: filters.setdefault("source", []).append("instagram")
    if "under ib" in ql or "with ib" in ql:
        filters["ib"] = ["under_ib"] if cat == "sales" else ["with_ib"]
    return {"category": cat, "group_by": gb, "period": period, "filters": filters, "title": q[:70]}


@router.post("/ask")
def report_ask(payload: dict, db: Session = Depends(get_db),
               current_user: models.User = Depends(get_current_user)):
    """Natural-language -> report. The admin types what they want; Claude maps it to a report
    spec (category/group-by/filters/period), we run it and return the table. Falls back to
    keyword matching if the AI is unavailable."""
    q = (payload or {}).get("question", "").strip()
    if not q:
        return {"error": "Please type what report you want."}
    schema_txt, periods = _schema_for_prompt(db)
    spec, explanation, used_ai = None, "", False
    try:
        import ai_config
        if ai_config.is_configured():
            import anthropic
            sysp = (
                "You convert a broker-CRM user's request into a JSON report spec. Return ONLY JSON:\n"
                '{"category","group_by":[...],"period","start","end","filters":{key:[values]},"title"}\n'
                "Available categories with their group_by keys and filters (option values):\n"
                f"{schema_txt}\n"
                f"Valid period presets: {periods}. For a custom range use period=\"custom\" with "
                "start/end as YYYY-MM-DD.\n"
                "Rules: choose ONE category; group_by is a list (use [\"none\"] for one total row, "
                "[\"month\"] for a trend, or e.g. [\"country\",\"month\"]); filters maps a filter key to a "
                "list of listed option values (country filters take the country name); omit unneeded "
                "filters; set a short human title. JSON only, no prose.")
            client = anthropic.Anthropic(api_key=ai_config.ANTHROPIC_API_KEY)
            model = getattr(ai_config, "MARKET_MODEL", None) or ai_config.CHAT_MODEL
            resp = client.messages.create(model=model, max_tokens=700, system=sysp,
                                           messages=[{"role": "user", "content": q}])
            txt = "".join(getattr(b, "text", "") for b in resp.content).strip()
            spec = _json.loads(_extract_json(txt))
            used_ai = True
    except Exception as e:
        explanation = f"(AI unavailable — used keyword matching: {str(e)[:80]})"
        spec = None
    if not spec:
        spec = _keyword_spec(q)
    cat = spec.get("category")
    if cat not in rb.CONFIG and cat != "sales":
        return {"error": f"Couldn't map that to a report (got category '{cat}'). Try naming a section "
                         "like leads, clients, deposits, withdrawals, IB, or sales.", "spec": spec}
    try:
        result = rb.run_report(db, cat, {
            "group_by": spec.get("group_by") or ["none"],
            "period": spec.get("period") or "this_month",
            "start": spec.get("start"), "end": spec.get("end"),
            "filters": spec.get("filters") or {},
        })
    except Exception as e:
        return {"error": f"Report failed: {str(e)[:120]}", "spec": spec}
    if not explanation:
        explanation = ("Interpreted by AI." if used_ai else "Interpreted by keyword matching.")
    return {"spec": spec, "explanation": explanation, "used_ai": used_ai,
            "title": spec.get("title") or result["title"], "result": result}
