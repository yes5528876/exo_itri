import os
from datetime import datetime
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DB_PATH = os.path.join(os.path.dirname(__file__), "exo_records.xlsx")

COLUMNS = [
    "record_id", "subject_name", "gender", "age", "height_cm", "weight_kg",
    "spring_k", "task_type", "condition", "timestamp",
    "theta_deg", "M_lumbar", "M_exo", "M_mus_exo",
    "F_c_bare", "F_c_exo", "reduction_percent", "load_index", "risk_flag",
]

COLUMN_LABELS = {
    "record_id": "紀錄編號",
    "subject_name": "姓名",
    "gender": "性別",
    "age": "年齡",
    "height_cm": "身高(cm)",
    "weight_kg": "體重(kg)",
    "spring_k": "彈簧係數",
    "task_type": "任務類型",
    "condition": "條件",
    "timestamp": "時間戳記",
    "theta_deg": "軀幹前傾角(°)",
    "M_lumbar": "腰椎力矩(N·m)",
    "M_exo": "外骨骼力矩(N·m)",
    "M_mus_exo": "背肌剩餘力矩(N·m)",
    "F_c_bare": "未穿戴壓迫力(N)",
    "F_c_exo": "穿戴壓迫力(N)",
    "reduction_percent": "減壓率(%)",
    "load_index": "負載指數",
    "risk_flag": "風險等級",
}

HEADER_FILL = PatternFill("solid", fgColor="2E75B6")
WARNING_FILL = PatternFill("solid", fgColor="FFD966")
HIGH_FILL = PatternFill("solid", fgColor="FF0000")
NORMAL_FILL = PatternFill("solid", fgColor="70AD47")

thin = Side(style="thin", color="CCCCCC")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def _get_or_create_wb():
    if os.path.exists(DB_PATH):
        wb = openpyxl.load_workbook(DB_PATH)
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Records"
        _write_header(ws)
        wb.save(DB_PATH)
    return wb


def _write_header(ws):
    for col_idx, col in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=COLUMN_LABELS.get(col, col))
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"


def _next_record_id(ws) -> str:
    max_row = ws.max_row
    if max_row <= 1:
        return "001"
    last_id = ws.cell(row=max_row, column=1).value
    try:
        num = int(str(last_id)) + 1
    except (TypeError, ValueError):
        num = max_row
    return f"{num:03d}"


def _auto_col_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 30)


def save_record(subject: dict, metrics: dict) -> str:
    wb = _get_or_create_wb()
    ws = wb["Records"]

    if ws.max_row == 1 and ws.cell(1, 1).value is None:
        _write_header(ws)

    record_id = _next_record_id(ws)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    row_data = {
        "record_id": record_id,
        "subject_name": subject.get("subject_name", ""),
        "gender": subject.get("gender", ""),
        "age": subject.get("age", ""),
        "height_cm": subject.get("height_cm", ""),
        "weight_kg": subject.get("weight_kg", ""),
        "spring_k": subject.get("spring_k", ""),
        "task_type": subject.get("task_type", ""),
        "condition": subject.get("condition", ""),
        "timestamp": timestamp,
        **metrics,
    }

    row_idx = ws.max_row + 1
    risk = metrics.get("risk_flag", "normal")

    for col_idx, col in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=row_idx, column=col_idx, value=row_data.get(col, ""))
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")
        if col == "risk_flag":
            if risk == "high":
                cell.fill = HIGH_FILL
                cell.font = Font(color="FFFFFF", name="Arial")
            elif risk == "warning":
                cell.fill = WARNING_FILL
                cell.font = Font(name="Arial")
            else:
                cell.fill = NORMAL_FILL
                cell.font = Font(color="FFFFFF", name="Arial")
        else:
            cell.font = Font(name="Arial")

    _auto_col_width(ws)
    wb.save(DB_PATH)
    return record_id


def load_records() -> list[dict]:
    if not os.path.exists(DB_PATH):
        return []
    wb = openpyxl.load_workbook(DB_PATH)
    ws = wb["Records"]
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 2:
        return []
    headers = [cell for cell in rows[0]]
    records = []
    for row in rows[1:]:
        records.append(dict(zip(headers, row)))
    return records


def export_summary(subject_name: str = None) -> str:
    """Export a summary sheet grouped by subject. Returns path."""
    wb = _get_or_create_wb()
    records = load_records()

    if subject_name:
        records = [r for r in records if str(r.get("姓名", "")) == subject_name]

    sheet_name = "Summary"
    if sheet_name in wb.sheetnames:
        del wb[sheet_name]
    ws_sum = wb.create_sheet(sheet_name)

    headers = ["姓名", "條件", "任務類型", "最大壓迫力(N)", "平均減壓率(%)", "高風險次數", "負載指數(最大)"]
    for ci, h in enumerate(headers, 1):
        cell = ws_sum.cell(1, ci, h)
        cell.font = Font(bold=True, color="FFFFFF", name="Arial")
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")
        cell.border = BORDER

    from collections import defaultdict
    groups = defaultdict(list)
    for r in records:
        key = (r.get("姓名", ""), r.get("條件", ""), r.get("任務類型", ""))
        groups[key].append(r)

    row_i = 2
    for (name, cond, task), recs in groups.items():
        def _float(v):
            try: return float(v)
            except: return 0.0
        f_c_col = "穿戴壓迫力(N)" if cond == "exo" else "未穿戴壓迫力(N)"
        max_fc = max(_float(r.get(f_c_col, 0)) for r in recs)
        avg_red = sum(_float(r.get("減壓率(%)", 0)) for r in recs) / len(recs)
        high_risk = sum(1 for r in recs if r.get("風險等級") == "high")
        max_li = max(_float(r.get("負載指數", 0)) for r in recs)
        row_data = [name, cond, task, round(max_fc, 1), round(avg_red, 2), high_risk, round(max_li, 3)]
        for ci, val in enumerate(row_data, 1):
            cell = ws_sum.cell(row_i, ci, val)
            cell.font = Font(name="Arial")
            cell.alignment = Alignment(horizontal="center")
            cell.border = BORDER
        row_i += 1

    _auto_col_width(ws_sum)
    wb.save(DB_PATH)
    return DB_PATH
