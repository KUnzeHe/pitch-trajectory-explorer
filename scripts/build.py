"""构建单文件交互页面 index.html（球种模型 / 真实数据 / 打击视角 三个标签页）。

用法（在仓库根目录运行）：
  python scripts/build.py                       # 自动读取 data/raw/<赛季>/p_*.csv，输出 index.html
  python scripts/build.py -o out.html 2026=data/raw/2026 2025=data/raw/2025

第一个赛季为页面默认赛季（自动模式下按年份从新到旧）。页面模板位于 src/：
  src/model.html     球种模型（位移雷达、轨迹、透视）
  src/realdata.html  真实数据（Statcast 极坐标散点）
  src/batting.html   第一视角模块（打者/捕手），构建时实例化为「第一视角观察」与「打席模拟」两个标签页

换算约定：
  IVB = pfx_z*12；HB 以手臂侧为正：右投 = -pfx_x*12，左投 = +pfx_x*12。
  打击视角使用 Statcast 9 参数（y0=50 ft 处的速度/加速度）重建完整轨迹，x0、z0 由 plate_x/plate_z 反推。
"""
import argparse
import glob
import json
import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("seasons", nargs="*", help="形如 2026=data/raw/2026；省略时自动扫描 data/raw/")
ap.add_argument("-o", "--out", default=str(ROOT / "index.html"))
args = ap.parse_args()
OUT = args.out
if args.seasons:
    SEASONS = [a.split("=", 1) for a in args.seasons]
else:
    raw = ROOT / "data" / "raw"
    SEASONS = [(d.name, str(d)) for d in sorted(raw.iterdir(), reverse=True)
               if d.is_dir() and glob.glob(str(d / "p_*.csv"))] if raw.exists() else []
if not SEASONS:
    raise SystemExit("没有找到数据：请先运行 scripts/download_statcast.sh 下载到 data/raw/<赛季>/")
DEFAULT_SAMPLE = 600             # 散点每人最多抽样球数（统计量仍用全季）；投手多时自动减少，控制页面体积
SAMPLE = {}
MIN_SHARE = 0.02                 # 某球种占比 < 2% 且 < 30 球视为零星/误分类，剔除

TYPES = [  # code, 中文, light, dark
    ("FF", "四缝线", "#2a78d6", "#3987e5"),
    ("SI", "伸卡", "#eb6834", "#d95926"),
    ("FC", "卡特", "#1baf7a", "#199e70"),
    ("SL", "滑球", "#eda100", "#c98500"),
    ("ST", "横扫", "#e87ba4", "#d55181"),
    ("SV", "横曲球 Slurve", "#00838f", "#26a5b1"),
    ("CU", "曲球", "#008300", "#2a9d2a"),
    ("KC", "指节曲球", "#5f5e5a", "#a8a79f"),
    ("CH", "变速球", "#6250d6", "#9085e9"),
    ("FS", "指叉", "#e34948", "#e66767"),
    ("FO", "叉指球 Forkball", "#8a6a2f", "#b08d4f"),
]
code2i = {t[0]: i for i, t in enumerate(TYPES)}
FASTBALLS = ("FF", "SI", "FC")
TRAJ = ["x0", "z0", "vx0", "vy0", "vz0", "ax", "ay", "az", "ry"]   # Statcast 9 参数（y0=50 ft）+ 出手 y
BAT_SAMPLE = 80                  # 打击视角“实战模式”每人保留的真实投球数
Y_PLATE = 17 / 12                # Statcast plate_x/plate_z 所在平面（本垒前缘）


def add_traj(d):
    """由 plate_x/plate_z 反推 y0=50 ft 处的 x0、z0（Statcast 匀加速轨迹模型）。"""
    tp = (-d.vy0 - np.sqrt(d.vy0 ** 2 - 2 * d.ay * (50 - Y_PLATE))) / d.ay
    d["x0"] = d.plate_x - d.vx0 * tp - 0.5 * d.ax * tp ** 2
    d["z0"] = d.plate_z - d.vz0 * tp - 0.5 * d.az * tp ** 2
    d["ry"] = d.release_pos_y
    return d


def traj_vec(row_or_series):
    r = row_or_series
    return [round(float(r[c]), 3 if c in ("x0", "z0", "ry") else 2) for c in TRAJ]


TEAMS = {  # Statcast 缩写: (中文名, 徽章底色, 徽章文字色)
    "ATH": ("运动家", "#003831", "#EFB21E"), "ATL": ("亚特兰大勇士", "#13274F", "#ffffff"),
    "AZ": ("亚利桑那响尾蛇", "#A71930", "#ffffff"), "BAL": ("巴尔的摩金莺", "#DF4601", "#000000"),
    "BOS": ("波士顿红袜", "#BD3039", "#ffffff"), "CHC": ("芝加哥小熊", "#0E3386", "#ffffff"),
    "CWS": ("芝加哥白袜", "#27251F", "#C4CED4"), "CIN": ("辛辛那提红人", "#C6011F", "#ffffff"),
    "CLE": ("克利夫兰守护者", "#00385D", "#ffffff"), "COL": ("科罗拉多落基", "#333366", "#C4CED4"),
    "DET": ("底特律老虎", "#0C2340", "#ffffff"), "HOU": ("休斯敦太空人", "#002D62", "#EB6E1F"),
    "KC": ("堪萨斯城皇家", "#004687", "#ffffff"), "LAA": ("洛杉矶天使", "#BA0021", "#ffffff"),
    "LAD": ("洛杉矶道奇", "#005A9C", "#ffffff"), "MIA": ("迈阿密马林鱼", "#00A3E0", "#000000"),
    "MIL": ("密尔沃基酿酒人", "#12284B", "#FFC52F"), "MIN": ("明尼苏达双城", "#002B5C", "#ffffff"),
    "NYM": ("纽约大都会", "#002D72", "#FF5910"), "NYY": ("纽约洋基", "#0C2340", "#ffffff"),
    "PHI": ("费城费城人", "#E81828", "#ffffff"), "PIT": ("匹兹堡海盗", "#27251F", "#FDB827"),
    "SD": ("圣迭戈教士", "#2F241D", "#FFC425"), "SF": ("旧金山巨人", "#FD5A1E", "#27251F"),
    "SEA": ("西雅图水手", "#0C2C56", "#ffffff"), "STL": ("圣路易斯红雀", "#C41E3A", "#ffffff"),
    "TB": ("坦帕湾光芒", "#092C5C", "#8FBCE6"), "TEX": ("德州游骑兵", "#003278", "#ffffff"),
    "TOR": ("多伦多蓝鸟", "#134A8E", "#ffffff"), "WSH": ("华盛顿国民", "#AB0003", "#ffffff"),
}

ZH_NAME = {  # 日本投手显示汉字名
    808967: "山本由伸", 660271: "大谷翔平", 808963: "佐佐木朗希", 684007: "今永昇太",
    608372: "菅野智之", 837227: "今井达也", 673540: "千贺滉大",
}
SIGNATURE = {  # 只标注广为人知的招牌球，其余看点由数据自动生成
    673540: "招牌球：“幽灵叉球”（Statcast 记为 FO）",
    642207: "招牌球：“Airbender” 变速球",
    694973: "招牌球：被称作 splinker 的伸卡式指叉（记为 FS）",
    661403: "招牌球：高速卡特",
    445276: "招牌球：卡特",
    477132: "招牌球：滑球 + 12-6 曲球",
}


def display_name(pid, sv):
    last, _, first = sv.partition(", ")
    en = f"{first} {last}".strip()
    return f"{ZH_NAME[pid]} {en}" if pid in ZH_NAME else en


def process(season, src, n_sample, rng):
    files = sorted(glob.glob(f"{src}/p_*.csv"))
    pitchers, rows, frames = [], [], []
    for f in files:
        d = pd.read_csv(f)
        if d.empty:
            continue
        d = d.copy()
        pid = int(d.pitcher.iloc[0])
        hand = d.p_throws.iloc[0]
        d["team"] = np.where(d.inning_topbot == "Top", d.home_team, d.away_team)
        games = d.groupby("game_pk").inning.min()
        starts = int((games == 1).sum())
        d = d[d.pitch_type.isin(code2i)].dropna(subset=["pfx_x", "pfx_z", "release_speed"]).copy()
        vc = d.pitch_type.value_counts()
        keep = [c for c, n in vc.items() if n / len(d) >= MIN_SHARE or n >= 30]
        dropped = {c: int(n) for c, n in vc.items() if c not in keep}
        d = d[d.pitch_type.isin(keep)].copy()
        sign = -1 if hand == "R" else 1
        d["hb"] = (d.pfx_x * 12 * sign).round(1)
        d["ivb"] = (d.pfx_z * 12).round(1)
        d = add_traj(d)
        teams = list(d.sort_values(["game_date", "at_bat_number"]).team.drop_duplicates())
        k = len(pitchers)
        mix = []
        for code, g in d.groupby("pitch_type"):
            mix.append({"t": code2i[code], "n": int(len(g)), "u": round(len(g) / len(d) * 100, 1),
                        "v": round(float(g.release_speed.median()), 1),
                        "s": int(g.release_spin_rate.median()) if g.release_spin_rate.notna().any() else -1,
                        "ivb": round(float(g.ivb.median()), 1), "hb": round(float(g.hb.median()), 1)})
        mix.sort(key=lambda m: -m["n"])
        dt = d.dropna(subset=TRAJ)
        bat_types = [{"t": code2i[c], "n": int(len(g)), "u": round(len(g) / len(dt) * 100, 1),
                      "P": traj_vec(g[TRAJ].median())} for c, g in dt.groupby("pitch_type")]
        bat_types.sort(key=lambda b: -b["n"])
        bs = dt.sample(min(BAT_SAMPLE, len(dt)), random_state=int(rng.integers(1e9)))
        bat_samp = [[code2i[r.pitch_type]] + traj_vec(r._asdict()) for r in bs.itertuples()]
        ff = [m for m in mix if TYPES[m["t"]][0] == "FF"]
        fb = ff or [m for m in mix if TYPES[m["t"]][0] in FASTBALLS]
        fbm = max(fb, key=lambda m: m["n"]) if fb else None
        med = lambda c: float(d[c].median()) if c in d and d[c].notna().any() else None
        metrics = {"fb": fbm, "arm": med("arm_angle"), "ext": med("release_extension"), "relz": med("release_pos_z"),
                   "use": {TYPES[m["t"]][0]: m for m in mix}}
        ng = int(len(games))
        pitchers.append({
            "id": pid, "name": display_name(pid, d.player_name.iloc[0]), "hand": hand,
            "role": "先发" if starts >= ng / 2 else "后援", "games": ng, "starts": starts,
            "n": int(len(d)), "teams": teams, "mix": mix, "dropped": dropped,
            "sig": SIGNATURE.get(pid, ""), "_m": metrics,
            "bat": {"types": bat_types, "samp": bat_samp},
        })
        samp = d.sample(min(n_sample, len(d)), random_state=int(rng.integers(1e9)))
        for r in samp.itertuples():
            rows.append([k, code2i[r.pitch_type], r.hb, r.ivb, round(r.release_speed, 1),
                         int(r.release_spin_rate) if pd.notna(r.release_spin_rate) else -1,
                         r.game_date[5:]])
        d["k"] = k
        frames.append(d)

    alld = pd.concat(frames)
    allstats = []
    for code, g in alld.groupby("pitch_type"):
        allstats.append({"t": code2i[code], "n": int(len(g)), "u": round(len(g) / len(alld) * 100, 1),
                         "v": round(float(g.release_speed.median()), 1),
                         "s": int(g.release_spin_rate.median()),
                         "ivb": round(float(g.ivb.median()), 1), "hb": round(float(g.hb.median()), 1),
                         "np": int(g.k.nunique())})
    allstats.sort(key=lambda m: m["t"])
    rd = alld[alld.p_throws == "R"].dropna(subset=TRAJ)
    typ_types = [{"t": code2i[c], "n": int(len(g)), "u": round(len(g) / len(rd) * 100, 1),
                  "P": traj_vec(g[TRAJ].median())}
                 for c, g in rd.groupby("pitch_type") if g.k.nunique() >= 2]
    typ_types.sort(key=lambda b: -b["n"])
    typical = {"types": typ_types, "np": int(rd.k.nunique())}   # 实战抽样在前端由右投投手的 samp 合并
    add_styles(pitchers, season)
    # 卡片顺序：按球队缩写，再按球数
    order = sorted(range(len(pitchers)), key=lambda i: (pitchers[i]["teams"][-1], -pitchers[i]["n"]))
    remap = {old: new for new, old in enumerate(order)}
    pitchers = [pitchers[i] for i in order]
    for r in rows:
        r[0] = remap[r[0]]
    print(f"[{season}] {len(pitchers)} pitchers, {len(alld)} pitches, {len(rows)} sampled, "
          f"{len({t for p in pitchers for t in p['teams']})} teams")
    for p in pitchers:
        if p["dropped"] or len(p["teams"]) > 1:
            print("   ", p["name"], p["teams"], "dropped:", p["dropped"])
    return {"season": season, "pitchers": pitchers, "rows": rows, "all": allstats,
            "nTotal": int(len(alld)), "typical": typical}


ZH_SHORT = {"FF": "四缝线", "SI": "伸卡", "FC": "卡特", "SL": "滑球", "ST": "横扫", "SV": "横曲球", "CU": "曲球",
            "KC": "指节曲球", "CH": "变速球", "FS": "指叉", "FO": "叉指球"}


def evaluate(p, m, fbv):
    """一两句点评：整体风格 + 主要武器/出手特点。数值均来自该投手本人各球种的中位数。"""
    u, fb, a, e = m["use"], m["fb"], m["arm"], m["ext"]
    g = lambda c: u.get(c)
    fbc = TYPES[fb["t"]][0] if fb else None
    top_fast = fbv.index(fb["v"]) < max(5, len(fbv) // 8) if fb else False
    si, ff, fc = g("SI"), g("FF"), g("FC")
    # 第一句：整体风格
    if si and si["u"] >= 25 and si["u"] > (ff["u"] if ff else 0):
        s1 = f"典型的滚地球投手：伸卡往手臂侧下沉（HB {si['hb']:+.0f} in），引诱打者打成滚地球"
    elif fc and fc["u"] >= 30:
        s1 = f"以卡特为核心：{fc['v']:.0f} mph 的卡特在尾端往手套侧切，专门让打者打在球棒细端、制造弱击球"
    elif fb and fb["v"] >= 97.5 and ff and ff["ivb"] >= 17.5:
        s1 = f"纯粹的力量型：{fb['v']:.0f} mph 的四缝线还带 {ff['ivb']:.0f} in 的「上飘」，专攻好球带上缘"
    elif fb and (fb["v"] >= 97.5 or top_fast):
        s1 = f"靠速度压制，{ZH_SHORT[fbc]}均速 {fb['v']:.1f} mph"
    elif fb and fb["v"] <= 92.5:
        s1 = "球速不占优势，靠球路组合、位移和落点吃饭"
    elif ff and ff["ivb"] >= 18:
        s1 = f"四缝线 IVB 达 {ff['ivb']:.0f} in，比同速度的速球更「浮」，容易让打者挥到球的下方"
    else:
        k = sum(1 for x in u.values() if x["u"] >= 4)
        others = sorted((x for c, x in u.items() if c not in FASTBALLS), key=lambda x: -x["u"])
        if k >= 6:
            s1 = f"球种多达 {k} 种、配球多变，让打者很难押中球种"
        elif ff and ff["u"] >= 50:
            s1 = f"速球主导：四缝线占 {ff['u']:.0f}%，敢在好球带里直接对决"
        elif k <= 2:
            s1 = "只靠两种球的极简组合，胜在每一种都足够有威胁"
        elif ff and ff["ivb"] <= 13.5:
            s1 = f"四缝线偏平（IVB {ff['ivb']:.0f} in），更多依赖位移和出手角度"
        elif len(others) >= 2:
            s1 = f"以{ZH_SHORT.get(fbc, '速球')}为基础，{ZH_SHORT[TYPES[others[1]['t']][0]]}（{others[1]['u']:.0f}%）也是常用的辅助球种"
        else:
            s1 = f"以{ZH_SHORT.get(fbc, '速球')}为基础的均衡型"
    # 第二句：主要武器（使用率最高的非速球），用相对本人速球的差值描述
    base = ff or fb
    off = [x for c, x in u.items() if c not in FASTBALLS]
    s2 = ""
    if off and base:
        w = max(off, key=lambda x: x["u"])
        c = TYPES[w["t"]][0]
        dv, dz, dx = base["v"] - w["v"], base["ivb"] - w["ivb"], w["hb"] - base["hb"]
        nm = ZH_SHORT[c]
        if c in ("ST", "SV") or (c == "SL" and dx <= -12):
            s2 = f"主要武器是{nm}（{w['u']:.0f}%），比速球往手套侧多偏 {abs(dx):.0f} in，用横向位移把打者的视线拉开"
        elif c in ("CU", "KC"):
            s2 = f"主要武器是{nm}（{w['u']:.0f}%），比速球慢 {dv:.0f} mph、多坠 {dz:.0f} in，与速球形成上下和快慢的双重反差"
        elif c in ("CH", "FS", "FO"):
            s2 = f"主要武器是{nm}（{w['u']:.0f}%），出手像速球，但慢 {dv:.0f} mph、多坠 {dz:.0f} in，靠速差和下坠骗挥棒"
        elif c == "SL":
            bits = ([f"比速球慢 {dv:.0f} mph"] if dv >= 2 else []) + ([f"往手套侧多偏 {abs(dx):.0f} in"] if abs(dx) >= 3 else [])
            s2 = f"主要武器是{nm}（{w['u']:.0f}%），" + ("、".join(bits) + "，变化晚且紧" if bits else "轨迹与速球很接近，变化晚而短促")
    # 出手特点（补充半句）
    tail = ""
    if a is not None and a < 20:
        tail = "接近侧投的出手角度让来球更「平」、更横，对同侧打者通常尤其难受"
    elif a is not None and a < 30:
        tail = "低肩出手让速球偏平、横向跑动更明显"
    elif a is not None and a >= 55:
        tail = "高压出手让速球与下坠球形成明显的上下对比"
    elif e and e >= 7.2:
        tail = f"{e:.1f} ft 的超长伸展让出手点更靠近本垒，体感球速比测速更快"
    s2 = "；".join(x for x in (s2, tail) if x)
    return "。".join(x for x in (s1, s2) if x) + "。"


def add_styles(pitchers, season):
    """由数据生成投球风格关键词与一句事实性点评（阈值为经验设定，排名只在本页投手池内比较）。"""
    N = len(pitchers)
    fbv = sorted((p["_m"]["fb"]["v"] for p in pitchers if p["_m"]["fb"]), reverse=True)
    ffi = sorted((p["_m"]["use"]["FF"]["ivb"] for p in pitchers if "FF" in p["_m"]["use"]), reverse=True)
    exts = sorted((p["_m"]["ext"] for p in pitchers if p["_m"]["ext"]), reverse=True)
    for p in pitchers:
        m, u = p["_m"], p["_m"]["use"]
        tags = []  # (显著度, 关键词)
        fb = m["fb"]
        if fb:
            v = fb["v"]
            if v >= 97.5: tags.append((3 + (v - 97.5), "火球型"))
            elif v <= 92.0: tags.append((2, "速度不快、靠控球与变化"))
        if "FF" in u:
            ff = u["FF"]
            if ff["ivb"] >= 18.5: tags.append((2.5 + (ff["ivb"] - 18.5) / 2, "高 IVB「上飘」四缝线"))
            elif ff["ivb"] <= 13.5 and ff["u"] >= 20: tags.append((1.5, "偏平的四缝线"))
            if ff["s"] >= 2550: tags.append((1.4, "高转速四缝线"))
        a = m["arm"]
        if a is not None:
            if a < 20: tags.append((3, "侧投"))
            elif a < 32: tags.append((2.2, "低肩出手"))
            elif a >= 56: tags.append((2, "高压出手"))
        e = m["ext"]
        if e:
            if e >= 7.2: tags.append((2.3, "伸展极长"))
            elif e <= 5.9: tags.append((1.5, "伸展偏短"))
        g = lambda c: u.get(c, {"u": 0, "ivb": 0, "hb": 0})
        if g("SI")["u"] >= 25 and g("SI")["u"] > g("FF")["u"]: tags.append((2.4, "伸卡为主、滚地球型"))
        if g("FC")["u"] >= 30: tags.append((2.4, "卡特为主"))
        if g("ST")["u"] >= 15 and g("ST")["hb"] <= -14: tags.append((2.2, "大横移横扫"))
        if g("SL")["u"] >= 25: tags.append((2.0, "滑球是主要武器"))
        if g("CU")["u"] >= 12 and g("CU")["ivb"] <= -14: tags.append((2.1, "大落差曲球"))
        if g("KC")["u"] >= 15: tags.append((1.8, "指节曲球是主要变化球"))
        if g("CH")["u"] >= 20: tags.append((2.2, "变速球是招牌"))
        if g("FS")["u"] >= 15: tags.append((2.3, "指叉是主武器"))
        if g("FO")["u"] >= 15: tags.append((2.6, "叉指球（幽灵叉）"))
        k = sum(1 for x in u.values() if x["u"] >= 4)
        if k >= 6: tags.append((1.6, f"球路多样（{k} 种）"))
        elif k <= 3: tags.append((1.6, f"球路精简（{k} 种）"))
        tags = [t for _, t in sorted(tags, key=lambda x: -x[0])][:4] or ["均衡型"]
        top = p["mix"][0]
        parts = [f"最常用{TYPES[top['t']][1].split(' ')[0]}（{top['u']:.0f}%）"]
        if fb:
            parts.append(f"{TYPES[fb['t']][1]}中位 {fb['v']:.1f} mph（本页 {N} 人中第 {fbv.index(fb['v']) + 1}）")
        if "FF" in u:
            parts.append(f"四缝线 IVB {u['FF']['ivb']:+.1f} in（第 {ffi.index(u['FF']['ivb']) + 1}）")
        if a is not None:
            parts.append(f"手臂角度 {a:.0f}°")
        if e:
            parts.append(f"伸展 {e:.1f} ft（第 {exts.index(e) + 1}）")
        p["style"] = {"tags": tags, "text": "，".join(parts) + "。", "eval": evaluate(p, m, fbv)}
        del p["_m"]


rng = np.random.default_rng(2026)
def n_sample(src):
    n = len(glob.glob(f"{src}/p_*.csv"))
    return DEFAULT_SAMPLE if n <= 20 else 400


seasons = [process(s, src, SAMPLE.get(s, n_sample(src)), rng) for s, src in SEASONS]
payload = {"types": [{"code": c, "zh": z, "c": l, "cd": dk} for c, z, l, dk in TYPES],
           "teams": {k: {"zh": v[0], "bg": v[1], "fg": v[2]} for k, v in TEAMS.items()},
           "seasons": seasons}

# ---- 合并页面 ----
model = open(ROOT / "src" / "model.html", encoding="utf-8").read()
m_style = re.search(r"<style>(.*?)</style>", model, re.S).group(1)
m_body = re.search(r"<main>(.*?)</main>", model, re.S).group(1)
m_script = re.search(r"<script>(.*?)</script>", model, re.S).group(1)
part = open(ROOT / "src" / "realdata.html", encoding="utf-8").read()
r_style = re.search(r"<style>(.*?)</style>", part, re.S).group(1)
r_body = re.search(r"<!--BODY-->(.*?)<!--/BODY-->", part, re.S).group(1)
r_script = re.search(r"<script>(.*?)</script>", part, re.S).group(1)
r_script = r_script.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False,
                                                           separators=(",", ":")))
bat = open(ROOT / "src" / "batting.html", encoding="utf-8").read()
b_style = re.search(r"<style>(.*?)</style>", bat, re.S).group(1)
b_body = re.search(r"<!--BODY-->(.*?)<!--/BODY-->", bat, re.S).group(1)
b_script = re.search(r"<script>(.*?)</script>", bat, re.S).group(1)


def bat_instance(sec, mode, pfx):
    """打击模块实例化两次（第一视角观察 / 打席模拟）：元素 id 加前缀，固定模式。"""
    body = b_body.replace('id="b-', f'id="{pfx}-')
    js = (b_script.replace("'b-", f"'{pfx}-").replace('"b-', f'"{pfx}-')
          .replace("/*__SEC__*/'tab-bat'", f"'{sec}'").replace("/*__MODE__*/null", f"'{mode}'"))
    return body, js


o_body, o_js = bat_instance("tab-obs", "obs", "o")
p_body, p_js = bat_instance("tab-play", "play", "p")
tab_label = f"真实数据 · {'/'.join(s for s, _ in SEASONS)} MLB 投手"

html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>球种位移与轨迹</title>
<style>{m_style}{r_style}{b_style}</style>
</head>
<body><main>
<h1 class="h1">球种位移与轨迹</h1>
<div class="tabs" role="tablist">
  <button class="tab on" data-tab="model" role="tab">球种模型</button>
  <button class="tab" data-tab="real" role="tab">{tab_label}</button>
  <button class="tab" data-tab="obs" role="tab">第一视角观察</button>
  <button class="tab" data-tab="play" role="tab">打席模拟</button>
</div>
<section id="tab-model">{m_body}</section>
<section id="tab-real" hidden>{r_body}</section>
<section id="tab-obs" hidden>{o_body}</section>
<section id="tab-play" hidden>{p_body}</section>
</main>
<script>
(()=>{{{m_script}}})();
const REAL=(()=>{{{r_script}}})();
const OBS=((D)=>{{{o_js}}})(REAL.data);
const PLAY=((D)=>{{{p_js}}})(REAL.data);
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));
  document.getElementById('tab-model').hidden=b.dataset.tab!=='model';
  document.getElementById('tab-real').hidden=b.dataset.tab!=='real';
  ['obs','play'].forEach(t=>document.getElementById('tab-'+t).hidden=b.dataset.tab!==t);
  if(b.dataset.tab==='real')REAL.draw();
  OBS.show(b.dataset.tab==='obs');PLAY.show(b.dataset.tab==='play');
}});
</script>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8").write(html)
print("wrote", OUT, len(html) // 1024, "KB")
