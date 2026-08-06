#!/usr/bin/env python3
"""data/raw/*.json의 장비 표기를 정규화해 data/products.json 카탈로그 생성/갱신.

재실행해도 기존 coupang_url은 보존된다 (표기 흔들림은 aliases로 흡수).
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "products.json"

# 정규화 키가 달라도 같은 제품인 것들 (수동 병합: 변형키 → 대표키)
MERGE = {
    "lg 25gr75fg": "lg ultragear 25gr75fg",
    "logitech g733 black": "logitech g733",
    "logitech g pro x 2": "logitech g pro x 2 lightspeed",
    "logitech g pro x tkl black": "logitech g pro x tkl",
    "asus tuf gaming vg279qm 280hz": "asus tuf gaming vg279qm",
}


def norm_key(value: str) -> str:
    """대소문자·괄호·중복공백 차이를 무시하는 병합 키."""
    k = value.casefold()
    k = re.sub(r"[(),.]", " ", k)
    k = re.sub(r"\s+", " ", k).strip()
    return MERGE.get(k, k)


def collect():
    groups = defaultdict(Counter)  # key -> Counter(원 표기)
    cats = {}                      # key -> category
    for f in sorted(RAW.rglob("*.json")):
        data = json.load(open(f, encoding="utf-8"))
        for team in data.values():
            if not isinstance(team, dict) or "players" not in team:
                continue
            for p in team["players"]:
                for cat, entry in (p.get("gear") or {}).items():
                    if entry and entry.get("value"):
                        key = f'{cat}|{norm_key(entry["value"])}'   # 동명 다카테고리 충돌 방지
                        groups[key][entry["value"]] += 1
                        cats[key] = cat
    return groups, cats


def main():
    groups, cats = collect()
    existing = {}
    if OUT.exists():
        for prod in json.load(open(OUT, encoding="utf-8"))["products"]:
            keep = {k: prod.get(k) for k in ("coupang_url", "image", "coupang_name") if prod.get(k)}
            for alias in prod["aliases"]:
                existing[f'{prod["category"]}|{norm_key(alias)}'] = keep

    products = []
    for key, counter in groups.items():
        display = counter.most_common(1)[0][0]
        prod = {
            "name": display,
            "category": cats[key],
            "count": sum(counter.values()),
            "coupang_url": None,
            "aliases": sorted(counter),
        }
        prod.update(existing.get(key) or {})
        products.append(prod)
    products.sort(key=lambda p: (-p["count"], p["category"], p["name"]))

    out = {
        "_note": "coupang_url을 채우면 build.py가 해당 제품의 모든 노출에 구매 버튼을 렌더. "
                 "aliases는 data/raw에 등장하는 표기들. 이 파일은 scripts/gen_catalog.py로 재생성해도 URL 보존됨.",
        "products": products,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    filled = sum(1 for p in products if p["coupang_url"])
    print(f"제품 {len(products)}개 (링크 채움 {filled}개) → {OUT}")


if __name__ == "__main__":
    main()
