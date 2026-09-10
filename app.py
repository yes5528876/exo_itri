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
from calculations import compute_all, NIOSH_LIMIT, LEAN_BACK_DEG
from database import (save_records, load_records, export_summary, DB_PATH, COLUMN_LABELS,
                      DatabaseBusyError, DatabaseCorruptError)
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
        # records waiting to be written to Excel (kept while the file is locked)
        "pending_records": [],
        "db_error": "",
        "db_notice": "",
        "last_flush_try": 0.0,
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

# Editing imu_reader.py while the app runs reloads that module, but session_state
# still holds readers of the old class: stop them (and any test relying on them).
if (st.session_state.imu_manager is not None
        and not isinstance(st.session_state.imu_manager, DualIMUManager)):
    st.session_state.imu_manager.disconnect()
    st.session_state.imu_manager = None
    st.session_state.imu_use_real = False
    st.session_state.testing = False
    st.warning("IMU 程式已更新，測試已停止，請重新連線 IMU。")

IMU_NAMES = {"Trunk": "IMU1（軀幹）", "Pelvis": "IMU2（骨盆）"}


def _drop_history(imu) -> str:
    """Sidebar suffix summarising past link drops of a connected IMU."""
    if not imu.disconnect_count:
        return ""
    last = datetime.fromtimestamp(imu.last_disconnect_time).strftime("%H:%M:%S")
    return f"（曾斷線 {imu.disconnect_count} 次，最近 {last}）"

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
    addr1 = st.text_input("MAC 地址", value="DC:D2:5D:E8:79:BD", key="addr_imu1")
    addr_trunk = addr1 if sel1 == "(手動輸入)" else sel1.split()[-1]

    mgr: DualIMUManager | None = st.session_state.imu_manager
    imu1 = mgr.imu_trunk if mgr else None
    imu1_connected = imu1 and imu1.connected
    imu1_connecting = imu1 and imu1.connecting
    imu1_reconnecting = imu1 and imu1.reconnecting

    c1a, c1b = st.columns(2)
    with c1a:
        if st.button("🔗 連 IMU1", use_container_width=True, disabled=bool(imu1_connecting)):
            if mgr is None:
                mgr = DualIMUManager()
                st.session_state.imu_manager = mgr
                st.session_state.imu_use_real = True
            if mgr.imu_trunk:
                mgr.imu_trunk.stop()   # also ends an auto-reconnect loop
            from imu_reader import IMUReader
            mgr.imu_trunk = IMUReader(addr_trunk.strip(), label="Trunk")
            mgr.imu_trunk.start_async()
            st.session_state.imu_connecting = True
            st.rerun()
    with c1b:
        # stays enabled while reconnecting, so an endless retry can be stopped
        if st.button("✖ 斷 IMU1", use_container_width=True, disabled=imu1 is None):
            if mgr and mgr.imu_trunk:
                mgr.imu_trunk.stop()
                mgr.imu_trunk = None
            st.rerun()

    if imu1_connecting:
        st.caption("⏳ IMU1 連線中…")
    elif imu1_reconnecting:
        st.caption("🟠 IMU1 斷線，自動重連中…")
    elif imu1 and imu1.error_msg:
        st.caption(f"🔴 IMU1 錯誤: {imu1.error_msg[:60]}")
    elif imu1_connected:
        st.caption("🟢 IMU1 已連線" + _drop_history(imu1))
    else:
        st.caption("⚪ IMU1 未連線")

    st.markdown("")

    # ── IMU 2 (骨盆) ──
    st.markdown("**IMU 2 — 骨盆 (θ2)**")
    sel2 = st.selectbox("", device_options, key="sel_imu2", label_visibility="collapsed")
    addr2 = st.text_input("MAC 地址", value="EA:8A:1B:4A:C6:63", key="addr_imu2")
    addr_pelvis = addr2 if sel2 == "(手動輸入)" else sel2.split()[-1]

    imu2 = mgr.imu_pelvis if mgr else None
    imu2_connected = imu2 and imu2.connected
    imu2_connecting = imu2 and imu2.connecting
    imu2_reconnecting = imu2 and imu2.reconnecting

    c2a, c2b = st.columns(2)
    with c2a:
        if st.button("🔗 連 IMU2", use_container_width=True, disabled=bool(imu2_connecting)):
            if mgr is None:
                mgr = DualIMUManager()
                st.session_state.imu_manager = mgr
                st.session_state.imu_use_real = True
            if mgr.imu_pelvis:
                mgr.imu_pelvis.stop()   # also ends an auto-reconnect loop
            from imu_reader import IMUReader
            mgr.imu_pelvis = IMUReader(addr_pelvis.strip(), label="Pelvis")
            mgr.imu_pelvis.start_async()
            st.session_state.imu_connecting = True
            st.rerun()
    with c2b:
        if st.button("✖ 斷 IMU2", use_container_width=True, disabled=imu2 is None):
            if mgr and mgr.imu_pelvis:
                mgr.imu_pelvis.stop()
                mgr.imu_pelvis = None
            st.rerun()

    if imu2_connecting:
        st.caption("⏳ IMU2 連線中…")
    elif imu2_reconnecting:
        st.caption("🟠 IMU2 斷線，自動重連中…")
    elif imu2 and imu2.error_msg:
        st.caption(f"🔴 IMU2 錯誤: {imu2.error_msg[:60]}")
    elif imu2_connected:
        st.caption("🟢 IMU2 已連線" + _drop_history(imu2))
    else:
        st.caption("⚪ IMU2 未連線（θ2 = 0°）")

    # update global connecting flag
    # (re)connecting drives the 1 s refresh at the bottom of the page
    st.session_state.imu_connecting = bool(imu1_connecting or imu2_connecting
                                           or imu1_reconnecting or imu2_reconnecting)
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

# Signed angle (negative = leaning back): shown, recorded and fed to the formulas
# as is; below LEAN_BACK_DEG it is highlighted on screen and in Excel.
theta_measured = theta_raw - st.session_state.theta_offset
leaning_back = theta_measured < LEAN_BACK_DEG
metrics = compute_all(theta_measured, weight_kg, spring_k, condition_val, load_kg=patient_kg)

# ── Main layout ──────────────────────────────────────────────────────────────
st.markdown("# 🦴 外骨骼輔助人機介面")
imu_badge = "🟢 實體 IMU" if using_real_imu else "🟡 手動模擬"
st.markdown(f"**受測者:** {subject_info['subject_name']} | **任務:** {task_type} | **條件:** {condition_val.upper()} | **資料來源:** {imu_badge}")

# ── BLE link alerts ──────────────────────────────────────────────────────────
# Banners live in fixed st.empty() slots created on every run. While the page
# auto-refreshes, each run ends in st.rerun() and Streamlit never removes an
# element a later run didn't draw, so an outdated banner must be overwritten.
alert_slots = {"Trunk": st.empty(), "Pelvis": st.empty()}
imu_link_down = False   # an IMU that should be streaming isn't (pauses auto-save)
if mgr:
    alert_seen = st.session_state.setdefault("imu_alert_seen", {})
    for imu in (mgr.imu_trunk, mgr.imu_pelvis):
        if imu is None:
            continue
        name = IMU_NAMES.get(imu.label, imu.label)

        # pop-up once per new drop / recovery (event timestamps only move forward)
        seen = alert_seen.get(imu.label, 0.0)
        if imu.last_disconnect_time > seen:
            st.toast(f"{name} 藍牙斷線，正在自動重連…", icon="⚠️")
        if imu.last_reconnect_time > seen:
            st.toast(f"{name} 已重新連線", icon="✅")
        alert_seen[imu.label] = max(seen, imu.last_disconnect_time, imu.last_reconnect_time)

        if imu.reconnecting or (imu.connected and imu.stale):
            imu_link_down = True

        if imu.reconnecting:
            down_s = time.time() - imu.last_disconnect_time
            attempt = f"，第 {imu.reconnect_attempts} 次嘗試" if imu.reconnect_attempts else ""
            msg = (f"**{name} 藍牙斷線**，正在自動重連…（已斷線 {down_s:.0f} 秒{attempt}）"
                   f"　原因：{imu.last_disconnect_reason}")
            if st.session_state.testing:
                msg += "\n\n測試中的 3 秒自動儲存已暫停，重新連線後自動恢復。"
            if down_s > 30:
                msg += "\n\n若一直連不回來：確認 IMU 有電、在藍牙範圍內，或在側邊欄按「斷」再「連」。"
            alert_slots[imu.label].error(msg, icon="📡")
        elif imu.connected and time.time() - imu.last_reconnect_time < 5:
            alert_slots[imu.label].success(f"{name} 已重新連線，資料恢復更新。", icon="✅")

# ── Excel writes ─────────────────────────────────────────────────────────────
# Records are queued, then written. If the workbook can't be written (e.g. it's
# open in Excel) they stay queued and are retried, so nothing is lost and a file
# problem never stops the running test.
db_pending_slot = st.empty()   # fixed slots like alert_slots, filled in after
db_notice_slot = st.empty()    # this run's writes


def _flush_pending() -> list[str]:
    """Try to write all queued records; returns their ids ([] if nothing written)."""
    pending = st.session_state.pending_records
    if not pending:
        return []
    st.session_state.last_flush_try = time.time()
    try:
        ids, backup = save_records(pending)
    except DatabaseBusyError as e:
        st.session_state.db_error = str(e)
        return []
    except Exception as e:   # any other file problem: keep the records, show why
        st.session_state.db_error = f"{type(e).__name__}: {e}"
        return []
    pending.clear()
    st.session_state.db_error = ""
    if backup:
        st.session_state.db_notice = (
            f"原本的 {os.path.basename(DB_PATH)} 已損毀無法讀取，已改名保存為 {backup}，"
            "並建立新檔繼續記錄。")
    return ids


def _record_now(m: dict) -> list[str]:
    """Queue one record stamped with the measurement time, then try to write it."""
    rec = dict(m, timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    st.session_state.pending_records.append((subject_info, rec))
    return _flush_pending()

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
        ids = _record_now(metrics)
        if ids:
            st.success(f"已儲存 — 紀錄編號: {ids[-1]}")
        else:
            st.toast("Excel 暫時無法寫入，這筆紀錄已暫存，會自動重試。", icon="💾")

with col_b5:
    if st.button("📊 匯出報表"):
        _flush_pending()   # include any queued records in the summary
        try:
            path = export_summary()
            st.success(f"報表已匯出: `{path}`")
        except Exception as e:
            st.warning(f"報表匯出失敗：{e}")

st.divider()

# ── Live update logic ─────────────────────────────────────────────────────────
if st.session_state.testing:
    now = time.time()

    # Always update last_metrics while testing
    st.session_state.last_metrics = metrics.copy()

    # Update session stats
    f_c_current = metrics["F_c_exo"] if condition_val == "exo" else metrics["F_c_bare"]
    if f_c_current > st.session_state.max_fc:
        st.session_state.max_fc = f_c_current

    # Auto-save every 3 seconds; paused while an IMU link is down so a dropped
    # IMU's frozen angle is not recorded as real data
    if now - st.session_state.last_auto_save >= 3.0 and not imu_link_down:
        _record_now(st.session_state.last_metrics)
        st.session_state.last_auto_save = now
        st.session_state.high_risk_count += 1

# Retry queued records every 3 s (also covers a failed manual save outside a test)
if (st.session_state.pending_records
        and time.time() - st.session_state.last_flush_try >= 3.0):
    _flush_pending()

if st.session_state.pending_records:
    db_pending_slot.warning(f"💾 有 {len(st.session_state.pending_records)} 筆紀錄還沒寫進 Excel："
                            f"{st.session_state.db_error}。紀錄已暫存、會自動重試，請先不要關閉程式。")
if st.session_state.db_notice:
    db_notice_slot.warning(st.session_state.db_notice)

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

    def _dot(imu, idle):
        if imu is not None and imu.reconnecting:
            return "🟠"
        return "🟢" if imu is not None and imu.connected else idle

    ci4.markdown(f"""
    <div class="metric-card" style="padding-top:28px;">
      <div class="metric-value" style="color:#555;font-size:20px;">{_dot(imu1, '🔴')} IMU1<br>{_dot(imu2, '⚪')} IMU2</div>
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

# "+ 0.0" turns a rounded -0.0 into 0.0
_card(c1, "軀幹前傾角", f"{round(theta_measured, 1) + 0.0:.1f}",
      "°　後仰" if leaning_back else "°",
      "#ff9f43" if leaning_back else "#4fc3f7")
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
li_pct = max(0.0, min(li / 1.5 * 100, 100))   # LI goes negative when leaning back far

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
if st.session_state.testing and imu_link_down:
    st.warning("⏸ 測試進行中 — IMU 斷線，自動儲存暫停中，重新連線後恢復")
elif st.session_state.testing:
    elapsed_since_save = time.time() - st.session_state.last_auto_save
    next_save = max(0, 3.0 - elapsed_since_save)
    st.info(f"⏱ 測試進行中 — 下次自動儲存: {next_save:.1f} 秒")

# ── Records table ─────────────────────────────────────────────────────────────
st.divider()
st.markdown('<div class="section-title">📋 歷史紀錄</div>', unsafe_allow_html=True)

hist_slot, hist_caption_slot = st.empty(), st.empty()   # fixed slots (see alert_slots)
try:
    records = load_records()
except DatabaseCorruptError as e:
    records = None
    hist_slot.warning(f"歷史紀錄無法讀取：{e}。下次儲存時會自動把舊檔改名備份並建立新檔。")
except Exception as e:   # locked or being saved by another program: skip this refresh
    records = None
    hist_slot.warning(f"歷史紀錄暫時無法讀取：{e}")
if records:
    df = pd.DataFrame(records)
    # Colour risk column
    def style_risk(val):
        colors = {"high": "background-color:#ff4444;color:white",
                  "warning": "background-color:#ffd966",
                  "normal": "background-color:#70ad47;color:white"}
        return colors.get(val, "")

    def style_lean(val):
        try:
            leaning = float(val) < LEAN_BACK_DEG
        except (TypeError, ValueError):    # blank or non-numeric cell
            leaning = False
        return "background-color:#BDD7EE;color:#1F3864" if leaning else ""

    risk_col = "風險等級" if "風險等級" in df.columns else "risk_flag"
    lean_col = COLUMN_LABELS["theta_deg"]
    styler = df.style
    if risk_col in df.columns:
        styler = styler.map(style_risk, subset=[risk_col])
    if lean_col in df.columns:
        styler = styler.map(style_lean, subset=[lean_col])
    hist_slot.dataframe(styler, use_container_width=True, height=300)
    hist_caption_slot.caption(f"共 {len(df)} 筆紀錄 | 資料庫: {DB_PATH}")
elif records is not None:
    hist_slot.info("尚無歷史紀錄")

# ── Auto-refresh while testing, connecting, or IMU live ───────────────────────
if st.session_state.testing:
    time.sleep(0.5)
    st.rerun()
elif st.session_state.imu_connecting:
    time.sleep(1.0)
    st.rerun()
elif st.session_state.imu_use_real and mgr and mgr.any_active:
    # keep polling even when data stalls, so a dropped link shows up on screen
    time.sleep(0.3)
    st.rerun()
elif st.session_state.pending_records:
    # keep retrying queued Excel writes even when nothing else refreshes the page
    time.sleep(1.0)
    st.rerun()
