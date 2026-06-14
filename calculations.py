import math

# Anatomical constants
R_MUSCLE = 0.05       # m, erector spinae moment arm to spine center
D_COM = 0.30          # m, upper body COM to L5-S1 (typical: 0.25–0.35)
UPPER_BODY_RATIO = 0.6
G = 9.81              # m/s²
NIOSH_LIMIT = 3400    # N


def upper_body_weight(weight_kg: float) -> float:
    return UPPER_BODY_RATIO * weight_kg


def lumbar_moment(theta_deg: float, weight_kg: float, load_kg: float = 0.0) -> float:
    """M_lumbar = (W_upper + W_load) * g * d * sin(theta)"""
    theta_rad = math.radians(theta_deg)
    w_upper = upper_body_weight(weight_kg) + load_kg
    return w_upper * G * D_COM * math.sin(theta_rad)


def exo_moment(spring_k: float, theta_deg: float) -> float:
    """Passive spring exoskeleton: M_exo = k * theta (Nm/deg * deg)"""
    # return spring_k * theta_deg
    return spring_k * theta_deg


def muscle_force_bare(m_lumbar: float) -> float:
    return m_lumbar / R_MUSCLE


def muscle_force_exo(m_lumbar: float, m_exo: float) -> float:
    m_mus = max(0.0, m_lumbar - m_exo)
    return m_mus / R_MUSCLE


def compression_bare(theta_deg: float, weight_kg: float, load_kg: float = 0.0) -> tuple:
    """Returns (F_c_bare, M_lumbar, F_muscle_bare)"""
    theta_rad = math.radians(theta_deg)
    w_upper = upper_body_weight(weight_kg) + load_kg
    m_lumbar = lumbar_moment(theta_deg, weight_kg, load_kg)
    f_muscle = muscle_force_bare(m_lumbar)
    f_c = w_upper * G * math.cos(theta_rad) + f_muscle
    return f_c, m_lumbar, f_muscle


def compression_exo(theta_deg: float, weight_kg: float, spring_k: float, load_kg: float = 0.0) -> tuple:
    """Returns (F_c_exo, M_exo, M_mus_exo, F_muscle_exo)"""
    theta_rad = math.radians(theta_deg)
    w_upper = upper_body_weight(weight_kg) + load_kg
    m_lumbar = lumbar_moment(theta_deg, weight_kg, load_kg)
    m_exo = exo_moment(spring_k, theta_deg)
    m_mus_exo = max(0.0, m_lumbar - m_exo)
    f_muscle_exo = m_mus_exo / R_MUSCLE
    f_c_exo = w_upper * G * math.cos(theta_rad) + f_muscle_exo
    return f_c_exo, m_exo, m_mus_exo, f_muscle_exo


def reduction_percent(f_c_bare: float, f_c_exo: float) -> float:
    if f_c_bare == 0:
        return 0.0
    return max(0.0, (f_c_bare - f_c_exo) / f_c_bare * 100)


def load_index(f_c: float) -> float:
    return f_c / NIOSH_LIMIT


def risk_flag(li: float) -> str:
    if li < 0.75:
        return "normal"
    elif li <= 1.0:
        return "warning"
    else:
        return "high"


def compute_all(theta_deg: float, weight_kg: float, spring_k: float, condition: str, load_kg: float = 0.0) -> dict:
    f_c_bare, m_lumbar, _ = compression_bare(theta_deg, weight_kg, load_kg)
    f_c_exo, m_exo, m_mus_exo, _ = compression_exo(theta_deg, weight_kg, spring_k, load_kg)

    if condition == "exo":
        f_c_display = f_c_exo
    else:
        f_c_display = f_c_bare

    li = load_index(f_c_display)
    red = reduction_percent(f_c_bare, f_c_exo)

    return {
        "theta_deg": round(theta_deg, 2),
        "M_lumbar": round(m_lumbar, 2),
        "M_exo": round(m_exo, 2),
        "M_mus_exo": round(m_mus_exo, 2),
        "F_c_bare": round(f_c_bare, 1),
        "F_c_exo": round(f_c_exo, 1),
        "reduction_percent": round(red, 2),
        "load_index": round(li, 3),
        "risk_flag": risk_flag(li),
    }
