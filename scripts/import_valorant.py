#!/usr/bin/env python3
"""prosettings.net 목록 테이블 스크레이프 결과 → data/raw/valorant/<region>.json 생성.

VCT 국제리그(퍼시픽·아메리카스·EMEA·차이나) 프랜차이즈 팀만 수록한다.
기존 파일의 name_kr(한국 선수 이름)은 유지한다.
"""
import json
import re
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE = Path("/private/tmp/claude-501/-Users-jeki-lol-rune-extension/"
             "d81da40a-1d7b-4f81-b37c-4a75292f2b88/scratchpad/valorant_table.json")
OUT = ROOT / "data" / "raw" / "valorant"
SOURCE = "https://prosettings.net/lists/valorant/"

REGIONS = OrderedDict([
    ("pacific", ("VCT Pacific", ["Gen.G", "DRX", "T1", "Nongshim RedForce", "Paper Rex",
                                 "Rex Regum Qeon", "Team Secret", "Global Esports", "ZETA DIVISION",
                                 "DetonatioN FocusMe", "BOOM Esports", "FULL SENSE"])),
    ("americas", ("VCT Americas", ["Sentinels", "NRG", "100 Thieves", "Cloud9", "Evil Geniuses",
                                   "LOUD", "MIBR", "FURIA", "Leviatan", "KRÜ Esports", "G2 Esports"])),
    ("emea", ("VCT EMEA", ["Fnatic", "Team Heretics", "Team Liquid", "Team Vitality", "Karmine Corp",
                           "Natus Vincere", "BBL Esports", "FUT Esports", "Gentle Mates", "GIANTX"])),
    ("china", ("VCT China", ["Edward Gaming", "Bilibili Gaming", "Trace Esports", "TyLoo",
                             "NOVA Esports", "FunPlus Phoenix", "JD Gaming", "Wolves Esports",
                             "Titan Esports Club", "All Gamers", "Dragon Ranger Gaming"])),
])

COLORS = {"white", "black", "pink", "green", "silver", "magenta", "matcha", "orange", "blue",
          "red", "purple", "yellow", "cyan", "grey", "gray", "navy", "gold", "lilac", "mint"}

def strip_color(v):
    """모델 뒤에 붙은 색상 표기를 떼어 모델 단위로 통일."""
    toks = v.split()
    while len(toks) > 2 and toks[-1].lower() in COLORS:
        toks.pop()
    return " ".join(toks)

GENERIC = ("custom", "unknown", "n/a", "various", "tbd")

def cell(v):
    v = (v or "").strip()
    if not v or v in {"-", "N/A"}:
        return None
    low = v.lower()
    if any(low.startswith(w) for w in GENERIC):
        return None                      # "Custom Keyboard" 같은 총칭은 제품이 아님
    return re.sub(r"\s*\(unreleased\)\s*", "", v, flags=re.I).strip() or None

def entry(v):
    v = cell(v)
    return {"value": strip_color(v), "source": SOURCE, "confidence": "medium"} if v else None

def setting(v):
    v = cell(v)
    return {"value": v, "source": SOURCE, "confidence": "medium"} if v else None

def team_code(name):
    return re.sub(r"[^A-Z0-9]", "", name.upper())[:8] or "TEAM"

def main():
    data = json.load(open(TABLE, encoding="utf-8"))
    rows = data["rows"]
    # 기존 한글 이름 보존
    name_kr = {}
    for f in OUT.glob("*.json"):
        for code, t in json.load(open(f, encoding="utf-8")).items():
            if isinstance(t, dict) and "players" in t:
                for p in t["players"]:
                    if p.get("name_kr"):
                        name_kr[p["nickname"].lower()] = p["name_kr"]

    by_team = {}
    for r in rows:
        _, team, player, mouse, hz, dpi, sens, edpi, scoped, monitor, gpu, res, chair, pad, kb, hs = r[:16]
        by_team.setdefault(team, []).append(dict(
            nickname=player, mouse=mouse, dpi=dpi, sens=sens, edpi=edpi,
            monitor=monitor, res=res, pad=pad, kb=kb, hs=hs))

    # 닉네임 중복 검사(전체 발로란트 범위)
    seen = {}
    for _, (_, teams) in REGIONS.items():
        for t in teams:
            for p in by_team.get(t, []):
                seen.setdefault(p["nickname"].lower(), []).append(t)
    dupes = {n: ts for n, ts in seen.items() if len(ts) > 1}

    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.json"):
        old.unlink()

    total = 0
    for key, (region, teams) in REGIONS.items():
        doc = {"as_of": "2026-08-06",
               "notes": {"source": f"{SOURCE} 목록 테이블(공개 세팅 DB)에서 수집.",
                         "scope": f"{region} 프랜차이즈 팀. 로스터가 아니라 '공개된 세팅 데이터가 있는 선수' 기준.",
                         "colors": "제품 색상 표기는 모델 단위로 통일했습니다."}}
        for t in teams:
            players = by_team.get(t)
            if not players:
                continue
            code = team_code(t)
            doc[code] = {"team_name": t, "region": region, "players": []}
            for p in players:
                nick = p["nickname"]
                doc[code]["players"].append({
                    "nickname": nick,
                    "name_kr": name_kr.get(nick.lower(), ""),
                    "role": "",
                    "slug_suffix": team_code(t).lower() if nick.lower() in dupes else "",
                    "gear": {"mouse": entry(p["mouse"]), "keyboard": entry(p["kb"]),
                             "monitor": entry(p["monitor"]), "headset": entry(p["hs"]),
                             "mousepad": entry(p["pad"])},
                    "settings": {"dpi": setting(p["dpi"]), "in_game_sens": setting(p["sens"]),
                                 "edpi": setting(p["edpi"]), "resolution": setting(p["res"])},
                })
                total += 1
        (OUT / f"{key}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n",
                                         encoding="utf-8")
        n_t = sum(1 for k, v in doc.items() if isinstance(v, dict) and "players" in v)
        print(f"  {key}: {n_t}팀 / {sum(len(v['players']) for k, v in doc.items() if isinstance(v, dict) and 'players' in v)}명")
    print(f"총 {total}명 · 닉네임 중복 {len(dupes)}건 {list(dupes) if dupes else ''}")

if __name__ == "__main__":
    main()
