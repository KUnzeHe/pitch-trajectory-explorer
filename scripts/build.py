"""构建单文件交互页面 index.html（球种模型 / 真实数据 / 打击视角 三个标签页）。

用法（在仓库根目录运行）：
  python scripts/build.py                       # 自动读取 data/raw/<赛季>/p_*.csv，输出 index.html
  python scripts/build.py -o out.html 2026=data/raw/2026 2025=data/raw/2025

第一个赛季为页面默认赛季（自动模式下按年份从新到旧）。页面模板位于 src/：
  src/model.html     球种模型（位移雷达、轨迹、透视）
  src/realdata.html  真实数据（Statcast 极坐标散点）
  src/batting.html   打击视角（打者/捕手第一人称、打席模拟）

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
        top = "、".join(f"{TYPES[m['t']][1].split(' ')[0]} {m['u']:.0f}%" for m in mix[:3])
        fb = [m for m in mix if TYPES[m["t"]][0] in FASTBALLS]
        fbm = max(fb, key=lambda m: m["n"]) if fb else None
        auto = f"主要球路：{top}" + (f"；{TYPES[fbm['t']][1]}中位球速 {fbm['v']:.1f} mph" if fbm else "")
        ng = int(len(games))
        pitchers.append({
            "id": pid, "name": display_name(pid, d.player_name.iloc[0]), "hand": hand,
            "role": "先发" if starts >= ng / 2 else "后援", "games": ng, "starts": starts,
            "n": int(len(d)), "teams": teams, "mix": mix, "dropped": dropped,
            "note": auto + ("<br>" + SIGNATURE[pid] if pid in SIGNATURE else ""),
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
  <button class="tab" data-tab="bat" role="tab">打击视角</button>
</div>
<section id="tab-model">{m_body}</section>
<section id="tab-real" hidden>{r_body}</section>
<section id="tab-bat" hidden>{b_body}</section>
</main>
<script>
(()=>{{{m_script}}})();
const REAL=(()=>{{{r_script}}})();
const BAT=((D)=>{{{b_script}}})(REAL.data);
document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===b));
  document.getElementById('tab-model').hidden=b.dataset.tab!=='model';
  document.getElementById('tab-real').hidden=b.dataset.tab!=='real';
  document.getElementById('tab-bat').hidden=b.dataset.tab!=='bat';
  if(b.dataset.tab==='real')REAL.draw();
  BAT.show(b.dataset.tab==='bat');
}});
</script>
</body>
</html>
"""
open(OUT, "w", encoding="utf-8").write(html)
print("wrote", OUT, len(html) // 1024, "KB")
