"""Generate biomechanical diagrams for the Word document."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.family"] = ["Microsoft JhengHei", "DejaVu Sans"]
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, Arc, FancyBboxPatch
import numpy as np
import os

OUT = r"C:\Users\long\Desktop\exo\doc_imgs"
os.makedirs(OUT, exist_ok=True)

# ── Figure 1: Biomechanical force model diagram ───────────────────────────────
fig, ax = plt.subplots(figsize=(7, 8))
ax.set_xlim(0, 10)
ax.set_ylim(0, 11)
ax.set_aspect("equal")
ax.axis("off")
fig.patch.set_facecolor("white")

THETA = 35  # degrees for illustration
theta_r = np.radians(THETA)

# Colors
C_BONE  = "#C8A87A"
C_SPINE = "#8B6914"
C_ARROW = "#C00000"
C_BLUE  = "#1F3882"
C_GREEN = "#376830"
C_GRAY  = "#444444"
C_EXO   = "#2E75B6"

# ── Pelvis (simplified rectangle) ────────────────────────────────────────────
pelvis_x, pelvis_y = 5.0, 1.8
ax.add_patch(FancyBboxPatch((pelvis_x-1.6, pelvis_y-0.5), 3.2, 1.0,
    boxstyle="round,pad=0.1", facecolor=C_BONE, edgecolor=C_SPINE, lw=1.5))
ax.text(pelvis_x, pelvis_y+0.1, "骨盆（Pelvis）", ha="center", va="center",
        fontsize=9, fontweight="bold", color=C_SPINE,
        fontproperties=matplotlib.font_manager.FontProperties(family="DejaVu Sans"))

# ── L5-S1 joint point ────────────────────────────────────────────────────────
l5s1_x, l5s1_y = 5.0, 2.5
ax.plot(l5s1_x, l5s1_y, "o", color=C_SPINE, markersize=14, zorder=5)
ax.plot(l5s1_x, l5s1_y, "o", color="#FFD966", markersize=8, zorder=6)
ax.text(l5s1_x+0.3, l5s1_y+0.05, "L5-S1", ha="left", va="center",
        fontsize=9, fontweight="bold", color=C_SPINE)

# ── Spine / trunk line ────────────────────────────────────────────────────────
trunk_len = 4.5
trunk_end_x = l5s1_x + trunk_len * np.sin(theta_r)
trunk_end_y = l5s1_y + trunk_len * np.cos(theta_r)
ax.plot([l5s1_x, trunk_end_x], [l5s1_y, trunk_end_y],
        color=C_SPINE, lw=5, solid_capstyle="round", zorder=3)

# Vertebrae dots along spine
for t in np.linspace(0.3, 1.0, 5):
    vx = l5s1_x + trunk_len * t * np.sin(theta_r)
    vy = l5s1_y + trunk_len * t * np.cos(theta_r)
    ax.plot(vx, vy, "o", color=C_BONE, markersize=7, zorder=4)

# Upper body COM marker (at d_COM = 0.3 * trunk_len / trunk_len → at 67% up)
com_frac = 0.67
com_x = l5s1_x + trunk_len * com_frac * np.sin(theta_r)
com_y = l5s1_y + trunk_len * com_frac * np.cos(theta_r)
ax.plot(com_x, com_y, "D", color=C_BLUE, markersize=10, zorder=7)
ax.text(com_x+0.3, com_y, "質心 COM", ha="left", va="center",
        fontsize=9, color=C_BLUE, fontstyle="italic")

# ── Theta angle arc ───────────────────────────────────────────────────────────
# Vertical reference line
ax.plot([l5s1_x, l5s1_x], [l5s1_y, l5s1_y+3.5],
        color="#AAAAAA", lw=1.2, ls="--")
arc = Arc((l5s1_x, l5s1_y), 1.6, 1.6, angle=0,
          theta1=90-THETA, theta2=90, color=C_BLUE, lw=1.5)
ax.add_patch(arc)
mid_arc = 90 - THETA/2
ax.text(l5s1_x + 1.0*np.cos(np.radians(mid_arc)),
        l5s1_y + 1.0*np.sin(np.radians(mid_arc)),
        "θ", fontsize=14, color=C_BLUE, fontweight="bold", ha="center")

# ── Gravity arrow on COM (W_upper × g × cos θ downward) ──────────────────────
ax.annotate("", xy=(com_x, com_y-1.4), xytext=(com_x, com_y),
            arrowprops=dict(arrowstyle="-|>", color=C_ARROW, lw=2))
ax.text(com_x-0.15, com_y-0.75, "W_upper×g", ha="right", va="center",
        fontsize=8.5, color=C_ARROW, fontweight="bold")

# ── M_lumbar arc (moment at L5-S1) ───────────────────────────────────────────
C_RED = "#8B0000"
moment_arc = Arc((l5s1_x, l5s1_y), 2.4, 2.4, angle=0,
                 theta1=60, theta2=150, color=C_RED, lw=2.2,
                 linestyle="-")
ax.add_patch(moment_arc)
ax.annotate("", xy=(l5s1_x - 1.2*np.cos(np.radians(150)),
                    l5s1_y + 1.2*np.sin(np.radians(150))),
            xytext=(l5s1_x - 1.2*np.cos(np.radians(145)),
                    l5s1_y + 1.2*np.sin(np.radians(145))),
            arrowprops=dict(arrowstyle="-|>", color="#8B0000", lw=1.5))
ax.text(l5s1_x-1.6, l5s1_y+1.6, "M_lumbar", ha="right", va="bottom",
        fontsize=9, color="#8B0000", fontweight="bold")

# ── Muscle force arrow (along spine, away from L5-S1) ────────────────────────
mus_len = 2.0
# Muscle pulls along trunk direction from L5-S1
mus_end_x = l5s1_x + mus_len * np.sin(theta_r)
mus_end_y = l5s1_y + mus_len * np.cos(theta_r)
ax.annotate("", xy=(mus_end_x, mus_end_y), xytext=(l5s1_x, l5s1_y),
            arrowprops=dict(arrowstyle="-|>", color=C_GREEN, lw=2.5))
ax.text(mus_end_x+0.2, mus_end_y+0.1, "F_mus\n= M_lumbar/d_mus",
        ha="left", va="bottom", fontsize=8.5, color=C_GREEN, fontweight="bold")

# ── Exo moment arrow ──────────────────────────────────────────────────────────
exo_arc = Arc((l5s1_x, l5s1_y), 3.2, 3.2, angle=0,
              theta1=65, theta2=85, color=C_EXO, lw=2.5)
ax.add_patch(exo_arc)
ax.text(l5s1_x+1.3, l5s1_y+2.4, "M_exo = k×θ", ha="left", va="center",
        fontsize=8.5, color=C_EXO, fontweight="bold")

# ── d_COM annotation ──────────────────────────────────────────────────────────
# Line from L5S1 to COM
ax.annotate("", xy=(com_x, com_y), xytext=(l5s1_x, l5s1_y),
            arrowprops=dict(arrowstyle="<->", color="#555555", lw=1.2, ls="dotted"))
mid_x = (l5s1_x + com_x) / 2
mid_y = (l5s1_y + com_y) / 2
ax.text(mid_x+0.3, mid_y-0.25, "d_COM\n≈ 0.30 m", ha="left",
        fontsize=8, color="#555555")

# ── d_mus annotation ──────────────────────────────────────────────────────────
# Perpendicular from spine center to muscle line (~0.05m)
perp_x = l5s1_x + 0.7 * np.cos(theta_r)
perp_y = l5s1_y - 0.7 * np.sin(theta_r)
ax.annotate("", xy=(l5s1_x, l5s1_y), xytext=(perp_x, perp_y),
            arrowprops=dict(arrowstyle="<->", color="#888888", lw=1.1))
ax.text(perp_x-0.1, perp_y-0.35, "d_mus ≈ 0.05 m",
        ha="center", fontsize=8, color="#888888")

# ── Compression force arrow (downward at L5S1) ────────────────────────────────
ax.annotate("", xy=(l5s1_x, l5s1_y-1.2), xytext=(l5s1_x, l5s1_y),
            arrowprops=dict(arrowstyle="-|>", color="#990000", lw=3.0))
ax.text(l5s1_x-0.15, l5s1_y-0.65, "F_c", ha="right", va="center",
        fontsize=12, color="#990000", fontweight="bold")

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color=C_ARROW,  label="重力 (W_upper × g)"),
    mpatches.Patch(color=C_GREEN,  label="豎脊肌力 F_mus"),
    mpatches.Patch(color="#8B0000",label="腰椎力矩 M_lumbar"),
    mpatches.Patch(color=C_EXO,    label="外骨骼力矩 M_exo"),
    mpatches.Patch(color="#990000", label="椎間盤壓力 F_c"),
]
ax.legend(handles=legend_items, loc="lower right", fontsize=8.5,
          framealpha=0.9, edgecolor="#CCCCCC")

ax.set_title("腰椎壓力生物力學模型（L5-S1）", fontsize=13, fontweight="bold",
             color=C_BLUE, pad=10,
             fontproperties=matplotlib.font_manager.FontProperties(family="DejaVu Sans"))

plt.tight_layout()
plt.savefig(os.path.join(OUT, "fig1_model.png"), dpi=150, bbox_inches="tight",
            facecolor="white")
plt.close()
print("Figure 1 saved.")

# ── Figure 2: Calculation flow ────────────────────────────────────────────────
fig2, ax2 = plt.subplots(figsize=(8, 9))
ax2.set_xlim(0, 10)
ax2.set_ylim(0, 12)
ax2.axis("off")
fig2.patch.set_facecolor("white")

def flow_box(ax, cx, cy, w, h, text, fill, text_color="white", fontsize=9.5):
    ax.add_patch(FancyBboxPatch((cx-w/2, cy-h/2), w, h,
        boxstyle="round,pad=0.15", facecolor=fill,
        edgecolor="#333333", lw=1.2, zorder=3))
    ax.text(cx, cy, text, ha="center", va="center",
            fontsize=fontsize, color=text_color, fontweight="bold",
            zorder=4, wrap=True,
            multialignment="center")

def flow_arrow(ax, x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2+0.32), xytext=(x1, y1-0.32),
                arrowprops=dict(arrowstyle="-|>", color="#555555", lw=1.5),
                zorder=2)

boxes = [
    (5, 11,   9, 0.8,  "INPUT: θ, W_body, k, condition",   "#1F3882"),
    (5, 9.8,  9, 0.8,  "W_upper = 0.6 × W_body  [kg]",     "#2E75B6"),
    (5, 8.6,  9, 0.8,  "M_lumbar = W_upper × g × d_COM × sin(θ)  [N·m]", "#2E75B6"),
    (5, 7.4,  9, 0.8,  "M_exo = k × θ  [N·m]",             "#2E75B6"),
    (5, 6.2,  9, 0.8,  "M_mus_exo = max(0, M_lumbar − M_exo)  [N·m]",    "#2E75B6"),
    (2.5, 4.8, 4.2, 0.8, "F_c_bare = W×g×cos(θ)\n+ M_lumbar/d_mus  [N]",  "#37563C"),
    (7.5, 4.8, 4.2, 0.8, "F_c_exo = W×g×cos(θ)\n+ M_mus_exo/d_mus  [N]", "#37563C"),
    (5, 3.4,  9, 0.8,  "Reduction% = (F_c_bare − F_c_exo) / F_c_bare × 100",  "#6E3A00"),
    (5, 2.2,  9, 0.8,  "LI = F_c_active / 3400",            "#6E3A00"),
    (5, 1.0,  9, 0.8,  "OUTPUT → risk_flag (normal / warning / high)",    "#880000"),
]

for (cx, cy, w, h, text, fill) in boxes:
    flow_box(ax2, cx, cy, w, h, text, fill)

# Arrows between boxes
for i in range(len(boxes)-1):
    cx1, cy1 = boxes[i][0], boxes[i][1]
    cx2, cy2 = boxes[i+1][0], boxes[i+1][1]
    if i == 4:  # split to two boxes
        flow_arrow(ax2, cx1, cy1, 2.5, 4.8)
        flow_arrow(ax2, cx1, cy1, 7.5, 4.8)
    elif i == 5:  # merge from two to one
        flow_arrow(ax2, 2.5, 4.8, 5, 3.4)
        flow_arrow(ax2, 7.5, 4.8, 5, 3.4)
    elif i >= 6:
        flow_arrow(ax2, cx1, cy1, cx2, cy2)
    elif i < 4:
        flow_arrow(ax2, cx1, cy1, cx2, cy2)

ax2.set_title("計算流程圖", fontsize=13, fontweight="bold", color="#1F3882", pad=10)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "fig2_flow.png"), dpi=150, bbox_inches="tight",
            facecolor="white")
plt.close()
print("Figure 2 saved.")

# ── Figure 3: IMU placement diagram ──────────────────────────────────────────
fig3, ax3 = plt.subplots(figsize=(5, 7))
ax3.set_xlim(0, 6)
ax3.set_ylim(0, 9)
ax3.axis("off")
fig3.patch.set_facecolor("white")

# Body silhouette (simplified)
# Head
ax3.add_patch(plt.Circle((3, 8.2), 0.5, color="#D4A574", zorder=3))
# Torso
ax3.add_patch(FancyBboxPatch((2.0, 4.8), 2.0, 3.0,
    boxstyle="round,pad=0.2", facecolor="#D4A574", edgecolor="#8B6914", lw=1.5, zorder=2))
# Pelvis
ax3.add_patch(FancyBboxPatch((1.7, 3.5), 2.6, 1.1,
    boxstyle="round,pad=0.15", facecolor="#C8A87A", edgecolor="#8B6914", lw=1.5, zorder=2))
# Legs
ax3.add_patch(FancyBboxPatch((2.0, 1.0), 0.8, 2.4, boxstyle="round,pad=0.1",
    facecolor="#D4A574", edgecolor="#8B6914", lw=1, zorder=2))
ax3.add_patch(FancyBboxPatch((3.2, 1.0), 0.8, 2.4, boxstyle="round,pad=0.1",
    facecolor="#D4A574", edgecolor="#8B6914", lw=1, zorder=2))

# Spine line
spine_x = [3, 3]
spine_y = [3.6, 7.6]
ax3.plot(spine_x, spine_y, color="#8B6914", lw=3, ls="--", zorder=4)

# IMU 1 (trunk - upper back)
ax3.add_patch(FancyBboxPatch((3.2, 6.2), 1.3, 0.7,
    boxstyle="round,pad=0.1", facecolor="#2E75B6", edgecolor="#1F3882", lw=2, zorder=5))
ax3.text(3.85, 6.55, "IMU 1\n(軀幹)", ha="center", va="center",
         fontsize=8, color="white", fontweight="bold")
ax3.annotate("", xy=(3.2, 6.55), xytext=(3.0, 6.55),
             arrowprops=dict(arrowstyle="-", color="#2E75B6", lw=1.5))
ax3.text(1.8, 6.55, "θ1", ha="center", va="center", fontsize=11,
         color="#2E75B6", fontweight="bold")

# IMU 2 (pelvis)
ax3.add_patch(FancyBboxPatch((3.2, 3.65), 1.3, 0.7,
    boxstyle="round,pad=0.1", facecolor="#376830", edgecolor="#1F3882", lw=2, zorder=5))
ax3.text(3.85, 4.0, "IMU 2\n(骨盆)", ha="center", va="center",
         fontsize=8, color="white", fontweight="bold")
ax3.annotate("", xy=(3.2, 4.0), xytext=(3.0, 4.0),
             arrowprops=dict(arrowstyle="-", color="#376830", lw=1.5))
ax3.text(1.8, 4.0, "θ2", ha="center", va="center", fontsize=11,
         color="#376830", fontweight="bold")

# L5-S1 label
ax3.plot(3, 3.7, "o", color="#FFD966", markersize=10, zorder=6)
ax3.text(2.7, 3.55, "L5-S1", ha="right", fontsize=8,
         color="#8B6914", fontweight="bold")

# Theta calculation box
ax3.add_patch(FancyBboxPatch((0.2, 0.1), 5.6, 0.75,
    boxstyle="round,pad=0.1", facecolor="#EBF3FB", edgecolor="#2E75B6", lw=1.5))
ax3.text(3, 0.48, "θ（軀幹前傾角）= θ1 − θ2", ha="center", va="center",
         fontsize=9.5, color="#1F3882", fontweight="bold")

ax3.set_title("IMU 配戴位置示意圖", fontsize=12, fontweight="bold", color="#1F3882", pad=8)
plt.tight_layout()
plt.savefig(os.path.join(OUT, "fig3_imu.png"), dpi=150, bbox_inches="tight",
            facecolor="white")
plt.close()
print("Figure 3 saved.")
print("All figures saved to:", OUT)
