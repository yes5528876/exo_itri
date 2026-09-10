"""
Lumbar compression force model (L5-S1), single-equivalent-muscle, quasi-static.

Corrected formula set (2025 revision):
  W_upper   [kg]   = UPPER_BODY_RATIO × W_body
  M_lumbar  [N·m]  = W_upper × g × d_COM × sin(θ)
  M_exo     [N·m]  = k × θ          (passive spring, no pre-load)
  M_mus_exo [N·m]  = max(0, M_lumbar - M_exo)
  F_c_bare  [N]    = W_upper × g × cos(θ)  +  M_lumbar  / d_mus
  F_c_exo   [N]    = W_upper × g × cos(θ)  +  M_mus_exo / d_mus
  Reduction [%]    = (F_c_bare - F_c_exo) / F_c_bare × 100
  LI        [-]    = F_c / NIOSH_LIMIT

Numerical check (W_body=65 kg, θ=45°, k=0.5 Nm/deg):
  M_lumbar  ≈  81.2 N·m
  F_c_bare  ≈ 1894 N   (LI ≈ 0.557)
  F_c_exo   ≈ 1444 N   (LI ≈ 0.425)
  Reduction ≈ 23.8 %
"""

import math

# ── Anatomical & physical constants ──────────────────────────────────────────
G               = 9.81   # m/s²,  gravitational acceleration
D_COM           = 0.30   # m,     upper-body COM to L5-S1  (lit. range 0.25–0.35)
D_MUS           = 0.05   # m,     erector spinae moment arm (lit. range 0.04–0.06)
UPPER_BODY_RATIO = 0.60  # —,     upper-body mass fraction  (lit. range 0.55–0.67)
NIOSH_LIMIT     = 3400   # N,     NIOSH L5-S1 injury threshold
LEAN_BACK_DEG   = -2.0   # deg,   measured angle below this = leaning back (clear of
                         #        normal standing sway); highlighted on screen and in Excel


# ── Core biomechanical calculations ──────────────────────────────────────────

def upper_body_mass(weight_kg: float, load_kg: float = 0.0) -> float:
    """Upper-body equivalent mass including any held load.
    Returns [kg].
    """
    return UPPER_BODY_RATIO * weight_kg + load_kg


def lumbar_moment(theta_deg: float, weight_kg: float, load_kg: float = 0.0) -> float:
    """Lumbar equilibrium moment at L5-S1.
    M_lumbar = W_upper[kg] × g × d_COM × sin(θ)
    Returns [N·m].
    """
    return upper_body_mass(weight_kg, load_kg) * G * D_COM * math.sin(math.radians(theta_deg))


def exo_moment(spring_k: float, theta_deg: float) -> float:
    """Passive spring exoskeleton assistive moment (no pre-load).
    M_exo = k[Nm/deg] × θ[deg]
    Returns [N·m].
    """
    return max(0.0, spring_k * theta_deg)


def compression_bare(theta_deg: float, weight_kg: float, load_kg: float = 0.0) -> tuple:
    """L5-S1 compression force WITHOUT exoskeleton.
    F_c_bare = W_upper×g×cos(θ)  +  M_lumbar / d_mus
    Returns (F_c_bare [N], M_lumbar [N·m], F_mus_bare [N]).
    """
    theta_rad = math.radians(theta_deg)
    m_upper   = upper_body_mass(weight_kg, load_kg)       # kg
    m_lumbar  = lumbar_moment(theta_deg, weight_kg, load_kg)  # N·m
    f_mus     = m_lumbar / D_MUS                          # N  (erector spinae force)
    f_c       = m_upper * G * math.cos(theta_rad) + f_mus # N  (total L5-S1 compression)
    return f_c, m_lumbar, f_mus


def compression_exo(theta_deg: float, weight_kg: float, spring_k: float,
                    load_kg: float = 0.0) -> tuple:
    """L5-S1 compression force WITH passive spring exoskeleton.
    F_c_exo = W_upper×g×cos(θ)  +  M_mus_exo / d_mus
    Returns (F_c_exo [N], M_exo [N·m], M_mus_exo [N·m], F_mus_exo [N]).
    """
    theta_rad  = math.radians(theta_deg)
    m_upper    = upper_body_mass(weight_kg, load_kg)
    m_lumbar   = lumbar_moment(theta_deg, weight_kg, load_kg)
    m_exo      = exo_moment(spring_k, theta_deg)
    m_mus_exo  = max(0.0, m_lumbar - m_exo)               # exo absorbs part of moment
    f_mus_exo  = m_mus_exo / D_MUS
    f_c_exo    = m_upper * G * math.cos(theta_rad) + f_mus_exo
    return f_c_exo, m_exo, m_mus_exo, f_mus_exo


def reduction_percent(f_c_bare: float, f_c_exo: float) -> float:
    """Pressure reduction rate (%).
    Reduction = (F_c_bare - F_c_exo) / F_c_bare × 100
    Denominator is the baseline (bare), NOT F_c_exo.
    """
    if f_c_bare <= 0:
        return 0.0
    return max(0.0, (f_c_bare - f_c_exo) / f_c_bare * 100.0)


def load_index(f_c: float) -> float:
    """Dimensionless load index relative to NIOSH 3400 N limit."""
    return f_c / NIOSH_LIMIT


def risk_flag(li: float) -> str:
    """Risk classification based on Load Index.
    LI < 0.75  → 'normal'
    0.75–1.0   → 'warning'
    > 1.0      → 'high'
    """
    if li < 0.75:
        return "normal"
    elif li <= 1.0:
        return "warning"
    return "high"


# ── Unified entry point ───────────────────────────────────────────────────────

def compute_all(theta_deg: float, weight_kg: float, spring_k: float,
                condition: str, load_kg: float = 0.0) -> dict:
    """Compute all biomechanical metrics for the current frame.

    Args:
        theta_deg : calibrated trunk angle as measured [deg]; negative = leaning back
        weight_kg : subject body weight [kg]
        spring_k  : passive spring stiffness [Nm/deg]
        condition : 'bare' or 'exo'
        load_kg   : mass of any held object [kg], default 0

    Negative angles go straight into the formulas (by choice: such rows are
    flagged via LEAN_BACK_DEG instead of clamped). The single-muscle model only
    covers forward flexion, so leaning back gives a negative M_lumbar and an
    F_c_bare below standing weight that turns negative past about -9.5 deg
    (tan θ = -D_MUS/D_COM); F_c_exo stays at W_upper·g·cos θ.

    Returns dict with keys:
        theta_deg, M_lumbar, M_exo, M_mus_exo,
        F_c_bare, F_c_exo, reduction_percent, load_index, risk_flag
    """
    f_c_bare, m_lumbar, _ = compression_bare(theta_deg, weight_kg, load_kg)
    f_c_exo, m_exo, m_mus_exo, _ = compression_exo(theta_deg, weight_kg, spring_k, load_kg)

    # Load index based on the active condition
    f_c_active = f_c_exo if condition == "exo" else f_c_bare
    li  = load_index(f_c_active)
    red = reduction_percent(f_c_bare, f_c_exo)

    return {
        "theta_deg":        round(theta_deg, 2),
        "M_lumbar":         round(m_lumbar, 2),
        "M_exo":            round(m_exo, 2),
        "M_mus_exo":        round(m_mus_exo, 2),
        "F_c_bare":         round(f_c_bare, 1),
        "F_c_exo":          round(f_c_exo, 1),
        "reduction_percent": round(red, 2),
        "load_index":       round(li, 3),
        "risk_flag":        risk_flag(li),
    }
