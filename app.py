"""
外骨骼輔助人機介面 (IMU Exoskeleton Assessment Web UI)
Run: streamlit run app.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import time
import math
import streamlit as st
import pandas as pd
from datetime import datetime
from calculations import compute_all, NIOSH_LIMIT
from database import save_record, load_records, export_summary, DB_PATH
from imu_reader import DualIMUManager

def scan_ble_devices(timeout: float = 5.0):
    import asyncio
    try:
        from bleak import BleakScanner
    except ImportError:
        return []
    async def _scan():
        devices = await BleakScanner.discover(timeout=timeout)
        return [{"name": d.name or "Unknown", "address": d.address} for d in devices]
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_scan())
    finally:
        loop.close()

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="外骨骼輔助人機介面",
    page_icon="🦴",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Styles ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.metric-card {
    background: #1e2736;
    border-radius: 10px;
    padding: 14px 18px;
    text-align: center;
    margin-bottom: 8px;
}
.metric-label { color: #a0b0c8; font-size: 13px; margin-bottom: 4px; }
.metric-value { font-size: 26px; font-weight: bold; color: #e8f0fe; }
.metric-unit  { color: #7090b0; font-size: 12px; }
.risk-normal  { color: #70ad47; font-weight: bold; }
.risk-warning { color: #ffd966; font-weight: bold; }
.risk-high    { color: #ff4444; font-weight: bold; }
.section-title { font-size: 18px; font-weight: bold; color: #2e75b6;
                  border-bottom: 2px solid #2e75b6; padding-bottom: 4px; margin-bottom: 12px; }
.stButton > button { width: 100%; border-radius: 8px; font-size: 15px; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# ── Session state init ────────────────────────────────────────────────────────
def _init_state():
    defaults = {
        "calibrated": False,
        "testing": False,
        "theta_offset": 0.0,
        "high_risk_count": 0,
        "action_start": None,
        "action_total": 0.0,
        "max_fc": 0.0,
        "last_metrics": None,
        "last_auto_save": 0.0,
        # IMU
        "imu_manager": None,
        "imu_use_real": False,
        "imu_connecting": False,
        "angle_axis": "Pitch",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_state()

# ── Sidebar: Subject info ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧑 受測者資料")
    subject_name = st.text_input("姓名", value="")
    gender = st.radio("性別", ["男", "女"], horizontal=True)
    age = st.number_input("年齡", 10, 100, 30)
    height_cm = st.number_input("身高 (cm)", 100.0, 220.0, 170.0, step=0.5)
    weight_kg = st.number_input("體重 (kg)", 30.0, 150.0, 65.0, step=0.5)
    patient_kg = st.number_input("老人重量 (kg)", 0.0, 150.0, 60.0, step=0.5,
                                  help="搬運/移床的老人體重，計入腰椎負載：W_upper = 體重×0.6 + 老人重量")
    spring_k = st.number_input("彈簧係數 k (Nm/deg)", 0.0, 5.0, 0.5, step=0.05,
                                help="被動式彈簧外骨骼: M_exo = k × θ")
    task_type = st.selectbox("任務類型", ["擺位", "移床"])
    condition = st.radio("條件", ["bare (未穿)", "exo (穿戴)"], horizontal=True)
    condition_val = "bare" if condition.startswith("bare") else "exo"

    st.divider()
    st.markdown("## 📡 BLE IMU 連線設定")

    if st.button("🔍 掃描 BLE 裝置", use_container_width=True):
        with st.spinner("掃描中 (5秒)..."):
            found = scan_ble_devices(timeout=5.0)
            st.session_state["ble_scan_results"] = found

    scan_results = st.session_state.get("ble_scan_results", [])
    device_options = ["(手動輸入)"] + [f"{d['name']}  {d['address']}" for d in scan_results]

    # ── IMU 1 (軀幹) ──
    st.markdown("**IMU 1 — 軀幹 (θ1)**")
    sel1 = st.selectbox("", device_options, key="sel_imu1", label_visibility="collapsed")
    addr1 = st.text_input("MAC 地址", value="EA:8A:1B:4A:C6:63", key="addr_imu1")
    addr_trunk = addr1 if sel1 == "(手動輸入)" else sel1.split()[-1]

    mgr: DualIMUManager | None = st.session_state.imu_manager
    imu1 = mgr.imu_trunk if mgr else None
    imu1_connected = imu1 and imu1.connected
    imu1_connecting = imu1 and imu1.connecting

    c1a, c1b = st.columns(2)
    with c1a:
        if st.button("🔗 連 IMU1", use_container_width=True, disabled=bool(imu1_connecting)):
            if mgr is None:
                mgr = DualIMUManager()
                st.session_state.imu_manager = mgr
                st.session_state.imu_use_real = True
            if imu1_connected:
                mgr.imu_trunk.stop()
            from imu_reader import IMUReader
            mgr.imu_trunk = IMUReader(addr_trunk.strip(), label="Trunk")
            mgr.imu_trunk.start_async()
            st.session_state.imu_connecting = True
            st.rerun()
    with c1b:
        if st.button("✖ 斷 IMU1", use_container_width=True, disabled=not imu1_connected):
            if mgr and mgr.imu_trunk:
                mgr.imu_trunk.stop()
                mgr.imu_trunk = None
            st.rerun()

    if imu1_connecting:
        st.caption("⏳ IMU1 連線中…")
    elif imu1 and imu1.error_msg:
        st.caption(f"🔴 IMU1 錯誤: {imu1.error_msg[:60]}")
    elif imu1_connected:
        st.caption("🟢 IMU1 已連線")
    else:
        st.caption("⚪ IMU1 未連線")

    st.markdown("")

    # ── IMU 2 (骨盆) ──
    st.markdown("**IMU 2 — 骨盆 (θ2)**")
    sel2 = st.selectbox("", device_options, key="sel_imu2", label_visibility="collapsed")
    addr2 = st.text_input("MAC 地址", value="DC:D2:5D:E8:79:BD", key="addr_imu2")
    addr_pelvis = addr2 if sel2 == "(手動輸入)" else sel2.split()[-1]

    imu2 = mgr.imu_pelvis if mgr else None
    imu2_connected = imu2 and imu2.connected
    imu2_connecting = imu2 and imu2.connecting

    c2a, c2b = st.columns(2)
    with c2a:
        if st.button("🔗 連 IMU2", use_container_width=True, disabled=bool(imu2_connecting)):
            if mgr is None:
                mgr = DualIMUManager()
                st.session_state.imu_manager = mgr
                st.session_state.imu_use_real = True
            if imu2_connected:
                mgr.imu_pelvis.stop()
            from imu_reader import IMUReader
            mgr.imu_pelvis = IMUReader(addr_pelvis.strip(), label="Pelvis")
            mgr.imu_pelvis.start_async()
            st.session_state.imu_connecting = True
            st.rerun()
    with c2b:
        if st.button("✖ 斷 IMU2", use_container_width=True, disabled=not imu2_connected):
            if mgr and mgr.imu_pelvis:
                mgr.imu_pelvis.stop()
                mgr.imu_pelvis = None
            st.rerun()

    if imu2_connecting:
        st.caption("⏳ IMU2 連線中…")
    elif imu2 and imu2.error_msg:
        st.caption(f"🔴 IMU2 錯誤: {imu2.error_msg[:60]}")
    elif imu2_connected:
        st.caption("🟢 IMU2 已連線")
    else:
        st.caption("⚪ IMU2 未連線（θ2 = 0°）")

    # update global connecting flag
    st.session_state.imu_connecting = bool(imu1_connecting or imu2_connecting)
    if mgr and (imu1_connected or imu2_connected):
        st.session_state.imu_use_real = True

    angle_axis = st.selectbox("軀幹角度軸", ["Pitch", "Roll", "Yaw"], index=0,
                               help="選擇哪個軸代表軀幹前傾角")
    st.session_state["angle_axis"] = angle_axis

    st.divider()
    st.markdown("## ⚙️ 手動模擬輸入")
    st.caption("（IMU 未連線時使用）")
    theta1_sim = st.slider("θ1 軀幹 (°)", 0.0, 90.0, 30.0, step=0.5)
    theta2_sim = st.slider("θ2 骨盆 (°)", 0.0, 45.0, 5.0, step=0.5)

    st.divider()
    st.caption(f"資料庫: `{DB_PATH}`")

subject_info = {
    "subject_name": subject_name or "未命名",
    "gender": gender,
    "age": age,
    "height_cm": height_cm,
    "weight_kg": weight_kg,
    "patient_kg": patient_kg,
    "spring_k": spring_k,
    "task_type": task_type,
    "condition": condition_val,
}

# ── Compute current angle & metrics ─────────────────────────────────────────
mgr: DualIMUManager | None = st.session_state.imu_manager
if st.session_state.imu_use_real and mgr and (mgr.trunk_ok or mgr.imu_trunk):
    axis = st.session_state.get("angle_axis", "Pitch")
    imu_t = mgr.imu_trunk
    imu_p = mgr.imu_pelvis
    def _get_axis(imu, ax):
        if imu is None: return 0.0
        return {"Roll": imu.roll, "Pitch": imu.pitch, "Yaw": imu.yaw}.get(ax, imu.pitch)
    theta1_real = _get_axis(imu_t, axis)
    theta2_real = _get_axis(imu_p, axis)
    theta_raw = theta1_real - theta2_real
    using_real_imu = True
else:
    theta_raw = theta1_sim - theta2_sim
    using_real_imu = False

theta_calibrated = max(0.0, theta_raw - st.session_state.theta_offset)
metrics = compute_all(theta_calibrated, weight_kg, spring_k, condition_val, load_kg=patient_kg)

# ── Main layout ──────────────────────────────────────────────────────────────
st.markdown("# 🦴 外骨骼輔助人機介面")
imu_badge = "🟢 實體 IMU" if using_real_imu else "🟡 手動模擬"
st.markdown(f"**受測者:** {subject_info['subject_name']} | **任務:** {task_type} | **條件:** {condition_val.upper()} | **資料來源:** {imu_badge}")

# ── Control buttons ──────────────────────────────────────────────────────────
col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)

with col_b1:
    if st.button("📐 IMU 校正", help="請受測者站直後按下，設定當前姿態為 0°"):
        st.session_state.theta_offset = theta_raw
        st.session_state.calibrated = True
        st.session_state.high_risk_count = 0
        st.session_state.action_total = 0.0
        st.session_state.max_fc = 0.0
        st.session_state.over20_start = None
        st.success("已校正 — 當前姿態設為 0°")

with col_b2:
    if st.button("▶ 開始測試", disabled=st.session_state.testing):
        if not st.session_state.calibrated:
            st.warning("請先進行 IMU 校正")
        else:
            st.session_state.testing = True
            st.session_state.action_start = time.time()
            st.session_state.last_auto_save = time.time()
            st.success("測試進行中…")

with col_b3:
    if st.button("⏹ 停止測試", disabled=not st.session_state.testing):
        st.session_state.testing = False
        if st.session_state.action_start:
            st.session_state.action_total += time.time() - st.session_state.action_start
            st.session_state.action_start = None
        st.info("測試已停止")

with col_b4:
    if st.button("💾 儲存紀錄"):
        m = metrics.copy()
        m["theta_deg"] = round(theta_calibrated, 2)
        rid = save_record(subject_info, m)
        st.success(f"已儲存 — 紀錄編號: {rid}")

with col_b5:
    if st.button("📊 匯出報表"):
        path = export_summary()
        st.success(f"報表已匯出: `{path}`")

st.divider()

# ── Live update logic ─────────────────────────────────────────────────────────
if st.session_state.testing:
    now = time.time()

    # Always update last_metrics while testing
    st.session_state.last_metrics = metrics.copy()
    st.session_state.last_metrics["theta_deg"] = round(theta_calibrated, 2)

    # Update session stats
    f_c_current = metrics["F_c_exo"] if condition_val == "exo" else metrics["F_c_bare"]
    if f_c_current > st.session_state.max_fc:
        st.session_state.max_fc = f_c_current

    # Auto-save every 3 seconds
    if now - st.session_state.last_auto_save >= 3.0:
        save_record(subject_info, st.session_state.last_metrics)
        st.session_state.last_auto_save = now
        st.session_state.high_risk_count += 1

# ── Live IMU Angle Display ───────────────────────────────────────────────────
if st.session_state.imu_use_real and mgr:
    st.markdown('<div class="section-title">📡 IMU 即時角度</div>', unsafe_allow_html=True)
    imu1 = mgr.imu_trunk
    imu2 = mgr.imu_pelvis

    ci1, ci2, ci3, ci4, ci5, ci6, ci7 = st.columns(7)

    def _imu_card(col, label, value, ok):
        color = "#4fc3f7" if ok else "#666"
        col.markdown(f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value" style="color:{color};">{value}</div>
        </div>""", unsafe_allow_html=True)

    ok1 = imu1 and imu1.connected
    ok2 = imu2 and imu2.connected

    _imu_card(ci1, "IMU1 Roll",  f"{imu1.roll:.1f}°"  if ok1 else "—", ok1)
    _imu_card(ci2, "IMU1 Pitch", f"{imu1.pitch:.1f}°" if ok1 else "—", ok1)
    _imu_card(ci3, "IMU1 Yaw",   f"{imu1.yaw:.1f}°"   if ok1 else "—", ok1)

    ci4.markdown(f"""
    <div class="metric-card" style="padding-top:28px;">
      <div class="metric-value" style="color:#555;font-size:20px;">{'🟢' if ok1 else '🔴'} IMU1<br>{'🟢' if ok2 else '⚪'} IMU2</div>
    </div>""", unsafe_allow_html=True)

    _imu_card(ci5, "IMU2 Roll",  f"{imu2.roll:.1f}°"  if ok2 else "—", ok2)
    _imu_card(ci6, "IMU2 Pitch", f"{imu2.pitch:.1f}°" if ok2 else "—", ok2)
    _imu_card(ci7, "IMU2 Yaw",   f"{imu2.yaw:.1f}°"   if ok2 else "—", ok2)

    st.divider()

# ── Metrics display ──────────────────────────────────────────────────────────
risk = metrics["risk_flag"]
risk_color = {"normal": "#70ad47", "warning": "#ffd966", "high": "#ff4444"}.get(risk, "#aaa")
risk_label = {"normal": "低風險 ✔", "warning": "中風險 ⚠", "high": "高風險 ✖"}.get(risk, risk)

# Row 1: Angle + compression forces
st.markdown('<div class="section-title">📡 即時量測數值</div>', unsafe_allow_html=True)
c1, c2, c3, c4, c5 = st.columns(5)

def _card(col, label, value, unit, color="#e8f0fe"):
    col.markdown(f"""
    <div class="metric-card">
      <div class="metric-label">{label}</div>
      <div class="metric-value" style="color:{color};">{value}</div>
      <div class="metric-unit">{unit}</div>
    </div>""", unsafe_allow_html=True)

_card(c1, "軀幹前傾角", f"{theta_calibrated:.1f}", "°", "#4fc3f7")
_card(c2, "未穿戴腰椎壓迫力 F_c_bare", f"{metrics['F_c_bare']:.0f}", "N")
_card(c3, "穿戴腰椎壓迫力 F_c_exo", f"{metrics['F_c_exo']:.0f}", "N", "#80cbc4")
_card(c4, "外骨骼有效率", f"{metrics['reduction_percent']:.1f}", "%", "#a5d6a7")
_card(c5, "負載指數 LI", f"{metrics['load_index']:.3f}", f"/ 3400N", risk_color)

# Row 2: Moments
st.markdown('<div class="section-title">⚙️ 力矩計算</div>', unsafe_allow_html=True)
c6, c7, c8, c9, _ = st.columns(5)
_card(c6, "腰椎力矩 M_lumbar", f"{metrics['M_lumbar']:.1f}", "N·m")
_card(c7, "外骨骼力矩 M_exo", f"{metrics['M_exo']:.1f}", "N·m", "#ffb74d")
_card(c8, "背肌剩餘力矩 M_mus_exo", f"{metrics['M_mus_exo']:.1f}", "N·m", "#ce93d8")
_card(c9, "風險等級", risk_label, "", risk_color)

# Row 3: Session stats
st.markdown('<div class="section-title">📊 本次測試統計</div>', unsafe_allow_html=True)
c10, c11, c12, c13, _ = st.columns(5)

action_time = st.session_state.action_total
if st.session_state.testing and st.session_state.action_start:
    action_time += time.time() - st.session_state.action_start

_card(c10, "已自動儲存次數", str(st.session_state.high_risk_count), "次", "#ff8a65")
_card(c11, "動作總時間", f"{action_time:.1f}", "s")
_card(c12, "腰椎最大壓迫力", f"{st.session_state.max_fc:.0f}", "N",
      "#ff4444" if st.session_state.max_fc > NIOSH_LIMIT else "#e8f0fe")
_card(c13, "校正狀態", "已校正 ✔" if st.session_state.calibrated else "未校正", "",
      "#70ad47" if st.session_state.calibrated else "#ff8a65")

# ── NIOSH gauge ───────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-title">📈 負載指數儀表板</div>', unsafe_allow_html=True)
li = metrics["load_index"]
li_pct = min(li / 1.5 * 100, 100)

st.markdown(f"""
<div style="background:#1e2736;border-radius:12px;padding:16px;">
  <div style="display:flex;justify-content:space-between;font-size:13px;color:#a0b0c8;margin-bottom:6px;">
    <span>低風險 (&lt;0.75)</span><span>中等 (0.75–1.0)</span><span>高風險 (&gt;1.0)</span>
  </div>
  <div style="background:#333;border-radius:6px;height:24px;position:relative;">
    <div style="width:{li_pct:.1f}%;background:{risk_color};height:100%;border-radius:6px;transition:width 0.3s;"></div>
    <div style="position:absolute;top:2px;left:{min(li_pct,97):.1f}%;color:#fff;font-size:13px;font-weight:bold;">
      &nbsp;{li:.3f}
    </div>
  </div>
  <div style="display:flex;justify-content:space-between;font-size:11px;color:#557;margin-top:4px;">
    <span>0</span><span style="margin-left:50%">0.75</span><span>1.0</span><span>1.5+</span>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Testing status hint ──────────────────────────────────────────────────────
if st.session_state.testing:
    elapsed_since_save = time.time() - st.session_state.last_auto_save
    next_save = max(0, 3.0 - elapsed_since_save)
    st.info(f"⏱ 測試進行中 — 下次自動儲存: {next_save:.1f} 秒")

# ── Records table ─────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-title">📋 歷史紀錄</div>', unsafe_allow_html=True)

records = load_records()
if records:
    df = pd.DataFrame(records)
    # Colour risk column
    def style_risk(val):
        colors = {"high": "background-color:#ff4444;color:white",
                  "warning": "background-color:#ffd966",
                  "normal": "background-color:#70ad47;color:white"}
        return colors.get(val, "")

    risk_col = "風險等級" if "風險等級" in df.columns else "risk_flag"
    st.dataframe(
        df.style.map(style_risk, subset=[risk_col]) if risk_col in df.columns else df,
        use_container_width=True,
        height=300,
    )
    st.caption(f"共 {len(df)} 筆紀錄 | 資料庫: {DB_PATH}")
else:
    st.info("尚無歷史紀錄")

# ── Auto-refresh while testing, connecting, or IMU live ───────────────────────
if st.session_state.testing:
    time.sleep(0.5)
    st.rerun()
elif st.session_state.imu_connecting:
    time.sleep(1.0)
    st.rerun()
elif st.session_state.imu_use_real and mgr and (mgr.trunk_ok or mgr.pelvis_ok):
    time.sleep(0.3)
    st.rerun()
