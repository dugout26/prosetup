#!/usr/bin/env python3
"""sitemap.xml의 URL을 IndexNow(빙·얀덱스 등)와 네이버 서치어드바이저에 알린다.

build.py와 분리된 수동 실행용. 배포(main 푸시 → GitHub Pages 반영) 후에 1회 실행한다.

  python3 scripts/notify_indexnow.py <키>          # 또는 INDEXNOW_KEY 환경변수
  python3 scripts/notify_indexnow.py <키> --dry    # 보낼 내용만 출력

준비(운영자): 32자 hex 키를 만들고, https://dugout26.github.io/<키>.txt 에 키 문자열만 담긴 파일을
루트 저장소(dugout26/dugout26.github.io)에 올려야 한다. 사이트가 /prosetup 하위 경로라서 keyLocation을 호스트 루트로 고정한다.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOST = "dugout26.github.io"
ENDPOINTS = ["https://api.indexnow.org/indexnow", "https://searchadvisor.naver.com/indexnow"]
MAX_URLS = 10000


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    key = (args[0] if args else os.environ.get("INDEXNOW_KEY", "")).strip()
    if not re.fullmatch(r"[0-9a-fA-F]{8,128}", key):
        sys.exit("키가 없거나 형식이 틀립니다(hex 8~128자). 사용법은 파일 상단 주석 참고.")
    urls = re.findall(r"<loc>([^<]+)</loc>", (ROOT / "sitemap.xml").read_text(encoding="utf-8"))[:MAX_URLS]
    body = {"host": HOST, "key": key, "keyLocation": f"https://{HOST}/{key}.txt", "urlList": urls}
    print(f"URL {len(urls)}개 · keyLocation {body['keyLocation']}")
    if "--dry" in sys.argv:
        print(json.dumps(dict(body, urlList=urls[:5] + ["…"]), ensure_ascii=False, indent=1))
        return
    data = json.dumps(body).encode("utf-8")
    for ep in ENDPOINTS:
        req = urllib.request.Request(ep, data=data, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                print(f"{ep} → {r.status}")
        except urllib.error.HTTPError as e:   # 403=키 파일 불일치, 422=호스트·URL 불일치
            print(f"{ep} → {e.code} {e.read()[:200].decode('utf-8', 'replace')}")
        except urllib.error.URLError as e:
            print(f"{ep} → 연결 실패: {e.reason}")


if __name__ == "__main__":
    main()
