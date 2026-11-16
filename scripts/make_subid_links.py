#!/usr/bin/env python3
"""쿠팡 파트너스 Open API로 페이지 유형별 subId 딥링크를 만들어 products.json에 기록.

build.py는 버튼마다 채널 키(ctx)를 넘긴다:  <게임>_player · <게임>_rank · <게임>_guide
(예: lol_player, valorant_guide). products.json 제품에 coupang_urls[ctx]가 있으면 그 링크를,
없으면 기본 coupang_url을 쓴다. 따라서 이 스크립트를 돌리기 전에도 사이트는 정상 동작한다.

파트너스 리포트에서 subId별 클릭·구매가 갈리므로 '선수 페이지 vs 랭킹 vs 가이드' 성과를 비교할 수 있다.
선수 단위 세분화는 링크 수가 폭증하므로 subId가 아니라 GoatCounter 클릭 이벤트
(coupang/<게임>/player/<선수>/<카테고리>/<제품>)로 본다.

사용법:
  export COUPANG_ACCESS_KEY=... COUPANG_SECRET_KEY=...   # 파트너스 > 추가기능 > Open API
  python3 scripts/make_subid_links.py --dry-run           # 대상만 출력
  python3 scripts/make_subid_links.py                     # product_url 있는 제품만 생성
  python3 scripts/make_subid_links.py --resolve           # product_url 없으면 기존 단축링크 리다이렉트로 원본 URL 확인

주의: --resolve는 기존 파트너스 단축링크를 한 번씩 요청하므로 리포트에 클릭으로 잡힐 수 있다(1회성).
Open API 호출 한도(분당·시간당)가 있어 요청 사이에 간격을 둔다.
"""
import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "products.json"
GAMES = ROOT / "data" / "games.json"
HOST = "https://api-gateway.coupang.com"
PATH = "/v2/providers/affiliate_open_api/apis/openapi/v1/deeplink"
PAGE_TYPES = ["player", "rank", "guide"]


def auth_header(method, path, query, access, secret):
    signed = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
    sig = hmac.new(secret.encode(), (signed + method + path + query).encode(), hashlib.sha256).hexdigest()
    return f"CEA algorithm=HmacSHA256, access-key={access}, signed-date={signed}, signature={sig}"


def deeplinks(urls, sub_id, access, secret):
    body = json.dumps({"coupangUrls": urls, "subId": sub_id}).encode()
    req = urllib.request.Request(HOST + PATH, data=body, method="POST", headers={
        "Authorization": auth_header("POST", PATH, "", access, secret),
        "Content-Type": "application/json;charset=UTF-8"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    if data.get("rCode") != "0":
        raise RuntimeError(data)
    # 판매 중지 등으로 링크를 못 만든 항목은 shortenUrl이 없다 → 건너뛰고 기본 링크를 쓴다
    out = {}
    for d in data.get("data") or []:
        link = d.get("shortenUrl") or d.get("landingUrl")
        if d.get("originalUrl") and link:
            out[d["originalUrl"]] = link
        else:
            print(f"  링크 생성 실패(건너뜀): {d.get('originalUrl')}", file=sys.stderr)
    return out


def resolve(short):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    url = short
    for _ in range(5):
        try:
            opener.open(urllib.request.Request(url, method="HEAD"), timeout=10)
            return None
        except urllib.error.HTTPError as e:
            loc = e.headers.get("Location")
            if not loc:
                return None
            url = loc
            if "coupang.com/vp/products/" in url:
                return url.split("?")[0]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--resolve", action="store_true")
    args = ap.parse_args()

    games = json.load(open(GAMES, encoding="utf-8"))["order"]
    channels = [f"{g}_{t}" for g in games for t in PAGE_TYPES]
    cat = json.load(open(CATALOG, encoding="utf-8"))
    targets = [p for p in cat["products"] if p.get("coupang_url")]
    print(f"링크 있는 제품 {len(targets)}개 × 채널 {len(channels)}개 ({', '.join(channels)})")
    if args.dry_run:
        return

    access, secret = os.environ.get("COUPANG_ACCESS_KEY"), os.environ.get("COUPANG_SECRET_KEY")
    if not (access and secret):
        sys.exit("COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 환경변수가 필요합니다.")

    if args.resolve:
        for p in targets:
            if not p.get("product_url"):
                p["product_url"] = resolve(p["coupang_url"])
                time.sleep(1)
    ready = [p for p in targets if p.get("product_url")]
    print(f"원본 URL 확보 {len(ready)}개")

    for ch in channels:
        sub_id = ch.replace("_", "")          # subId는 영숫자만 (예: lolplayer)
        for i in range(0, len(ready), 20):    # API 1회 최대 20개
            batch = ready[i:i + 20]
            m = deeplinks([p["product_url"] for p in batch], sub_id, access, secret)
            for p in batch:
                if m.get(p["product_url"]):
                    p.setdefault("coupang_urls", {})[ch] = m[p["product_url"]]
            time.sleep(1.5)
        print(f"  {ch} 완료")

    CATALOG.write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("products.json 갱신 — python3 build.py 로 반영")


if __name__ == "__main__":
    main()
