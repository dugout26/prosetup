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
    "logitech g pro x2 superstrike lunar eclipse": "logitech g pro x2 superstrike",  # 색상 에디션
    "logitech g pro x superlight 2 white": "logitech g pro x superlight 2",
}


# name_kr 자동 생성용 브랜드 한국어 표기(쿠팡·국내 유통 표기 기준). 모델명은 영문 그대로 둔다.
# 자동 결과는 docs/name_kr_review.md 표로 뽑아 사람이 검수하고, 고친 값은 products.json의
# name_kr에 직접 쓰면 재실행해도 보존된다(name_kr_auto=false).
BRAND_KR = {
    "logitech": "로지텍", "razer": "레이저", "zowie": "조위", "vaxee": "백시", "pulsar": "펄사", "asus": "에이수스",
    "artisan": "아티산", "hyperx": "하이퍼엑스", "steelseries": "스틸시리즈", "corsair": "커세어", "alienware": "에일리언웨어",
    "wooting": "우팅", "x-raypad": "엑스레이패드", "xraypad": "엑스레이패드", "sennheiser": "젠하이저", "sony": "소니",
    "lamzu": "람주", "roccat": "로캣", "beyerdynamic": "베이어다이나믹", "aoc": "알파스캔 AOC", "finalmouse": "파이널마우스",
    "lg": "LG", "hp": "HP", "samsung": "삼성", "jbl": "JBL", "cherry": "체리", "astro": "아스트로", "ninjutso": "닌주츠",
    "endgame": "엔드게임기어", "varmilo": "바밀로", "fnatic": "프나틱",
}


def name_kr_auto(name):
    head, _, rest = name.partition(" ")
    kr = BRAND_KR.get(head.casefold())
    return f"{kr} {rest}".strip() if kr and rest else None


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
            keep = {k: prod.get(k) for k in ("coupang_url", "coupang_urls", "product_url", "image", "coupang_name")
                    if prod.get(k)}
            if prod.get("name_kr") and prod.get("name_kr_auto") is False:   # 사람이 고친 한국어명만 보존
                keep["name_kr"], keep["name_kr_auto"] = prod["name_kr"], False
            if prod.get("display_name"):
                keep["name"] = keep["display_name"] = prod["display_name"]
            for alias in prod["aliases"]:
                slot = existing.setdefault(f'{prod["category"]}|{norm_key(alias)}', {})
                for k, v in keep.items():
                    slot.setdefault(k, v)   # 병합 시 링크 있는 쪽이 빈 쪽에 덮이지 않게

    products = []
    for key, counter in groups.items():
        base = key.split("|", 1)[1]
        exact = [v for v in counter if norm_key(v) == base and v.casefold().replace("(", "").replace(")", "") == base]
        display = exact[0] if exact and base in MERGE.values() else counter.most_common(1)[0][0]
        prod = {
            "name": display,
            "category": cats[key],
            "count": sum(counter.values()),
            "coupang_url": None,
            "aliases": sorted(counter),
        }
        prod.update(existing.get(key) or {})
        if prod.get("name_kr_auto") is not False:
            nk = name_kr_auto(prod["name"])
            prod.pop("name_kr", None)
            prod.pop("name_kr_auto", None)
            if nk:
                prod["name_kr"] = nk
        products.append(prod)
    products.sort(key=lambda p: (-p["count"], p["category"], p["name"]))

    out = {
        "_note": "coupang_url을 채우면 build.py가 해당 제품의 모든 노출에 구매 버튼을 렌더. "
                 "aliases는 data/raw에 등장하는 표기들. 이 파일은 scripts/gen_catalog.py로 재생성해도 URL 보존됨.",
        "products": products,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    rows = "".join(f"| {p['category']} | {p['name']} | {p.get('name_kr') or '(없음)'} | "
                   f"{'수기' if p.get('name_kr_auto') is False else '자동'} | {p.get('coupang_name') or ''} |\n"
                   for p in products)
    (ROOT / "docs" / "name_kr_review.md").write_text(
        "# 제품 한국어명(name_kr) 검수표\n\nscripts/gen_catalog.py가 브랜드만 한국어로 바꿔 자동 생성한 값입니다. "
        "틀린 값은 data/products.json에서 name_kr을 고치고 \"name_kr_auto\": false를 넣으면 재생성해도 유지됩니다.\n\n"
        "| 카테고리 | 제품(영문) | name_kr | 구분 | 쿠팡 상품명 |\n|---|---|---|---|---|\n" + rows, encoding="utf-8")
    filled = sum(1 for p in products if p["coupang_url"])
    print(f"제품 {len(products)}개 (링크 채움 {filled}개) → {OUT}")


if __name__ == "__main__":
    main()
