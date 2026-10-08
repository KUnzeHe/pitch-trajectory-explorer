"""各球种位移雷达图 + 轨迹图（MLB 典型值，示意用）。

- 位移雷达：捕手 / 投手两种视角（水平镜像）。
- 轨迹：捕手视角为正投影；投手视角为第一人称透视（相机在出手点后方）。
"""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, Polygon, Rectangle

from matplotlib import font_manager

_fonts = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = next((f for f in ["PingFang SC", "Noto Sans CJK SC", "Heiti SC", "Microsoft YaHei", "SimHei"]
                                    if f in _fonts), "sans-serif")
plt.rcParams["axes.unicode_minus"] = False

# name, abbr, velo (mph), IVB (in), HB (in, arm side +), color
PITCHES = [
    ("四缝线", "4S", 94.5, 16, 8, "#2a78d6"),
    ("伸卡", "SI", 93.5, 8, 15, "#eb6834"),
    ("卡特", "FC", 90, 9, -2.5, "#1baf7a"),
    ("滑球", "SL", 86, 2, -4.5, "#eda100"),
    ("横扫", "ST", 83, 1.5, -15, "#e87ba4"),
    ("曲球", "CU", 79.5, -10, -8, "#008300"),
    ("变速球", "CH", 85.5, 6, 13.5, "#6250d6"),
    ("指叉", "FS", 86.5, 2.5, 9.5, "#e34948"),
]
HAND = "R"
GRID, AXIS, MUTED = "#e1e0d9", "#c3c2b7", "#898781"
VIEW_NAME = {"catcher": "捕手视角", "pitcher": "投手视角"}


def arm_dir(view):
    """画面上手臂侧的方向：+1 在右，-1 在左。
    捕手视角下右投的手臂侧在左（三垒侧），投手视角正好镜像。"""
    d = -1 if HAND == "R" else 1
    return d if view == "catcher" else -d


def third_base_side(view):
    """画面上三垒侧的方向：捕手视角在左，投手视角在右。"""
    return -1 if view == "catcher" else 1


def gravity_drop_in(v_mph, dist_ft=54.0):
    t = dist_ft / (v_mph * 1.4667)
    return 0.5 * 32.2 * t**2 * 12


def radar(ax, view):
    arm = arm_dir(view)
    for r in (5, 10, 15, 20):
        ax.add_patch(Circle((0, 0), r, fill=False, color=GRID, lw=1))
        ax.text(0.5, r - 1.2, str(r), color=MUTED, fontsize=9)
    ax.axhline(0, color=AXIS, lw=1)
    ax.axvline(0, color=AXIS, lw=1)
    for name, ab, v, ivb, hb, c in PITCHES:
        x, y = arm * hb, ivb
        ax.add_patch(Circle((x, y), 2.8, color=c, alpha=0.15, lw=0))
        ax.plot([0, x], [0, y], color=c, lw=2, solid_capstyle="round")
        ax.plot(x, y, "o", ms=8, color=c, mec="white", mew=1.5)
        L = np.hypot(x, y) or 1
        ax.text(x + x / L * 2.2, y + y / L * 2.2, f"{name} {ab}",
                ha="center", va="center", fontsize=9)
    ax.text(0, 21.5, "少坠 (IVB+)", ha="center", color=MUTED, fontsize=10)
    ax.text(0, -22.5, "多坠 (IVB−)", ha="center", color=MUTED, fontsize=10)
    left, right = ("手臂侧", "手套侧") if arm < 0 else ("手套侧", "手臂侧")
    ax.text(-23, 0.8, left, color=MUTED, fontsize=10)
    ax.text(23, 0.8, right, color=MUTED, fontsize=10, ha="right")
    ax.set_xlim(-24, 24)
    ax.set_ylim(-24, 24)
    ax.set_aspect("equal")
    ax.axis("off")
    hand = "右投" if HAND == "R" else "左投"
    ax.set_title(f"位移雷达（{VIEW_NAME[view]}，{hand}，单位 in，IVB 不含重力）", fontsize=12)


def trajectory(ax, view):
    arm = arm_dir(view)
    R = np.array([arm * 2.0, 5.8])   # 出手点 (ft)，在手臂侧
    C = np.array([0.0, 2.5])         # 好球带中心 (ft)
    s = np.linspace(0, 1, 60)
    ax.axhline(0, color=AXIS, lw=1)
    ax.add_patch(Rectangle((-0.83, 1.5), 1.66, 2.0, fill=False,
                           ls="--", color="#52514e", lw=1))
    ax.text(0, 1.3, "好球带", ha="center", va="top", color=MUTED, fontsize=9)
    G0 = gravity_drop_in(90) / 12
    ax.plot(R[0] + (C[0] - R[0]) * s,
            R[1] + (C[1] + G0 - R[1]) * s - G0 * s**2,
            ls="--", color=MUTED, lw=1.5, label="无旋转参考球")
    for name, ab, v, ivb, hb, c in PITCHES:
        G = gravity_drop_in(v) / 12
        hx, iz = arm * hb / 12, ivb / 12
        x = R[0] + (C[0] - R[0]) * s + hx * s**2
        z = R[1] + (C[1] + G - R[1]) * s + (iz - G) * s**2
        ax.plot(x, z, color=c, lw=2, solid_capstyle="round")
        ax.plot(x[-1], z[-1], "o", ms=7, color=c, mec="white", mew=1.5)
        ax.text(x[-1] + (0.12 if x[-1] >= 0 else -0.12), z[-1], ab,
                ha="left" if x[-1] >= 0 else "right", va="center", fontsize=9)
    ax.plot(*R, "o", color=MUTED)
    ax.text(R[0], R[1] + 0.25, "出手点", ha="center", color=MUTED, fontsize=9)
    tb = third_base_side(view)
    ax.text(-3.6, 6.9, "三垒侧" if tb < 0 else "一垒侧", color=MUTED, fontsize=9)
    ax.text(3.6, 6.9, "一垒侧" if tb < 0 else "三垒侧", color=MUTED, fontsize=9, ha="right")
    ax.set_xlim(-3.8, 3.8)
    ax.set_ylim(-0.2, 7.2)
    ax.set_aspect("equal")
    ax.set_xlabel("水平位置 (ft)")
    ax.set_ylabel("高度 (ft)")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.legend(loc="lower left", frameon=False, fontsize=9)
    hand = "右投" if HAND == "R" else "左投"
    ax.set_title(f"{VIEW_NAME[view]}轨迹（{hand}）", fontsize=12)


# ---------------------------------------------------------------- 第一人称透视
# 坐标：x 水平（ft），y 到本垒前缘的距离（ft，朝投手为正），z 离地高度（ft）
FLIGHT_FT = 54.0      # 出手点到本垒的距离
BALL_R = 0.121        # 棒球半径 (ft)


def pitch_path_3d(v, ivb, hb, arm, n=80):
    """与正投影图同一模型：重力 + 匀加速的诱导位移，水平速度近似不变。"""
    R, C = np.array([arm * 2.0, 5.8]), np.array([0.0, 2.5])
    s = np.linspace(0, 1, n)
    G = gravity_drop_in(v) / 12 if v else gravity_drop_in(90) / 12
    hx, iz = arm * hb / 12, ivb / 12
    x = R[0] + (C[0] - R[0]) * s + hx * s**2
    z = R[1] + (C[1] + G - R[1]) * s + (iz - G) * s**2
    y = FLIGHT_FT * (1 - s)
    return x, y, z


def camera(arm, d):
    """相机：出手点后方 d ft、略偏手臂侧、比出手点略高（约在投手肩后）。"""
    return np.array([arm * 0.6, FLIGHT_FT + d, 6.2])


def project(x, y, z, cam):
    depth = cam[1] - y
    return (x - cam[0]) / depth, (z - cam[2]) / depth, depth


def plate_outline():
    """本垒板五边形（地面 z=0），前缘在 y=0。"""
    w = 17 / 24
    xs = np.array([-w, w, w, 0, -w])
    ys = np.array([0, 0, -w, -2 * w, -w])
    return xs, ys, np.zeros(5)


def _draw_scene(ax, view_arm, cam, zoom):
    """在 (u, v) 投影平面上画场景；zoom=True 为本垒放大图。"""
    # 本垒板 + 好球带
    px, py, pz = plate_outline()
    pu, pv, _ = project(px, py, pz, cam)
    ax.add_patch(Polygon(np.c_[pu, pv], closed=True, fc="#f1efe8", ec=AXIS, lw=1))
    zx = np.array([-0.83, 0.83, 0.83, -0.83])
    zz = np.array([1.5, 1.5, 3.5, 3.5])
    zu, zv, _ = project(zx, np.zeros(4), zz, cam)
    ax.add_patch(Polygon(np.c_[zu, zv], closed=True, fill=False, ls="--",
                         ec="#52514e", lw=1))
    # 无旋转参考球
    x, y, z = pitch_path_3d(None, 0, 0, view_arm)
    u, v, _ = project(x, y, z, cam)
    ax.plot(u, v, ls="--", color=MUTED, lw=1.2 if zoom else 1.5, label="无旋转参考球")

    for name, ab, velo, ivb, hb, c in PITCHES:
        x, y, z = pitch_path_3d(velo, ivb, hb, view_arm)
        u, v, depth = project(x, y, z, cam)
        if zoom:
            ax.plot(u, v, color=c, lw=2, solid_capstyle="round")
        else:
            # 线宽随距离变细：近处粗、远处细
            seg = np.stack([np.c_[u[:-1], v[:-1]], np.c_[u[1:], v[1:]]], axis=1)
            lw = np.clip(40 / depth[:-1], 1.0, 4.5)
            ax.add_collection(LineCollection(seg, colors=c, linewidths=lw,
                                             capstyle="round"))
            # 残影：同一时刻的球，按真实大小透视缩小
            for s_idx in (40, 60):
                ax.add_patch(Circle((u[s_idx], v[s_idx]), BALL_R / depth[s_idx],
                                    color=c, alpha=0.35, lw=0))
        ax.plot(u[-1], v[-1], "o", ms=6 if zoom else 4, color=c, mec="white", mew=1.2)
        if zoom:
            ax.text(u[-1] + (0.0012 if u[-1] >= zu.mean() else -0.0012), v[-1], ab,
                    ha="left" if u[-1] >= zu.mean() else "right", va="center", fontsize=9)
    return pu, pv, zu, zv


def trajectory_first_person(fig, d=10.0):
    """投手第一人称透视：下方为全景，上方为本垒附近放大。"""
    arm = arm_dir("pitcher")
    cam = camera(arm, d)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.15, 1], hspace=0.18)
    ax_zoom, ax_main = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])

    # 全景
    pu, pv, zu, zv = _draw_scene(ax_main, arm, cam, zoom=False)
    x0, y0, z0 = pitch_path_3d(94.5, 16, 8, arm)
    ru, rv, rd = project(x0[0], y0[0], z0[0], cam)
    ax_main.add_patch(Circle((ru, rv), BALL_R / rd, color="#888780", alpha=0.9, lw=0))
    ax_main.text(ru, rv + BALL_R / rd + 0.012, "出手点", ha="center", color=MUTED, fontsize=9)
    ax_main.set_aspect("equal")
    ax_main.autoscale_view()
    ax_main.margins(0.06, 0.25)
    ax_main.axis("off")
    ax_main.legend(loc="lower center", frameon=False, fontsize=9)
    # 放大框示意
    # 放大范围：好球带 + 各球种末段（不含地面上的本垒板，避免大片留白）
    ends = [project(*[c[-12:] for c in pitch_path_3d(v, i, h, arm)], cam)
            for _, _, v, i, h, _ in PITCHES]
    eu = np.concatenate([e[0] for e in ends] + [zu])
    ev = np.concatenate([e[1] for e in ends] + [zv])
    bx = (eu.min() - 0.006, eu.max() + 0.006)
    by = (ev.min() - 0.005, ev.max() + 0.003)
    ax_main.add_patch(Rectangle((bx[0], by[0]), bx[1] - bx[0], by[1] - by[0],
                                fill=False, ec="#52514e", lw=0.8, ls=":"))
    ax_main.set_title(f"全景（相机在出手点后方 {d:g} ft，近大远小）", fontsize=10, color="#52514e")

    # 本垒附近放大
    _draw_scene(ax_zoom, arm, cam, zoom=True)
    ax_zoom.set_xlim(*bx)
    ax_zoom.set_ylim(*by)
    ax_zoom.set_aspect("equal")
    ax_zoom.set_xticks([])
    ax_zoom.set_yticks([])
    for sp in ax_zoom.spines.values():
        sp.set_color("#c3c2b7")
    ax_zoom.set_title("本垒附近放大（同一透视）", fontsize=10, color="#52514e")
    tb_left = "一垒侧"
    ax_zoom.text(0.01, 0.02, tb_left, transform=ax_zoom.transAxes, color=MUTED, fontsize=9)
    ax_zoom.text(0.99, 0.02, "三垒侧", transform=ax_zoom.transAxes, color=MUTED,
                 fontsize=9, ha="right")
    hand = "右投" if HAND == "R" else "左投"
    fig.suptitle(f"投手视角轨迹（第一人称透视，{hand}）", fontsize=12)


if __name__ == "__main__":
    import os, sys
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "figures")
    os.makedirs(out, exist_ok=True)
    os.chdir(out)
    for view in ("catcher", "pitcher"):
        fig, ax = plt.subplots(figsize=(7, 7))
        radar(ax, view)
        fig.tight_layout()
        fig.savefig(f"pitch_movement_radar_{view}.png", dpi=200)
        fig.savefig(f"pitch_movement_radar_{view}.svg")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 7))
    trajectory(ax, "catcher")
    fig.tight_layout()
    fig.savefig("pitch_trajectory_catcher.png", dpi=200)
    fig.savefig("pitch_trajectory_catcher.svg")
    plt.close(fig)

    fig = plt.figure(figsize=(8, 8))
    trajectory_first_person(fig, d=10.0)
    fig.savefig("pitch_trajectory_pitcher.png", dpi=200, bbox_inches="tight")
    fig.savefig("pitch_trajectory_pitcher.svg", bbox_inches="tight")
    plt.close(fig)
