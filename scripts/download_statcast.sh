#!/usr/bin/env bash
# 从 Baseball Savant 下载指定赛季、名单中每位投手的常规赛逐球数据（Statcast CSV）。
# 用法：scripts/download_statcast.sh 2026        # 读取 data/pitchers_2026.txt，保存到 data/raw/2026/
#       scripts/download_statcast.sh 2025 --force  # 重新下载已存在的文件
# 每位投手一个请求（约 1–2 MB），请勿高频并发访问。
set -euo pipefail
cd "$(dirname "$0")/.."
SEASON="${1:?用法: $0 <赛季> [--force]}"
FORCE="${2:-}"
LIST="data/pitchers_${SEASON}.txt"
OUT="data/raw/${SEASON}"
[[ -f "$LIST" ]] || { echo "找不到名单 $LIST"; exit 1; }
mkdir -p "$OUT"
grep -oE '^[[:space:]]*[0-9]+' "$LIST" | tr -d ' ' | while read -r id; do
  f="$OUT/p_${id}.csv"
  if [[ -s "$f" && "$FORCE" != "--force" && $(wc -l < "$f") -gt 50 ]]; then echo "跳过 $id（已存在）"; continue; fi
  for try in 1 2 3; do
    curl -sS -L -A "Mozilla/5.0" --max-time 150 -o "$f" \
      "https://baseballsavant.mlb.com/statcast_search/csv?all=true&hfGT=R%7C&hfSea=${SEASON}%7C&player_type=pitcher&pitchers_lookup%5B%5D=${id}&type=details" \
      && [[ $(wc -l < "$f") -gt 50 ]] && break
    echo "  $id 第 $try 次下载失败，重试……"; sleep 3
  done
  echo "$id  $(($(wc -l < "$f") - 1)) 球"
  sleep 1
done
