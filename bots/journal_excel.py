"""
Excel workbook for the trade journal — journal/Trading_Journal.xlsx

Rebuilt from journal/trades.csv (+ daily notes pages) on every `trade_journal.py sync`.
Two-way for annotations: before rebuilding, edits you made in Excel to the yellow
columns on the Trades sheet (Setup, Exit reason, Notes, Charges) are read back into
trades.csv, so nothing you type in Excel is lost.

Sheets: Dashboard · Trades · Daily · Monthly · Notes · Rules
All totals are live Excel formulas over the Trades sheet.
"""
import os
import re
from datetime import datetime

from openpyxl import Workbook, load_workbook
from openpyxl.chart import LineChart, BarChart, Reference
from openpyxl.comments import Comment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

FONT = "Arial"
INR = '"₹"#,##0;[Red]-"₹"#,##0;"-"'
INR2 = '"₹"#,##0.00;[Red]-"₹"#,##0.00;"-"'
PCT = '0.0%;-0.0%;"-"'
HDR_FILL = PatternFill("solid", fgColor="1F3864")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")
SUB_FILL = PatternFill("solid", fgColor="D9E1F2")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GREEN_TXT = Font(name=FONT, color="006100")
RED_TXT = Font(name=FONT, color="9C0006")

# Trades sheet layout (column letters are referenced by formulas — keep in sync)
TRADE_COLS = [
    ("Trade ID", 14), ("Date", 12), ("Month", 9), ("Symbol", 26), ("Segment", 9), ("Side", 8),
    ("Qty", 7), ("Entry time", 10), ("Entry ₹", 10), ("Exit time", 10), ("Exit ₹", 10),
    ("Product", 14), ("Gross P&L ₹", 13), ("Charges ₹", 11), ("Charges source", 14),
    ("Net P&L ₹", 13), ("Return %", 10), ("Result", 8), ("Setup", 34), ("Exit reason", 26),
    ("Notes", 60), ("Entry order", 17), ("Exit order", 17),
]
EDITABLE = {"Setup": "setup", "Exit reason": "exit_reason", "Notes": "notes", "Charges ₹": "charges"}


def _font(bold=False, color="000000", size=10, italic=False):
    return Font(name=FONT, bold=bold, color=color, size=size, italic=italic)


def _header(ws, row, headers, widths=None):
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = _font(bold=True, color="FFFFFF")
        c.fill = HDR_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = BOX
        if widths:
            ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
    ws.row_dimensions[row].height = 30


# ── Read back Excel edits ─────────────────────────────────────────────────────

def read_back_edits(xlsx_path, rows):
    """Merge Setup / Exit reason / Notes / Charges edited in Excel into the CSV rows. Returns count changed."""
    if not os.path.exists(xlsx_path):
        return 0
    try:
        wb = load_workbook(xlsx_path, data_only=False)
    except Exception:
        return 0
    if "Trades" not in wb.sheetnames:
        return 0
    ws = wb["Trades"]
    head = [c.value for c in ws[1]]
    if "Trade ID" not in head:
        return 0
    idx = {h: i for i, h in enumerate(head)}
    by_id = {r["trade_id"]: r for r in rows}
    changed = 0
    for xr in ws.iter_rows(min_row=2, values_only=True):
        tid = xr[idx["Trade ID"]] if idx["Trade ID"] < len(xr) else None
        if not tid or tid not in by_id:
            continue
        r = by_id[tid]
        for col, key in EDITABLE.items():
            if col not in idx:
                continue
            val = xr[idx[col]]
            if val is None or (isinstance(val, str) and val.startswith("=")):
                continue
            if key == "charges":
                try:
                    val = round(float(val), 2)
                except (TypeError, ValueError):
                    continue
                if abs(val - float(r["charges"] or 0)) > 0.005:
                    r["charges"], r["charges_source"] = val, "excel"
                    r["net_pnl"] = round(float(r["gross_pnl"]) - val, 2)
                    changed += 1
            else:
                val = str(val).strip()
                if val and val != (r.get(key) or ""):
                    r[key] = val
                    changed += 1
    return changed


# ── Daily notes (from journal/daily/*.md) ─────────────────────────────────────

def parse_daily_notes(daily_dir, marker):
    out = []
    if not os.path.isdir(daily_dir):
        return out
    for name in sorted(os.listdir(daily_dir)):
        m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.md", name)
        if not m:
            continue
        with open(os.path.join(daily_dir, name), encoding="utf-8") as f:
            text = f.read()
        notes = text.split(marker, 1)[1] if marker in text else ""
        sections = {}
        for block in re.split(r"^## ", notes, flags=re.M)[1:]:
            title, _, body = block.partition("\n")
            body = "\n".join(l.strip() for l in body.strip().splitlines() if l.strip() and l.strip() != "-")
            sections[title.strip()] = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
        out.append((m.group(1), sections))
    return out


# ── Build workbook ────────────────────────────────────────────────────────────

def build_workbook(xlsx_path, rows, daily_notes, rules, charges_cfg):
    wb = Workbook()
    dash = wb.active
    dash.title = "Dashboard"
    tr = wb.create_sheet("Trades")
    daily = wb.create_sheet("Daily")
    monthly = wb.create_sheet("Monthly")
    notes = wb.create_sheet("Notes")
    rul = wb.create_sheet("Rules")

    rows = sorted(rows, key=lambda r: (r["date"], r["entry_time"]))
    n = len(rows)
    last = max(n + 1, 2)            # last data row on Trades
    rng = lambda col: f"Trades!${col}$2:${col}${last}"

    # ── Trades ────────────────────────────────────────────────────────────────
    _header(tr, 1, [c[0] for c in TRADE_COLS], [c[1] for c in TRADE_COLS])
    for i, r in enumerate(rows, 2):
        d = datetime.strptime(r["date"], "%Y-%m-%d")
        vals = [
            r["trade_id"], d, f'=TEXT(B{i},"yyyy-mm")', r["symbol"], r["segment"], r["side"],
            int(r["qty"]), r["entry_time"], float(r["entry_price"]), r["exit_time"], float(r["exit_price"]),
            r["product"],
            f'=IF(F{i}="LONG",(K{i}-I{i})*G{i},(I{i}-K{i})*G{i})',
            float(r["charges"]), r["charges_source"],
            f"=M{i}-N{i}",
            f"=IF(I{i}*G{i}=0,0,P{i}/(I{i}*G{i}))",
            f'=IF(P{i}>0,"WIN","LOSS")',
            r["setup"] or None, r["exit_reason"] or None, r["notes"] or None,
            r["entry_order"], r["exit_order"],
        ]
        for j, v in enumerate(vals, 1):
            c = tr.cell(row=i, column=j, value=v)
            c.font = _font()
            c.border = BOX
            c.alignment = Alignment(vertical="top", wrap_text=(j == 21))
        tr.cell(row=i, column=2).number_format = "dd-mmm-yyyy"
        for col in (9, 11):
            tr.cell(row=i, column=col).number_format = "#,##0.00"
            tr.cell(row=i, column=col).font = _font(color="0000FF")   # broker fill prices (inputs)
        for col in (13, 16):
            tr.cell(row=i, column=col).number_format = INR
        tr.cell(row=i, column=14).number_format = INR2
        tr.cell(row=i, column=17).number_format = PCT
        for col in (14, 19, 20, 21):                                   # editable in Excel
            tr.cell(row=i, column=col).fill = INPUT_FILL
            tr.cell(row=i, column=col).font = _font(color="0000FF")
    if n:
        table = Table(displayName="TradesTbl", ref=f"A1:{get_column_letter(len(TRADE_COLS))}{n + 1}")
        table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
        tr.add_table(table)
        tr.conditional_formatting.add(f"P2:P{last}", CellIsRule(operator="greaterThan", formula=["0"], font=GREEN_TXT))
        tr.conditional_formatting.add(f"P2:P{last}", CellIsRule(operator="lessThan", formula=["0"], font=RED_TXT))
    tr.freeze_panes = "B2"
    tr["N1"].comment = Comment("Estimated from Rules sheet rates until you type the contract-note figure here "
                               "(yellow cell). Next sync saves it to trades.csv.", "Journal")

    # ── Daily ─────────────────────────────────────────────────────────────────
    days = sorted({r["date"] for r in rows})
    _header(daily, 1, ["Date", "Trades", "Wins", "Losses", "Win %", "Gross P&L ₹", "Charges ₹",
                       "Net P&L ₹", "Cumulative ₹", "Best ₹", "Worst ₹"],
            [13, 8, 7, 8, 8, 13, 11, 13, 14, 11, 11])
    for i, ds in enumerate(days, 2):
        daily.cell(row=i, column=1, value=datetime.strptime(ds, "%Y-%m-%d")).number_format = "dd-mmm-yyyy"
        A = f"$A{i}"
        f = [
            f"=COUNTIF({rng('B')},{A})",
            f'=COUNTIFS({rng("B")},{A},{rng("P")},">0")',
            f"=B{i}-C{i}",
            f"=IF(B{i}=0,0,C{i}/B{i})",
            f"=SUMIF({rng('B')},{A},{rng('M')})",
            f"=SUMIF({rng('B')},{A},{rng('N')})",
            f"=SUMIF({rng('B')},{A},{rng('P')})",
            f"=H{i}" if i == 2 else f"=I{i - 1}+H{i}",
            f"=SUMPRODUCT(MAX(({rng('B')}={A})*{rng('P')}))",
            f"=-SUMPRODUCT(MAX(({rng('B')}={A})*(-{rng('P')})))",
        ]
        for j, v in enumerate(f, 2):
            c = daily.cell(row=i, column=j, value=v)
            c.font = _font()
        daily.cell(row=i, column=5).number_format = PCT
        for col in (6, 8, 9, 10, 11):
            daily.cell(row=i, column=col).number_format = INR
        daily.cell(row=i, column=7).number_format = INR2
        for col in range(1, 12):
            daily.cell(row=i, column=col).border = BOX
    dlast = max(len(days) + 1, 2)
    daily.conditional_formatting.add(f"H2:I{dlast}", CellIsRule(operator="greaterThan", formula=["0"], font=GREEN_TXT))
    daily.conditional_formatting.add(f"H2:I{dlast}", CellIsRule(operator="lessThan", formula=["0"], font=RED_TXT))
    daily.freeze_panes = "A2"
    if days:
        ch = LineChart()
        ch.title = "Equity curve (cumulative net P&L)"
        ch.y_axis.title = "₹"
        ch.x_axis.title = "Day"
        ch.add_data(Reference(daily, min_col=9, min_row=1, max_row=dlast), titles_from_data=True)
        ch.set_categories(Reference(daily, min_col=1, min_row=2, max_row=dlast))
        ch.x_axis.number_format = "dd-mmm"
        ch.height, ch.width = 7.5, 16
        _chart_fix(ch)
        daily.add_chart(ch, "M2")

    # ── Monthly ───────────────────────────────────────────────────────────────
    months = sorted({r["date"][:7] for r in rows})
    _header(monthly, 1, ["Month", "Trading days", "Trades", "Wins", "Win %", "Gross P&L ₹", "Charges ₹",
                         "Net P&L ₹", "Avg net / trade ₹", "Cumulative ₹"],
            [10, 13, 8, 7, 8, 13, 11, 13, 16, 14])
    for i, mo in enumerate(months, 2):
        monthly.cell(row=i, column=1, value=mo).font = _font()
        A = f"$A{i}"
        f = [
            f"=SUMPRODUCT((TEXT(Daily!$A$2:$A${dlast},\"yyyy-mm\")={A})*(Daily!$B$2:$B${dlast}>0))",
            f"=COUNTIF({rng('C')},{A})",
            f'=COUNTIFS({rng("C")},{A},{rng("P")},">0")',
            f"=IF(C{i}=0,0,D{i}/C{i})",
            f"=SUMIF({rng('C')},{A},{rng('M')})",
            f"=SUMIF({rng('C')},{A},{rng('N')})",
            f"=SUMIF({rng('C')},{A},{rng('P')})",
            f"=IF(C{i}=0,0,H{i}/C{i})",
            f"=H{i}" if i == 2 else f"=J{i - 1}+H{i}",
        ]
        for j, v in enumerate(f, 2):
            monthly.cell(row=i, column=j, value=v).font = _font()
        monthly.cell(row=i, column=5).number_format = PCT
        for col in (6, 8, 9, 10):
            monthly.cell(row=i, column=col).number_format = INR
        monthly.cell(row=i, column=7).number_format = INR2
        for col in range(1, 11):
            monthly.cell(row=i, column=col).border = BOX
    mlast = max(len(months) + 1, 2)
    if months:
        bc = BarChart()
        bc.title = "Net P&L by month"
        bc.y_axis.title = "₹"
        bc.add_data(Reference(monthly, min_col=8, min_row=1, max_row=mlast), titles_from_data=True)
        bc.set_categories(Reference(monthly, min_col=1, min_row=2, max_row=mlast))
        bc.height, bc.width = 7.5, 14
        _chart_fix(bc)
        monthly.add_chart(bc, "L2")
    monthly.freeze_panes = "A2"

    # ── Dashboard ─────────────────────────────────────────────────────────────
    dash.column_dimensions["A"].width = 30
    dash.column_dimensions["B"].width = 18
    dash.column_dimensions["C"].width = 3
    dash.column_dimensions["D"].width = 52
    dash["A1"] = "MCX Crude Trading Journal"
    dash["A1"].font = _font(bold=True, size=16, color="1F3864")
    dash["A2"] = f"Rebuilt from Angel One trade book · {datetime.now():%d %b %Y %H:%M}"
    dash["A2"].font = _font(italic=True, color="7F7F7F", size=9)
    stats = [
        ("All-time performance", None, None, None),
        ("Total trades", f"=COUNTA({rng('A')})", "0", "Closed round-trip trades"),
        ("Trading days", f"=COUNTA(Daily!$A$2:$A${dlast})", "0", ""),
        ("Wins", f'=COUNTIF({rng("P")},">0")', "0", "Net P&L > 0 after charges"),
        ("Losses", "=B5-B7", "0", ""),
        ("Win rate", "=IF(B5=0,0,B7/B5)", PCT, ""),
        ("Gross P&L", f"=SUM({rng('M')})", INR, "Before charges"),
        ("Charges", f"=SUM({rng('N')})", INR, "Estimates until contract-note figures are entered"),
        ("Net P&L", "=B10-B11", INR, "What actually hits the account"),
        ("Average win", f'=IFERROR(AVERAGEIF({rng("P")},">0"),0)', INR, ""),
        ("Average loss", f'=IFERROR(AVERAGEIF({rng("P")},"<=0"),0)', INR, ""),
        ("Win / loss ratio", "=IF(B14=0,0,ABS(B13/B14))", '0.00"x"', "Avg win ÷ avg loss"),
        ("Profit factor", f'=IFERROR(SUMIF({rng("P")},">0")/ABS(SUMIF({rng("P")},"<=0")),0)', '0.00"x"',
         "Total won ÷ total lost (>1.5 is good)"),
        ("Expectancy / trade", "=IF(B5=0,0,B12/B5)", INR, "Average net per trade"),
        ("Best trade", f"=MAX({rng('P')})", INR, ""),
        ("Worst trade", f"=MIN({rng('P')})", INR, ""),
        ("Best day", f"=MAX(Daily!$H$2:$H${dlast})", INR, ""),
        ("Worst day", f"=MIN(Daily!$H$2:$H${dlast})", INR, ""),
        ("Charges as % of gross", "=IF(B10<=0,0,B11/B10)", PCT, "Cost drag on winning edge"),
    ]
    r0 = 4
    for k, (label, formula, fmt, note) in enumerate(stats):
        row = r0 + k
        a = dash.cell(row=row, column=1, value=label)
        if formula is None:
            a.font = _font(bold=True, color="FFFFFF")
            a.fill = HDR_FILL
            dash.cell(row=row, column=2).fill = HDR_FILL
            continue
        a.font = _font(bold=label in ("Net P&L", "Win rate", "Profit factor"))
        a.border = BOX
        b = dash.cell(row=row, column=2, value=formula)
        b.number_format = fmt
        b.font = _font(bold=label == "Net P&L")
        b.border = BOX
        if note:
            dash.cell(row=row, column=4, value=note).font = _font(italic=True, color="7F7F7F", size=9)
    dash.conditional_formatting.add("B10:B22", CellIsRule(operator="greaterThan", formula=["0"], font=GREEN_TXT))
    dash.conditional_formatting.add("B10:B22", CellIsRule(operator="lessThan", formula=["0"], font=RED_TXT))
    lr = r0 + len(stats) + 1
    dash.cell(row=lr, column=1, value="How this file is maintained").font = _font(bold=True)
    legend = [
        "Run `python bots/trade_journal.py sync` after each session — it rebuilds this file.",
        "Yellow cells on Trades (Charges, Setup, Exit reason, Notes) are yours to edit in Excel;",
        "the next sync saves them back to trades.csv. Edits anywhere else are overwritten.",
        "Close the file in Excel before running sync (Windows locks open files).",
        "Blue text = broker fill prices / your inputs · black = formulas.",
    ]
    for k, t in enumerate(legend, 1):
        dash.cell(row=lr + k, column=1, value=t).font = _font(size=9, color="404040")

    # ── Notes ─────────────────────────────────────────────────────────────────
    note_cols = ["Market context", "What went well", "What to improve", "Plan for next session"]
    _header(notes, 1, ["Date"] + note_cols, [13, 55, 55, 55, 55])
    for i, (ds, sec) in enumerate(daily_notes, 2):
        notes.cell(row=i, column=1, value=datetime.strptime(ds, "%Y-%m-%d")).number_format = "dd-mmm-yyyy"
        for j, title in enumerate(note_cols, 2):
            c = notes.cell(row=i, column=j, value=sec.get(title) or None)
            c.alignment = Alignment(wrap_text=True, vertical="top")
            c.font = _font(size=9)
        notes.cell(row=i, column=1).alignment = Alignment(vertical="top")
        notes.cell(row=i, column=1).font = _font(bold=True)
        for col in range(1, 6):
            notes.cell(row=i, column=col).border = BOX
    notes.freeze_panes = "B2"
    notes.cell(row=len(daily_notes) + 3, column=1,
               value="Source: notes section of journal/daily/YYYY-MM-DD.md — edit there; this sheet is rebuilt on sync."
               ).font = _font(italic=True, size=9, color="7F7F7F")

    # ── Rules ─────────────────────────────────────────────────────────────────
    rul.column_dimensions["A"].width = 4
    rul.column_dimensions["B"].width = 95
    rul["B1"] = "Trading rules"
    rul["B1"].font = _font(bold=True, size=14, color="1F3864")
    for k, t in enumerate(rules, 3):
        rul.cell(row=k, column=1, value=k - 2).font = _font(bold=True)
        rul.cell(row=k, column=2, value=t).font = _font()
    cr = len(rules) + 5
    rul.cell(row=cr, column=2, value="Charge-estimate rates used for new trades (approximate — check contract notes)"
             ).font = _font(bold=True)
    items = [("Brokerage per executed order (₹)", charges_cfg["brokerage_per_order"]),
             ("Options — exchange txn (of turnover)", charges_cfg["OPT"]["txn"]),
             ("Options — CTT (of sell premium)", charges_cfg["OPT"]["ctt_sell"]),
             ("Options — stamp duty (of buy value)", charges_cfg["OPT"]["stamp_buy"]),
             ("Futures — exchange txn (of turnover)", charges_cfg["FUT"]["txn"]),
             ("Futures — CTT (of sell value)", charges_cfg["FUT"]["ctt_sell"]),
             ("SEBI fee (of turnover)", charges_cfg["sebi"]),
             ("GST (on brokerage + txn + SEBI)", charges_cfg["gst"])]
    for k, (label, v) in enumerate(items, cr + 1):
        rul.cell(row=k, column=2, value=f"{label}: {v:g}" if v >= 1 else f"{label}: {v * 100:.4g}%").font = _font(size=9)
    rul.cell(row=cr + len(items) + 2, column=2,
             value="Source: approximate Angel One / MCX rates; edit CHARGES in bots/trade_journal.py to change."
             ).font = _font(italic=True, size=9, color="7F7F7F")

    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = ws.title not in ("Dashboard", "Rules")
    wb.save(xlsx_path)


def _chart_fix(ch):
    ch.roundedCorners = False
    if ch.legend is not None:
        ch.legend.overlay = False
        ch.legend.position = "b"
    for t in (ch.title, ch.x_axis.title, ch.y_axis.title):
        if t is not None and hasattr(t, "overlay"):
            t.overlay = False
    ch.x_axis.delete = False
    ch.y_axis.delete = False
