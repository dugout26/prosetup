#!/usr/bin/env python3
"""오피셜(transfers.json lol.official)과 data/raw/lol 로스터가 어긋나는지 검사. 어긋나면 목록을 찍고 exit 1.

- 방출·은퇴: 그 선수가 아직 from 팀 블록에 있으면 오류
- 영입·이적·재계약(LCK 10팀 행): 그 선수가 to 팀 블록에 없으면 오류
같은 선수의 오피셜이 여러 건이면 가장 최근 날짜 기준.
"""
import glob
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LCK = {"T1", "GEN", "HLE", "KT", "DK", "NS", "KRX", "DNS", "BNK", "BRO"}

team = {}
for f in glob.glob(str(ROOT / "data/raw/lol/*.json")):
    for code, block in json.load(open(f, encoding="utf-8")).items():
        if isinstance(block, dict) and "players" in block:
            for p in block["players"]:
                team.setdefault(p["nickname"].lower(), set()).add(code)

latest = {}
for o in json.load(open(ROOT / "data/transfers.json", encoding="utf-8"))["lol"]["official"]:
    k = o["nickname"].lower()
    if k not in latest or str(o.get("date", "")) >= str(latest[k].get("date", "")):
        latest[k] = o

bad = []
for k, o in latest.items():
    cur = team.get(k, set())
    if o["type"] in ("방출", "은퇴") and o.get("from") in cur:
        bad.append(f"{o['nickname']}: {o['type']} 오피셜인데 아직 {o['from']} 로스터에 있음")
    elif o["type"] in ("영입", "이적", "재계약") and o.get("to") in LCK and o["to"] not in cur:
        bad.append(f"{o['nickname']}: {o['to']} {o['type']} 오피셜인데 {o['to']} 로스터에 없음 (현재 {sorted(cur) or '없음'})")

if bad:
    print("오피셜·로스터 불일치:")
    print("\n".join("  - " + b for b in bad))
    sys.exit(1)
print(f"오피셜·로스터 일치 (선수 {len(latest)}명)")
