"""
Generate revised biomechanics specification document.
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
section = doc.sections[0]
section.page_width  = Inches(8.27)   # A4
section.page_height = Inches(11.69)
section.left_margin = section.right_margin = Inches(1.0)
section.top_margin  = section.bottom_margin = Inches(1.0)

# ── Styles ────────────────────────────────────────────────────────────────────
def style_normal(run, bold=False, size=11, color=None):
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Arial"
    if color:
        run.font.color.rgb = RGBColor(*color)

def add_heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.name = "Arial"
        if level == 1:
            run.font.size = Pt(16)
            run.font.color.rgb = RGBColor(0x2E, 0x75, 0xB6)
        elif level == 2:
            run.font.size = Pt(13)
            run.font.color.rgb = RGBColor(0x26, 0x51, 0x82)
        else:
            run.font.size = Pt(11)
            run.font.color.rgb = RGBColor(0x40, 0x40, 0x40)
    return p

def add_para(doc, text="", bold=False, size=11, color=None, indent=False):
    p = doc.add_paragraph()
    if indent:
        p.paragraph_format.left_indent = Cm(1.0)
    run = p.add_run(text)
    style_normal(run, bold=bold, size=size, color=color)
    return p

def add_formula(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(1.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(4)
    run = p.add_run(text)
    run.font.name = "Courier New"
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x6C)
    return p

def add_issue(doc, tag, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    tag_run = p.add_run(f"[{tag}] ")
    tag_run.bold = True
    tag_run.font.size = Pt(11)
    tag_run.font.name = "Arial"
    if tag == "錯誤":
        tag_run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
    elif tag == "修正":
        tag_run.font.color.rgb = RGBColor(0x00, 0x80, 0x00)
    else:
        tag_run.font.color.rgb = RGBColor(0xCC, 0x77, 0x00)
    body_run = p.add_run(text)
    body_run.font.size = Pt(11)
    body_run.font.name = "Arial"
    return p

def table_header_cell(cell, text):
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(10)
    run.font.name = "Arial"
    run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "2E75B6")
    tcPr.append(shd)

def table_cell(cell, text, align="LEFT", fill=None, bold=False):
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if align=="CENTER" else WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(text)
    run.font.size = Pt(10)
    run.font.name = "Arial"
    run.bold = bold
    if fill:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill)
        tcPr.append(shd)

# ══════════════════════════════════════════════════════════════════════════════
# TITLE
# ══════════════════════════════════════════════════════════════════════════════
title = doc.add_heading("外骨骼輔助人機介面 — 生物力學模型規格書（修訂版）", 0)
for run in title.runs:
    run.font.name = "Arial"
    run.font.size = Pt(18)
    run.font.color.rgb = RGBColor(0x1F, 0x38, 0x82)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = sub.add_run("基於原始需求文件的公式審查與修正  |  2025")
r.font.size = Pt(10)
r.font.color.rgb = RGBColor(0x70, 0x70, 0x70)
r.font.name = "Arial"

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1: 原文公式問題彙整
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "一、原始文件公式問題彙整", level=1)
add_para(doc, "經逐條審查原需求文件中的生物力學公式，共發現以下五項問題：")
doc.add_paragraph()

issues = [
    ("錯誤", "M_lumbar 公式缺少重力加速度 g",
     "原文寫為 M_lumbar = W_upper × d × sin(θ)，W_upper 的單位為 kg（質量），\n"
     "力矩計算須乘以 g = 9.81 m/s²。正確應為：\n"
     "M_lumbar = W_upper [kg] × g [9.81 m/s²] × d_COM [m] × sin(θ)"),

    ("錯誤", "F_mus（未穿戴）公式計算方式錯誤",
     "原文出現「F_mus = W_upper × 9.81」，這是上半身重力，不是背肌力。\n"
     "正確計算背肌力應使用力矩平衡原理：\n"
     "F_mus = M_lumbar / d_mus（其中 d_mus ≈ 0.05 m，豎脊肌有效力臂）"),

    ("錯誤", "F_c_exo 公式缺少重力加速度 g",
     "原文寫為 F_c_exo = W_upper × cos(θ) + M_mus_exo / d_mus，\n"
     "第一項 W_upper 單位為 kg，須乘以 g 才能得到力（N）。\n"
     "正確應為：F_c_exo = W_upper × g × cos(θ) + M_mus_exo / d_mus"),

    ("錯誤", "減壓率公式分母錯誤",
     "原文寫為 Reduction% = (F_c_bare - F_c_exo) / F_c_exo × 100%，\n"
     "分母應為基準值 F_c_bare（未穿戴），不是 F_c_exo。\n"
     "正確應為：Reduction% = (F_c_bare - F_c_exo) / F_c_bare × 100%"),

    ("建議", "M_exo 線性模型的適用範圍說明不足",
     "原文同時提到 M_exo = K×θ 和 M_exo = F1 + K×θ 兩種模型，造成混淆。\n"
     "對於被動式彈簧外骨骼（自然長度在直立位），校正後 θ=0° 時彈簧無預壓，\n"
     "使用 M_exo = k × θ 即可。若有預壓（F1>0），才需用 F1 + k×θ 模型，\n"
     "本規格書採用無預壓版本（k 的單位：Nm/deg）。"),
]

for tag, title_text, body in issues:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    tag_run = p.add_run(f"[{tag}] ")
    tag_run.bold = True
    tag_run.font.size = Pt(11)
    tag_run.font.name = "Arial"
    if tag == "錯誤":
        tag_run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
    else:
        tag_run.font.color.rgb = RGBColor(0xCC, 0x77, 0x00)
    title_run = p.add_run(title_text)
    title_run.bold = True
    title_run.font.size = Pt(11)
    title_run.font.name = "Arial"

    for line in body.split("\n"):
        bp = doc.add_paragraph()
        bp.paragraph_format.left_indent = Cm(1.5)
        bp.paragraph_format.space_before = Pt(0)
        bp.paragraph_format.space_after  = Pt(2)
        br = bp.add_run(line)
        br.font.size = Pt(10.5)
        br.font.name = "Arial"

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2: 參數定義表
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "二、參數定義與預設值", level=1)
add_para(doc, "下表列出所有生物力學計算所需參數的定義、單位與本系統採用之預設值：")
doc.add_paragraph()

tbl = doc.add_table(rows=1, cols=5)
tbl.style = "Table Grid"
hdr = tbl.rows[0].cells
for cell, text in zip(hdr, ["符號", "說明", "單位", "預設值", "參考來源"]):
    table_header_cell(cell, text)

params = [
    ("θ",        "校正後軀幹前傾角（Trunk Flexion Angle）",  "degree",  "IMU 即時量測",      "IMU 校正後歸零"),
    ("W_body",   "受測者全身體重",                           "kg",      "輸入欄位",           "—"),
    ("W_upper",  "腰部以上體重（= 0.6 × W_body）",          "kg",      "0.6 × W_body",       "Winter (2009): 55–67%"),
    ("g",        "重力加速度",                               "m/s²",    "9.81",               "物理常數"),
    ("d_COM",    "上半身質心到 L5-S1 距離",                  "m",       "0.30",               "文獻範圍 0.25–0.35 m"),
    ("d_mus",    "豎脊肌有效力臂（到脊椎中心）",            "m",       "0.05",               "解剖學常數 0.04–0.06 m"),
    ("k",        "被動式外骨骼彈簧係數",                    "Nm/deg",  "使用者輸入",          "廠商規格書"),
    ("F_c_NIOSH","NIOSH 腰椎壓迫力傷害臨界值",              "N",       "3400",               "NIOSH 1994"),
]

fill_alt = "EBF3FB"
for i, (sym, desc, unit, default, ref) in enumerate(params):
    row = tbl.add_row()
    fill = fill_alt if i % 2 == 0 else None
    table_cell(row.cells[0], sym,     "CENTER", fill, bold=True)
    table_cell(row.cells[1], desc,    "LEFT",   fill)
    table_cell(row.cells[2], unit,    "CENTER", fill)
    table_cell(row.cells[3], default, "CENTER", fill)
    table_cell(row.cells[4], ref,     "LEFT",   fill)

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3: 修正後完整公式
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "三、修正後完整生物力學公式", level=1)
add_para(doc, "以下為經審查修正後的完整計算流程，已全部對應實作於 calculations.py。")
doc.add_paragraph()

# 3.1
add_heading(doc, "3.1 上半身有效重量", level=2)
add_para(doc, "將受測者體重換算為腰部以上承重質量：")
add_formula(doc, "W_upper = 0.6 × W_body                [kg]")
add_para(doc, "（0.6 為人體上半身佔全身質量比例的常用近似值，文獻範圍 0.55–0.67）", indent=True)
doc.add_paragraph()

# 3.2
add_heading(doc, "3.2 腰椎平衡力矩（Lumbar Moment）", level=2)
add_para(doc, "前傾角 θ 時，維持軀幹平衡所需的腰椎力矩（修正：加入 g）：")
add_formula(doc, "M_lumbar = W_upper × g × d_COM × sin(θ)          [N·m]")
add_para(doc, "▶ θ 越大，sin(θ) 越大 → M_lumbar 非線性飆升（主要驅動腰椎風險的因子）", indent=True)
doc.add_paragraph()

# 3.3
add_heading(doc, "3.3 外骨骼輔助力矩（Exoskeleton Moment）", level=2)
add_para(doc, "被動式彈簧外骨骼，校正後直立位（θ = 0°）時無預壓：")
add_formula(doc, "M_exo = k × θ                                     [N·m]")
add_para(doc, "▶ k 單位為 Nm/deg；若廠商規格為 N·m/rad，需換算（× 180/π ≈ × 57.3）", indent=True)
add_para(doc, "▶ 若彈簧有預壓力 F1（初始預壓大於 0），改用：M_exo = F1 + k × θ", indent=True)
doc.add_paragraph()

# 3.4
add_heading(doc, "3.4 穿戴後背肌剩餘力矩", level=2)
add_para(doc, "外骨骼分擔部分力矩後，背肌仍需承擔的剩餘力矩：")
add_formula(doc, "M_mus_exo = max(0, M_lumbar - M_exo)              [N·m]")
add_para(doc, "▶ max(0, …) 確保外骨骼不會對背肌產生「負力矩」（過度輔助時限制為 0）", indent=True)
doc.add_paragraph()

# 3.5
add_heading(doc, "3.5 未穿戴腰椎壓迫力 F_c_bare", level=2)
add_para(doc, "L5-S1 椎間盤所受總壓力由兩部分組成（修正：F_c_bare 的 W_upper 須乘 g）：")
add_formula(doc, "F_mus_bare = M_lumbar / d_mus                     [N]")
add_formula(doc, "F_c_bare   = W_upper × g × cos(θ) + F_mus_bare  [N]")
add_para(doc, "▶ 第一項：上半身重力在脊椎軸方向的分力（垂直壓縮）", indent=True)
add_para(doc, "▶ 第二項：豎脊肌收縮力傳遞到椎間盤的壓力（通常是主要貢獻項）", indent=True)
doc.add_paragraph()

# 3.6
add_heading(doc, "3.6 穿戴外骨骼腰椎壓迫力 F_c_exo", level=2)
add_para(doc, "外骨骼輔助後，背肌需求降低，椎間盤壓力隨之降低（修正：加入 g）：")
add_formula(doc, "F_mus_exo  = M_mus_exo / d_mus                   [N]")
add_formula(doc, "F_c_exo    = W_upper × g × cos(θ) + F_mus_exo  [N]")
doc.add_paragraph()

# 3.7
add_heading(doc, "3.7 外骨骼減壓率（修正分母）", level=2)
add_para(doc, "相對於未穿戴基準的腰椎壓力降低百分比（修正：分母改為 F_c_bare）：")
add_formula(doc, "Reduction% = (F_c_bare - F_c_exo) / F_c_bare × 100%")
add_para(doc, "▶ 設計良好的腰部外骨骼，θ > 45° 時約可降低 20%–40%", indent=True)
doc.add_paragraph()

# 3.8
add_heading(doc, "3.8 負載指數（Load Index）", level=2)
add_para(doc, "以 NIOSH 3400 N 臨界值為基準的無因次風險指標：")
add_formula(doc, "LI = F_c / 3400")
add_para(doc, "▶ 其中 F_c 為當前條件下的椎間盤壓力（bare 或 exo 條件）", indent=True)

tbl2 = doc.add_table(rows=4, cols=3)
tbl2.style = "Table Grid"
for cell, text in zip(tbl2.rows[0].cells, ["LI 範圍", "風險等級", "說明"]):
    table_header_cell(cell, text)
risk_rows = [
    ("LI < 0.75",    "低風險 (normal)",   "F_c < 2550 N，安全操作", "D5F0D5"),
    ("0.75 ≤ LI ≤ 1.0", "中等風險 (warning)", "F_c = 2550–3400 N，需留意", "FFF2CC"),
    ("LI > 1.0",     "高風險 (high)",     "F_c > 3400 N，超過 NIOSH 上限", "FFD5D5"),
]
for (li_range, level, desc, fill) in risk_rows:
    row = tbl2.add_row()
    table_cell(row.cells[0], li_range, "CENTER", fill, bold=True)
    table_cell(row.cells[1], level,    "CENTER", fill, bold=True)
    table_cell(row.cells[2], desc,     "LEFT",   fill)

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4: 完整計算流程圖（文字版）
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "四、完整計算流程（對應 calculations.py）", level=1)

steps = [
    ("INPUT",    "θ [deg], W_body [kg], k [Nm/deg], condition {bare|exo}"),
    ("STEP 1",   "W_upper  = 0.6 × W_body"),
    ("STEP 2",   "M_lumbar = W_upper × 9.81 × 0.30 × sin(θ)"),
    ("STEP 3",   "M_exo    = k × θ"),
    ("STEP 4",   "M_mus_exo = max(0, M_lumbar - M_exo)"),
    ("STEP 5a",  "F_mus_bare = M_lumbar / 0.05"),
    ("STEP 5b",  "F_c_bare   = W_upper × 9.81 × cos(θ) + F_mus_bare"),
    ("STEP 6a",  "F_mus_exo  = M_mus_exo / 0.05"),
    ("STEP 6b",  "F_c_exo    = W_upper × 9.81 × cos(θ) + F_mus_exo"),
    ("STEP 7",   "Reduction% = (F_c_bare - F_c_exo) / F_c_bare × 100"),
    ("STEP 8",   "LI = F_c_display / 3400  →  risk_flag"),
    ("OUTPUT",   "M_lumbar, M_exo, M_mus_exo, F_c_bare, F_c_exo, Reduction%, LI, risk_flag"),
]

tbl3 = doc.add_table(rows=1, cols=2)
tbl3.style = "Table Grid"
for cell, text in zip(tbl3.rows[0].cells, ["步驟", "計算式"]):
    table_header_cell(cell, text)

for i, (step, formula) in enumerate(steps):
    row = tbl3.add_row()
    fill = "EBF3FB" if i % 2 == 0 else None
    if step in ("INPUT", "OUTPUT"):
        fill = "D9E2F3"
    table_cell(row.cells[0], step,    "CENTER", fill, bold=(step in ("INPUT","OUTPUT")))
    table_cell(row.cells[1], formula, "LEFT",   fill)

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5: 模型假設與限制
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "五、模型假設與適用限制", level=1)

assumptions = [
    ("準靜態假設",
     "本模型忽略動態加速度（慣性力），假設動作緩慢且近似靜態平衡。"
     "實際護理搬運（如移床）涉及加速，真實椎間盤壓力會高於模型估算值。"),
    ("單肌肉模型",
     "使用單一等效背肌（豎脊肌）代表所有腰背伸肌群。"
     "實際上涉及多組肌肉共同作用，此模型為工程近似，"
     "但在評估相對減壓效果時仍具參考價值。"),
    ("上半身重量比例固定",
     "W_upper = 0.6 × W_body 為固定比例，未考慮受測者體型差異。"
     "文獻範圍為 0.55–0.67，建議未來可加入實際量測或依 BMI 調整。"),
    ("外骨骼線性彈簧模型",
     "M_exo = k × θ 為線性近似，適用於低速動作。"
     "若外骨骼為氣壓棒（Pneumatic Actuator），其力-行程關係為非線性，"
     "應替換為廠商提供的 Lookup Table 或氣體力學公式。"),
    ("不考慮外部負載",
     "目前計算未加入受測者手持物品的重量（W_load = 0）。"
     "若需評估搬運情境，應在 W_upper 中加入搬運物重量：W_upper = 0.6×W_body + W_load。"),
]

for title_text, body_text in assumptions:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    t_run = p.add_run(f"▶ {title_text}：")
    t_run.bold = True
    t_run.font.size = Pt(11)
    t_run.font.name = "Arial"
    b_run = p.add_run(body_text)
    b_run.font.size = Pt(10.5)
    b_run.font.name = "Arial"

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6: 數值驗證範例
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "六、數值驗證範例", level=1)
add_para(doc, "以受測者體重 65 kg、軀幹前傾角 θ = 45°、彈簧係數 k = 0.5 Nm/deg 為例：")
doc.add_paragraph()

example = [
    ("W_upper",     "0.6 × 65 = 39 kg"),
    ("M_lumbar",    "39 × 9.81 × 0.30 × sin(45°) = 39 × 9.81 × 0.30 × 0.707 ≈ 81.4 N·m"),
    ("M_exo",       "0.5 × 45 = 22.5 N·m"),
    ("M_mus_exo",   "81.4 - 22.5 = 58.9 N·m"),
    ("F_mus_bare",  "81.4 / 0.05 = 1628 N"),
    ("F_c_bare",    "39 × 9.81 × cos(45°) + 1628 = 270.7 + 1628 ≈ 1899 N"),
    ("F_mus_exo",   "58.9 / 0.05 = 1178 N"),
    ("F_c_exo",     "39 × 9.81 × cos(45°) + 1178 = 270.7 + 1178 ≈ 1449 N"),
    ("Reduction%",  "(1899 - 1449) / 1899 × 100 ≈ 23.7%"),
    ("LI (bare)",   "1899 / 3400 ≈ 0.559  →  低風險"),
    ("LI (exo)",    "1449 / 3400 ≈ 0.426  →  低風險"),
]

tbl4 = doc.add_table(rows=1, cols=2)
tbl4.style = "Table Grid"
for cell, text in zip(tbl4.rows[0].cells, ["變數", "計算結果"]):
    table_header_cell(cell, text)

for i, (var, val) in enumerate(example):
    row = tbl4.add_row()
    fill = "EBF3FB" if i % 2 == 0 else None
    table_cell(row.cells[0], var, "LEFT",  fill, bold=True)
    table_cell(row.cells[1], val, "LEFT",  fill)

doc.add_paragraph()

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7: 資料庫欄位
# ══════════════════════════════════════════════════════════════════════════════
add_heading(doc, "七、Excel 資料庫欄位定義", level=1)

db_cols = [
    ("record_id",          "紀錄編號",       "—",     "自動產生 001–999"),
    ("subject_name",       "姓名",           "—",     "中英文"),
    ("gender",             "性別",           "—",     "男 / 女"),
    ("age",                "年齡",           "歲",    ""),
    ("height_cm",          "身高",           "cm",    ""),
    ("weight_kg",          "體重",           "kg",    ""),
    ("spring_k",           "彈簧係數",       "Nm/deg",""),
    ("task_type",          "任務類型",       "—",     "擺位 / 移床"),
    ("condition",          "條件",           "—",     "bare / exo"),
    ("timestamp",          "時間戳記",       "—",     "自動代入電腦時間"),
    ("theta_deg",          "軀幹前傾角",     "°",     "IMU 即時量測"),
    ("M_lumbar",           "腰椎平衡力矩",   "N·m",   "STEP 2"),
    ("M_exo",              "外骨骼輔助力矩", "N·m",   "STEP 3"),
    ("M_mus_exo",          "背肌剩餘力矩",   "N·m",   "STEP 4"),
    ("F_c_bare",           "未穿戴壓迫力",   "N",     "STEP 5b"),
    ("F_c_exo",            "穿戴壓迫力",     "N",     "STEP 6b"),
    ("reduction_percent",  "外骨骼有效率",   "%",     "STEP 7"),
    ("load_index",         "負載指數",       "—",     "STEP 8"),
    ("risk_flag",          "風險等級",       "—",     "normal / warning / high"),
]

tbl5 = doc.add_table(rows=1, cols=4)
tbl5.style = "Table Grid"
for cell, text in zip(tbl5.rows[0].cells, ["欄位名稱", "中文說明", "單位", "備註"]):
    table_header_cell(cell, text)

for i, (col, label, unit, note) in enumerate(db_cols):
    row = tbl5.add_row()
    fill = "EBF3FB" if i % 2 == 0 else None
    table_cell(row.cells[0], col,   "LEFT",   fill, bold=True)
    table_cell(row.cells[1], label, "LEFT",   fill)
    table_cell(row.cells[2], unit,  "CENTER", fill)
    table_cell(row.cells[3], note,  "LEFT",   fill)

doc.add_paragraph()

# ── Footer note ───────────────────────────────────────────────────────────────
p_footer = doc.add_paragraph()
p_footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
p_footer.paragraph_format.space_before = Pt(20)
r1 = p_footer.add_run("本文件由 Claude 根據生物力學文獻與原需求文件自動審查生成  |  ")
r1.font.size = Pt(9)
r1.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
r1.font.name = "Arial"
r2 = p_footer.add_run("參考：McGill (2007), Winter (2009), NIOSH (1994)")
r2.font.size = Pt(9)
r2.font.italic = True
r2.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
r2.font.name = "Arial"

# ── Save ──────────────────────────────────────────────────────────────────────
output_path = r"C:\Users\long\Desktop\exo\外骨骼_生物力學規格書_修訂版.docx"
doc.save(output_path)
print(f"Saved: {output_path}")
