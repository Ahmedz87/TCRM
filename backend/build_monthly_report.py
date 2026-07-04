# -*- coding: utf-8 -*-
"""
build_monthly_report.py — one-shot generator for the extended Monthly Report .xlsx.
Reuses monthly_report_core + the same sheet-writing logic as the export endpoint, so the
file on disk matches what the report page exports. Writes a NEW file; never touches the
original "Monthly Report.xlsx".
  python build_monthly_report.py [--year 2026] [--through 6]
"""
import io, os, sys, argparse
from datetime import date
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from sqlalchemy import create_engine, text
import monthly_report_core as core
import monthly_report_router as rr

ap = argparse.ArgumentParser()
ap.add_argument('--year', type=int, default=date.today().year)
ap.add_argument('--through', type=int, default=date.today().month)
args = ap.parse_args()

import db_config
DSN = db_config.SQLALCHEMY_URL
eng = create_engine(DSN)

def execq(sql, params):
    with eng.connect() as conn:
        return conn.execute(text(sql), params).fetchall()

print(f"Computing {args.year} Jan..month {args.through} from live DB ...")
data = core.build_report(execq, args.year, args.through)

print("\n%-14s %8s %8s %6s %6s %5s %8s %8s %14s %14s %14s" % (
    "Month","Reg","Verif","KYC?","NoKYC","NDA","DepCl","WdCl","Deposits$","Withdraw$","Net$"))
for row in data["months"]:
    tag = "  (partial)" if row.get("partial") else ""
    print(f'{row["label"]:<14}{row["reg_accounts"]:>8d}{row["verified"]:>8d}{row["kyc_pending"]:>6d}{row["no_kyc"]:>6d}{row["nda"]:>6d}{row["dep_clients"]:>8d}{row["wd_clients"]:>8d}{row["deposits"]:>15,.0f}{row["withdrawals"]:>15,.0f}{row["net"]:>15,.0f}{tag}')
print("\nQuarters:")
for q in data["quarters"]:
    print(f'  {q["label"]:<10} ({q.get("months")}) reg={q["reg_accounts"]} nda={q["nda"]} dep$={q["deposits"]:,.0f} net$={q["net"]:,.0f}')
print("Half-year:")
for h in data["halves"]:
    print(f'  {h["label"]:<10} ({h.get("months")}) reg={h["reg_accounts"]} nda={h["nda"]} dep$={h["deposits"]:,.0f} net$={h["net"]:,.0f}')

# Build the workbook reusing the exact same writer as the endpoint
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
wb = openpyxl.load_workbook(rr.ORIGINAL_XLSX)
COLUMNS = rr.COLUMNS; MONEY_FIELDS = rr.MONEY_FIELDS; FLOAT_FIELDS = rr.FLOAT_FIELDS
hdr_fill = PatternFill("solid", fgColor="1F4E78"); hdr_font = Font(bold=True, color="FFFFFF", size=11)
roll_fill = PatternFill("solid", fgColor="DDEBF7"); part_fill = PatternFill("solid", fgColor="FFF2CC")
bold = Font(bold=True); thin = Side(style="thin", color="BFBFBF")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
def write_sheet(title, rows, note=None):
    if title in wb.sheetnames: del wb[title]
    ws = wb.create_sheet(title); r0 = 1
    if note:
        ws.cell(r0,1,note).font = Font(italic=True, color="808080", size=9); r0 += 2
    for ci,(k,label) in enumerate(COLUMNS,1):
        cell=ws.cell(r0,ci,label); cell.fill=hdr_fill; cell.font=hdr_font
        cell.alignment=Alignment(horizontal="center",vertical="center",wrap_text=True); cell.border=border
    for ri,row in enumerate(rows, r0+1):
        is_roll=row.get("_rollup"); is_part=row.get("partial")
        for ci,(k,label) in enumerate(COLUMNS,1):
            v=row.get(k)
            if k in MONEY_FIELDS|FLOAT_FIELDS and isinstance(v,(int,float)): v=round(v,2)
            cell=ws.cell(ri,ci,v); cell.border=border
            if k in MONEY_FIELDS|FLOAT_FIELDS: cell.number_format='#,##0.00'
            elif k!="label": cell.number_format='#,##0'
            if is_roll: cell.fill=roll_fill; cell.font=bold
            elif is_part and ci==1: cell.fill=part_fill
    ws.column_dimensions['A'].width=22
    for ci in range(2,len(COLUMNS)+1): ws.column_dimensions[get_column_letter(ci)].width=15
    ws.freeze_panes=ws.cell(r0+1,2)
note=(f"Auto-generated {data['generated_at']} from live broker_crm DB. Definitions in monthly_report_core.py. "
      f"Months after the last hand-filled entry; partial month highlighted. Original sheets unchanged.")
write_sheet(f"{args.year} Monthly (auto)", data["months"], note)
write_sheet(f"{args.year} Quarterly (auto)", [{**q,"_rollup":True} for q in data["quarters"]],
            "Quarterly rollups — true distinct counts over the quarter (not a sum of months).")
write_sheet(f"{args.year} Half-Year (auto)", [{**h,"_rollup":True} for h in data["halves"]],
            "Half-year rollups — true distinct counts over the half-year range.")
out = os.path.join(os.path.dirname(rr.ORIGINAL_XLSX), f"Monthly Report {args.year} (with auto months).xlsx")
wb.save(out)
print(f"\nSaved -> {out}")
print("Sheets:", wb.sheetnames)
