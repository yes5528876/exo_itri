"""
WIT WT901BLE IMU reader — BLE version using bleak.

WIT BLE GATT UUIDs:
  Service:  0000ffe5-0000-1000-8000-00805f9a34fb
  Notify:   0000ffe4-0000-1000-8000-00805f9a34fb  (sensor data in)
  Write:    0000ffe9-0000-1000-8000-00805f9a34fb  (commands out)

BLE Packet format (20 bytes, no checksum):
  Byte 0:    0x55 header
  Byte 1:    0x61 type (combined BLE packet)
  Bytes 2-7: Ax, Ay, Az (int16 little-endian, /32768*16 => g)
  Bytes 8-13: Wx, Wy, Wz (int16 little-endian, /32768*2000 => deg/s)
  Bytes 14-19: Roll, Pitch, Yaw (int16 little-endian, /32768*180 => deg)

Also handles legacy serial 11-byte packets (0x51/0x52/0x53) in case
firmware is updated or USB is used later.
"""

import asyncio
import threading
import struct
import time
import logging

try:
    from bleak import BleakClient, BleakScanner
    BLEAK_AVAILABLE = True
except ImportError:
    BLEAK_AVAILABLE = False

logger = logging.getLogger(__name__)

# WIT BLE GATT UUIDs
UUID_NOTIFY = "0000ffe4-0000-1000-8000-00805f9a34fb"
UUID_WRITE  = "0000ffe9-0000-1000-8000-00805f9a34fb"

# BLE combined packet (20 bytes)
BLE_HEADER   = 0x55
BLE_PKT_TYPE = 0x61
BLE_PKT_LEN  = 20

# Legacy serial packet types (11 bytes each)
PKT_ANGLE = 0x53
PKT_ACC   = 0x51
PKT_GYRO  = 0x52
SERIAL_PKT_LEN = 11


def _s16(lo: int, hi: int) -> int:
    return struct.unpack('h', bytes([lo, hi]))[0]


class IMUReader:
    """Single BLE IMU reader. Call start() to connect, stop() to disconnect."""

    def __init__(self, address: str, label: str = "IMU"):
        self.address = address
        self.label   = label

        self.roll  = 0.0
        self.pitch = 0.0   # trunk flexion angle (deg)
        self.yaw   = 0.0
        self.ax = self.ay = self.az = 0.0
        self.wx = self.wy = self.wz = 0.0

        self.connected   = False
        self.connecting  = False
        self.error_msg   = ""
        self.last_update = 0.0

        self._buf = bytearray()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Public API ────────────────────────────────────────────────────────────
    def start_async(self):
        """Non-blocking: start BLE thread immediately and return.
        Poll .connected / .error_msg / .connecting to check status."""
        if not BLEAK_AVAILABLE:
            self.error_msg = "bleak not installed"
            return
        self._stop_event.clear()
        self.connected  = False
        self.connecting = True
        self.error_msg  = ""
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()

    def start(self) -> bool:
        """Blocking version (for non-Streamlit use). Waits up to 10s."""
        self.start_async()
        for _ in range(100):
            time.sleep(0.1)
            if self.connected or self.error_msg:
                break
        return self.connected

    def stop(self):
        self._stop_event.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self.connected = False

    @property
    def stale(self) -> bool:
        return (time.time() - self.last_update) > 2.0

    # ── Thread + async loop ───────────────────────────────────────────────────
    def _thread_main(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._ble_main())
        except Exception as e:
            import traceback
            self.error_msg = f"{e}\n{traceback.format_exc()}"
            self.connected = False
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _ble_main(self):
        try:
            async with BleakClient(self.address, timeout=10.0) as client:
                self.connected  = True
                self.connecting = False
                self.error_msg  = ""
                logger.info(f"{self.label}: connected to {self.address}")

                await client.start_notify(UUID_NOTIFY, self._on_data)

                while not self._stop_event.is_set():
                    await asyncio.sleep(0.05)

                await client.stop_notify(UUID_NOTIFY)

        except Exception as e:
            import traceback
            self.error_msg = f"{e}\n{traceback.format_exc()}"
            self.connected = False
            self.connecting = False

    def _on_data(self, sender, data: bytearray):
        with self._lock:
            self._buf.extend(data)
            self._drain_buf()

    def _drain_buf(self):
        while len(self._buf) >= 2:
            if self._buf[0] != BLE_HEADER:
                self._buf.pop(0)
                continue

            pkt_type = self._buf[1]

            if pkt_type == BLE_PKT_TYPE:
                # 20-byte BLE combined packet
                if len(self._buf) < BLE_PKT_LEN:
                    break
                pkt = self._buf[:BLE_PKT_LEN]
                self._buf = self._buf[BLE_PKT_LEN:]
                self._parse_ble(pkt)

            elif pkt_type in (PKT_ANGLE, PKT_ACC, PKT_GYRO):
                # 11-byte legacy serial packet
                if len(self._buf) < SERIAL_PKT_LEN:
                    break
                pkt = self._buf[:SERIAL_PKT_LEN]
                # validate checksum
                if (sum(pkt[:10]) & 0xFF) == pkt[10]:
                    self._parse_serial(pkt)
                self._buf = self._buf[SERIAL_PKT_LEN:]

            else:
                # unknown type — skip this header byte
                self._buf.pop(0)

    def _parse_ble(self, pkt: bytearray):
        """Parse 20-byte BLE combined packet (type 0x61)."""
        self.ax = _s16(pkt[2],  pkt[3])  / 32768.0 * 16.0
        self.ay = _s16(pkt[4],  pkt[5])  / 32768.0 * 16.0
        self.az = _s16(pkt[6],  pkt[7])  / 32768.0 * 16.0
        self.wx = _s16(pkt[8],  pkt[9])  / 32768.0 * 2000.0
        self.wy = _s16(pkt[10], pkt[11]) / 32768.0 * 2000.0
        self.wz = _s16(pkt[12], pkt[13]) / 32768.0 * 2000.0
        self.pitch = _s16(pkt[14], pkt[15]) / 32768.0 * 180.0
        self.roll  = _s16(pkt[16], pkt[17]) / 32768.0 * 180.0
        self.yaw   = _s16(pkt[18], pkt[19]) / 32768.0 * 180.0
        self.last_update = time.time()

    def _parse_serial(self, pkt: bytearray):
        """Parse 11-byte legacy serial packet."""
        ptype = pkt[1]
        if ptype == PKT_ANGLE:
            self.roll  = _s16(pkt[2], pkt[3]) / 32768.0 * 180.0
            self.pitch = _s16(pkt[4], pkt[5]) / 32768.0 * 180.0
            self.yaw   = _s16(pkt[6], pkt[7]) / 32768.0 * 180.0
            self.last_update = time.time()
        elif ptype == PKT_ACC:
            self.ax = _s16(pkt[2], pkt[3]) / 32768.0 * 16.0
            self.ay = _s16(pkt[4], pkt[5]) / 32768.0 * 16.0
            self.az = _s16(pkt[6], pkt[7]) / 32768.0 * 16.0


# ── Dual-IMU manager ─────────────────────────────────────────────────────────
class DualIMUManager:
    """Manages up to two WT901BLE IMUs: trunk (θ1) and pelvis (θ2)."""

    def __init__(self):
        self.imu_trunk:  IMUReader | None = None
        self.imu_pelvis: IMUReader | None = None

    def connect_async(self, addr_trunk: str, addr_pelvis: str | None = None):
        """Non-blocking: start BLE threads immediately."""
        self.imu_trunk = IMUReader(addr_trunk, label="Trunk")
        self.imu_trunk.start_async()
        if addr_pelvis and addr_pelvis.strip() and addr_pelvis != addr_trunk:
            self.imu_pelvis = IMUReader(addr_pelvis, label="Pelvis")
            self.imu_pelvis.start_async()

    def connect(self, addr_trunk: str, addr_pelvis: str | None = None) -> dict:
        self.imu_trunk = IMUReader(addr_trunk, label="Trunk")
        ok1 = self.imu_trunk.start()
        if not ok1:
            return {"ok": False, "msg": f"Trunk IMU ({addr_trunk}): {self.imu_trunk.error_msg}"}

        if addr_pelvis and addr_pelvis.strip() and addr_pelvis != addr_trunk:
            self.imu_pelvis = IMUReader(addr_pelvis, label="Pelvis")
            ok2 = self.imu_pelvis.start()
            if not ok2:
                return {"ok": False, "msg": f"Pelvis IMU ({addr_pelvis}): {self.imu_pelvis.error_msg}"}

        return {"ok": True, "msg": "Connected"}

    @property
    def is_connecting(self) -> bool:
        t = self.imu_trunk and self.imu_trunk.connecting
        p = self.imu_pelvis and self.imu_pelvis.connecting
        return bool(t or p)

    @property
    def has_error(self) -> str:
        if self.imu_trunk and self.imu_trunk.error_msg:
            return self.imu_trunk.error_msg
        if self.imu_pelvis and self.imu_pelvis.error_msg:
            return self.imu_pelvis.error_msg
        return ""

    def disconnect(self):
        if self.imu_trunk:
            self.imu_trunk.stop()
        if self.imu_pelvis:
            self.imu_pelvis.stop()
        self.imu_trunk  = None
        self.imu_pelvis = None

    def get_angles(self) -> tuple[float, float]:
        theta1 = self.imu_trunk.pitch  if self.imu_trunk  else 0.0
        theta2 = self.imu_pelvis.pitch if self.imu_pelvis else 0.0
        return theta1, theta2

    @property
    def trunk_ok(self) -> bool:
        return bool(self.imu_trunk and self.imu_trunk.connected and not self.imu_trunk.stale)

    @property
    def pelvis_ok(self) -> bool:
        return bool(self.imu_pelvis and self.imu_pelvis.connected and not self.imu_pelvis.stale)


# ── BLE scanner helper (called from app.py) ───────────────────────────────────
def scan_ble_devices(timeout: float = 5.0) -> list[dict]:
    """Synchronous wrapper. Returns [{'name':..., 'address':...}, ...]"""
    if not BLEAK_AVAILABLE:
        return []

    async def _scan():
        devices = await BleakScanner.discover(timeout=timeout)
        return [{"name": d.name or "Unknown", "address": d.address} for d in devices]

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_scan())
    finally:
        loop.close()
