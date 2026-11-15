#!/usr/bin/env python3
"""data/raw/<game>/*.json → 정적 사이트 생성 (게임별 섹션 + 랭킹 + 제보 + sitemap).

게임 추가: data/games.json 에 항목을 넣고 data/raw/<key>/ 에 로스터 JSON을 두면 된다.
LoL은 path="" 라서 기존 URL(사이트 루트)을 그대로 유지한다.
쿠팡 링크·이미지: data/products.json 카탈로그에서 표기(alias) 매칭으로 해석.
"""
import html
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_URL = "https://dugout26.github.io/prosetup"
VERIFY_GOOGLE = "reLU6hFD0fFzI4ciTnfyEkadi_fsno6fJLTdosq1qTA"
VERIFY_NAVER = None
# 구글 폼(사진·영상 첨부 가능, 구글 로그인 필요). 없으면 사이트 내 폼만 노출.
GFORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSeGvN8f2idXK5TKF7at_2xBPxCVfEoxOBLXEubcZGwWNqUtXw/viewform"

GEAR_LABELS = [("mouse", "마우스"), ("keyboard", "키보드"), ("monitor", "모니터"),
               ("headset", "헤드셋"), ("mousepad", "마우스패드")]
CONF_KR = {"high": "확실", "medium": "보통", "low": "낮음"}

def esc(s):
    return html.escape(str(s), quote=True)

def load_json(rel):
    path = ROOT / rel
    return json.load(open(path, encoding="utf-8")) if path.exists() else None

GAMES_CFG = load_json("data/games.json") or {"order": [], "games": {}}

def load_catalog():
    """alias(원 표기) → 제품 dict. URL·이미지·표시명을 함께 들고 있다."""
    data = load_json("data/products.json")
    if not data:
        return {}
    return {a: prod for prod in data["products"] for a in prod["aliases"]}

CATALOG = load_catalog()
PRODUCTS = (load_json("data/products.json") or {"products": []})["products"]
BY_NAME = {p["name"]: p for p in PRODUCTS}
NOTES = (load_json("data/product_notes.json") or {"notes": {}})["notes"]
NOTES_CI = {k.casefold(): v for k, v in NOTES.items()}
# 후속 모델·단종 안내 + 가성비 대안 (data/alternatives.json)
ALTS = load_json("data/alternatives.json") or {}
SUCCESSOR = ALTS.get("models", {})
BUDGET = ALTS.get("budget", {})

DISC = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."
SEASON = "2026"   # 제목 연도 = 데이터가 반영한 시즌. 2027 로스터 확정·반영 후 바꾼다.
# 클릭 분석: GoatCounter 사이트 코드(예: "prosetup"). 채우면 모든 쿠팡 버튼 클릭이
# coupang/<게임>/<페이지유형>/<선수·카테고리>/<제품> 이벤트로 집계된다. None이면 스크립트 미삽입.
GOATCOUNTER = None
GUIDE_CATS = [("keyboard", "키보드"), ("mouse", "마우스"), ("headset", "헤드셋"),
              ("monitor", "모니터"), ("mousepad", "마우스패드")]

def topic(word):
    """은/는 조사 (받침 유무)."""
    c = ord(word[-1]) - 0xAC00
    return word + ("은" if 0 <= c < 11172 and c % 28 else "는")

def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).casefold()).strip("-")

def note_for(prod, fallback_name=""):
    for n in [prod.get("name", fallback_name)] + list(prod.get("aliases", [])):
        if n and n.casefold() in NOTES_CI:
            return NOTES_CI[n.casefold()]
    return None

def buy_url(prod, ctx=None):
    """subId 채널별 링크(coupang_urls[ctx])가 있으면 우선, 없으면 기본 링크."""
    return (prod.get("coupang_urls") or {}).get(ctx) or prod.get("coupang_url")

CATS = {k for k, _ in GEAR_LABELS}

def with_subid(url, track):
    """쿠팡 단축링크에 subId(게임-페이지유형-카테고리) 부착 → 파트너스 리포트에서 지면별 분리.
    (link.coupang.com 리다이렉트가 subid를 그대로 넘기는 것 확인, 2026-11-15)"""
    if "link.coupang.com" not in url or "subId=" in url:
        return url
    parts = track.split("/")
    cat = next((x for x in parts if x in CATS), "all")
    sub = re.sub(r"[^a-z0-9-]", "", f"{parts[0][:3]}-{parts[1] if len(parts) > 1 else 'etc'}-{cat}")
    return url + ("&" if "?" in url else "?") + "subId=" + sub

def buy_btn(prod, ctx, track, label="쿠팡 최저가 확인", cls="buy"):
    url = buy_url(prod, ctx)
    if not url:
        return ""
    url = with_subid(url, track)
    ev = f"coupang/{track}/{slugify(prod.get('name', ''))}"
    return (f'<a class="{cls}" href="{esc(url)}" target="_blank" rel="nofollow sponsored noopener" '
            f'data-goatcounter-click="{esc(ev)}" data-goatcounter-title="{esc(prod.get("name", ""))}">'
            f'{label} →</a>')

def compute_usage(teams):
    """카테고리별 [(제품, [(닉, 슬러그)...])] 사용자 수 내림차순 + 카테고리별 데이터 보유 선수 수."""
    owner = {a: i for i, prod in enumerate(PRODUCTS) for a in prod["aliases"]}
    users = {}
    known = {k: 0 for k, _ in GEAR_LABELS}
    for players in teams.values():
        for p in players:
            for key, _ in GEAR_LABELS:
                e = (p.get("gear") or {}).get(key)
                if not (e and e.get("value")):
                    continue
                known[key] += 1
                i = owner.get(e["value"])
                if i is not None and PRODUCTS[i]["category"] == key:
                    users.setdefault(i, set()).add((p["nickname"], player_slug(p)))
    usage = {k: [] for k, _ in GEAR_LABELS}
    for i, u in users.items():
        usage[PRODUCTS[i]["category"]].append((PRODUCTS[i], sorted(u, key=lambda x: x[0].casefold())))
    for k in usage:
        usage[k].sort(key=lambda pu: (-len(pu[1]), pu[0]["name"]))
    return usage, known

def alternatives(prod, name, cat, usage, limit=2):
    """(안내 문구, 대안 제품 목록). 후속 모델 지정 → 그대로, 쿠팡 미연결 → 같은 카테고리 인기 제품(같은 브랜드 우선)."""
    out, reason = [], None
    m = SUCCESSOR.get(prod.get("name", name)) or SUCCESSOR.get(name)
    if m:
        reason = m.get("note")
        out = [BY_NAME[n] for n in m.get("alts", []) if n in BY_NAME and buy_url(BY_NAME[n])]
    if not buy_url(prod) and len(out) < limit:
        reason = reason or "쿠팡 정식 판매 리스팅이 확인되지 않아, 같은 종류에서 프로 사용률이 높은 제품을 대신 소개합니다."
        brand = name.split()[0].casefold() if name else ""
        cands = [p for p, _ in usage.get(cat, []) if buy_url(p) and p is not prod and p not in out]
        cands.sort(key=lambda p: 0 if p["name"].split()[0].casefold() == brand else 1)
        out += cands[:limit - len(out)]
    return reason, out[:limit]

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
:root { --bg: #0E1117; --card: #161B24; --tx: #EDEFF3; --mut: #9BA3AF; --gold: #E8C36B;
        --line: rgba(255,255,255,0.09); }
body { font-family: Pretendard, 'Apple SD Gothic Neo', 'Noto Sans KR', -apple-system, sans-serif;
       background: var(--bg); color: var(--tx); line-height: 1.6; -webkit-font-smoothing: antialiased; }
a { color: inherit; text-decoration: none; }
.wrap { max-width: 720px; margin: 0 auto; padding: 28px 18px 60px; }
header.site { display: flex; align-items: baseline; gap: 10px; margin-bottom: 6px; }
header.site .logo { font-size: 22px; font-weight: 900; }
header.site .logo b { color: var(--gold); }
header.site .tag { font-size: 12px; color: var(--mut); }
.disc { font-size: 11.5px; color: var(--mut); background: var(--card); border: 1px solid var(--line);
        border-radius: 8px; padding: 7px 11px; margin: 0 0 10px; }
.updated { font-size: 12px; color: var(--mut); margin-bottom: 24px; }
h1 { font-size: 24px; font-weight: 900; margin: 10px 0 4px; }
.sub { color: var(--mut); font-size: 14px; margin-bottom: 22px; }
.teamblock { margin-bottom: 26px; }
.teamname { display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 800;
            margin-bottom: 10px; }
.teamname i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(126px, 1fr)); gap: 8px; }
.pcell { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
         padding: 12px 14px; transition: border-color 0.15s; }
.pcell:hover { border-color: rgba(232,195,107,0.5); }
.pcell .nick { font-size: 15px; font-weight: 800; }
.pcell .meta { font-size: 11.5px; color: var(--mut); margin-top: 2px; }
.pcell .none { font-size: 10.5px; color: #566070; margin-top: 4px; }
.crumb { font-size: 13px; color: var(--mut); margin-bottom: 18px; }
.crumb a:hover { color: var(--gold); }
.phead { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 4px; }
.phead h1 { margin: 0; font-size: 30px; }
.phead .kr { font-size: 17px; color: var(--mut); }
.rolechip { font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px;
            background: var(--card); border: 1px solid var(--line); color: var(--gold); }
section { margin-top: 26px; }
section h2 { font-size: 16px; font-weight: 800; margin-bottom: 12px; color: var(--gold); }
.gear { display: flex; flex-direction: column; gap: 10px; }
.item { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
        padding: 14px 16px; display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.item .cat { width: 84px; flex: none; font-size: 12.5px; color: var(--mut); font-weight: 700; }
.item .model { font-size: 15px; font-weight: 800; flex: 1; min-width: 160px; }
.item .model.unknown { color: #566070; font-weight: 600; }
.conf { font-size: 10.5px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--line);
        color: var(--mut); flex: none; }
.conf.high { color: #51CF66; border-color: rgba(81,207,102,0.4); }
.conf.low { color: #FFB4B4; border-color: rgba(255,107,107,0.3); }
.buy { flex: none; font-size: 13px; font-weight: 800; padding: 8px 16px; border-radius: 9px;
       background: var(--gold); color: #14171D; }
.buy:hover { background: #F0D08A; }
.settings { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.set { background: var(--card); border: 1px solid var(--line); border-radius: 12px;
       padding: 12px; text-align: center; }
.set .k { font-size: 11.5px; color: var(--mut); }
.set .v { font-size: 17px; font-weight: 900; margin-top: 3px; }
.set .v.unknown { color: #566070; font-weight: 600; font-size: 13px; }
.note { font-size: 12px; color: var(--mut); margin-top: 14px; line-height: 1.7; }
.rankrow { display: flex; align-items: center; gap: 12px; background: var(--card);
           border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; margin-bottom: 8px; }
.rankrow .rk { font-size: 20px; font-weight: 900; color: var(--gold); min-width: 34px; text-align: center; }
.rankrow .rk.top1 { font-size: 24px; }
.rankrow .info { flex: 1; min-width: 0; }
.rankrow .pname { display: block; font-weight: 800; font-size: 15px; }
.rankrow .users { display: block; font-size: 11.5px; color: var(--mut); margin-top: 4px; line-height: 1.6; }
.rankrow .users a { color: #9BA3AF; border-bottom: 1px dotted #566070; }
.rankrow .cnt { font-size: 13px; font-weight: 800; white-space: nowrap; }
.rankbanner { display: block; background: linear-gradient(90deg, rgba(232,195,107,.14), rgba(232,195,107,.03));
              border: 1px solid rgba(232,195,107,.35); border-radius: 12px; padding: 13px 16px;
              margin: 16px 0 4px; font-weight: 800; font-size: 14.5px; }
.rankbanner small { display: block; font-weight: 500; color: var(--mut); margin-top: 2px; font-size: 12px; }
.item .imain { flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.item .thumb { flex: none; width: 62px; height: 62px; border-radius: 10px; background: #0B0E14;
        border: 1px solid var(--line); object-fit: contain; }
.pnotes { flex-basis: 100%; margin-top: 4px; padding-top: 12px; border-top: 1px dashed var(--line); }
.pnotes .spec { font-size: 12px; color: var(--gold); font-weight: 700; margin-bottom: 8px; }
.pnotes ul { list-style: none; display: flex; flex-direction: column; gap: 4px; }
.pnotes li { font-size: 12.5px; color: var(--mut); line-height: 1.6; padding-left: 18px; position: relative; }
.pnotes li::before { position: absolute; left: 0; font-weight: 800; }
.pnotes li.pro::before { content: "＋"; color: #51CF66; }
.pnotes li.con::before { content: "－"; color: #FF8787; }
.rankrow .thumb { flex: none; width: 46px; height: 46px; border-radius: 8px; background: #0B0E14;
        border: 1px solid var(--line); object-fit: contain; }
.tipbox { background: var(--card); border: 1px solid var(--line); border-radius: 14px;
        padding: 16px 18px; margin-bottom: 12px; font-size: 13.5px; line-height: 1.85; color: var(--mut); }
.tipbox b { color: var(--tx); }
.tipbox ol, .tipbox ul { margin: 8px 0 0 18px; }
.tipbox li { margin-bottom: 5px; }
.rform { display: flex; flex-direction: column; gap: 12px; margin-top: 6px; }
.rform label { font-size: 12.5px; font-weight: 700; color: var(--mut); }
.rform label b { color: #FF8787; }
.rform input, .rform textarea, .rform select {
  width: 100%; background: #0B0E14; border: 1px solid var(--line); border-radius: 10px;
  padding: 12px 13px; color: var(--tx); font-size: 14.5px; font-family: inherit; }
.rform input:focus, .rform textarea:focus, .rform select:focus {
  outline: none; border-color: rgba(232,195,107,.6); }
.rform textarea { min-height: 92px; resize: vertical; }
.rform .row { display: flex; gap: 10px; }
.rform .row > div { flex: 1; min-width: 0; }
.rform .hp { position: absolute; left: -9999px; }
.rform button { margin-top: 6px; background: var(--gold); color: #14171D; border: 0;
  border-radius: 10px; padding: 15px; font-size: 15.5px; font-weight: 900; cursor: pointer; }
.rform button:hover { background: #F0D08A; }
.mailrow { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 10px; }
.mailrow code { background: #0B0E14; border: 1px solid var(--line); border-radius: 8px;
  padding: 9px 12px; font-size: 13.5px; color: var(--tx); }
.copybtn { background: var(--card); border: 1px solid var(--line); color: var(--mut);
  border-radius: 8px; padding: 9px 14px; font-size: 13px; font-weight: 700; cursor: pointer; }
.mailbtn { display: inline-block; margin-top: 14px; background: var(--gold); color: #14171D;
        font-weight: 800; font-size: 14px; padding: 12px 22px; border-radius: 10px; }
.etc1 { font-size: 12px; color: #566070; margin: 6px 2px 0; line-height: 1.8; }
.srcs { font-size: 11px; color: #566070; margin-top: 20px; line-height: 1.8; word-break: break-all; }
.srcs a { color: #7A8290; }
footer { margin-top: 44px; padding-top: 18px; border-top: 1px solid var(--line);
         font-size: 11.5px; color: #566070; line-height: 1.8; }
@media (max-width: 520px) {
  .settings { grid-template-columns: 1fr 1fr; }
  .item .cat { width: 100%; }
  .item .imain { flex: 1 1 calc(100% - 76px); }
  .item .buy { margin-left: auto; }
  .rankrow { flex-wrap: wrap; }
  .rankrow .info { flex: 1 1 calc(100% - 50px); }
  .rankrow .cnt { margin-left: 46px; }
  .rankrow .buy { margin-left: auto; }
}

h2.region { font-size: 13px; font-weight: 800; color: var(--gold); letter-spacing: 2px;
            margin: 30px 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--line); }
nav.gnav { display: flex; gap: 8px; margin: 4px 0 18px; flex-wrap: wrap; }
nav.gnav a { font-size: 12.5px; font-weight: 800; padding: 7px 14px; border-radius: 999px;
             background: var(--card); border: 1px solid var(--line); color: var(--mut); }
nav.gnav a.on { color: #14171D; background: var(--gold); border-color: var(--gold); }
nav.gnav a.soon { opacity: .5; }
nav.gnav.sm { margin: 10px 0 16px; }
nav.gnav.sm a { font-size: 12px; padding: 6px 12px; }
.badge.ev { color: #A5D8FF; border-color: rgba(116,192,252,.45); background: rgba(116,192,252,.08); }
.badge { font-size: 10.5px; font-weight: 800; padding: 2px 8px; border-radius: 999px; flex: none;
         color: #FFD8A8; border: 1px solid rgba(255,169,77,.45); background: rgba(255,169,77,.08); }
.specline { flex-basis: 100%; font-size: 12.5px; color: var(--gold); font-weight: 700; margin-top: -2px; }
.ctarow { flex-basis: 100%; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.buy { white-space: nowrap; }
.buy.big { font-size: 15px; padding: 12px 22px; border-radius: 10px; box-shadow: 0 4px 14px rgba(232,195,107,.25); }
.buy.sm { font-size: 12px; padding: 6px 12px; border-radius: 8px; white-space: nowrap; }
.ctahint { font-size: 11.5px; color: var(--mut); }
.alts { flex-basis: 100%; background: #0F131A; border: 1px solid rgba(255,169,77,.3); border-radius: 12px; padding: 12px 14px; }
.alts .alttit { font-size: 12.5px; font-weight: 800; color: #FFD8A8; }
.alts p { font-size: 11.5px; color: var(--mut); margin: 2px 0 8px; }
.altrow { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-top: 1px dashed var(--line); }
.altrow .aname { flex: 1; min-width: 0; font-size: 13.5px; font-weight: 800; }
.altrow .aname small, .cmp td small { display: block; font-size: 11px; color: var(--mut); font-weight: 500; }
.athumb { flex: none; width: 40px; height: 40px; border-radius: 8px; background: #0B0E14; border: 1px solid var(--line); object-fit: contain; }
.budget { flex-basis: 100%; font-size: 12px; color: var(--mut); }
.budget a { color: var(--tx); font-weight: 700; border-bottom: 1px dotted var(--gold); }
details.pnotes summary { font-size: 12px; color: var(--mut); cursor: pointer; font-weight: 700; }
details.pnotes ul { margin-top: 8px; }
.cmp { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; margin: 14px 0; overflow-x: auto; }
.cmptit { font-weight: 900; font-size: 15px; margin-bottom: 8px; }
.cmptit small { font-weight: 500; font-size: 11.5px; color: var(--mut); margin-left: 6px; }
.cmp table { width: 100%; border-collapse: collapse; }
.cmp th { font-size: 11px; color: var(--mut); text-align: left; padding: 4px 6px; font-weight: 700; }
.cmp td { padding: 9px 6px; border-top: 1px solid var(--line); vertical-align: middle; font-size: 13.5px; }
.cmp td.rk { font-weight: 900; color: var(--gold); width: 22px; }
.cmp td.pn { display: flex; gap: 10px; align-items: center; }
.cmp td.pn small.who a { color: #9BA3AF; }
.cmp td.num { width: 90px; position: relative; }
.cmp td.num i { display: block; height: 4px; background: var(--gold); border-radius: 2px; margin-top: 4px; opacity: .8; }
.cmp td.cta { text-align: right; width: 70px; }
.cmp .na { font-size: 11px; color: #566070; }
.cmp td.gc { font-size: 12.5px; }
.cmp td.gc .buy { margin-top: 4px; display: inline-block; }
.cmp a.src { color: #7A8290; border-bottom: 1px dotted #566070; }
.gcard .who { flex-basis: 100%; font-size: 12px; color: var(--mut); }
.gcard .who a, p.more a { color: #9BA3AF; border-bottom: 1px dotted #566070; }
.gcard ul.pc { flex-basis: 100%; list-style: none; }
.gcard ul.pc li, details.pnotes li { font-size: 12.5px; color: var(--mut); line-height: 1.6; padding-left: 18px; position: relative; }
.gcard ul.pc li::before { position: absolute; left: 0; font-weight: 800; }
.gcard ul.pc li.pro::before { content: "＋"; color: #51CF66; }
.gcard ul.pc li.con::before { content: "－"; color: #FF8787; }
a.more, p.more { display: inline-block; font-size: 12.5px; color: var(--mut); margin-top: 8px; }
a.more:hover { color: var(--gold); }
details.faq { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 12px 14px; margin-bottom: 8px; }
details.faq summary { font-weight: 800; font-size: 14px; cursor: pointer; }
details.faq p { font-size: 13px; color: var(--mut); margin-top: 6px; }
@media (max-width: 520px) {
  .buy.big { flex: 1 1 100%; text-align: center; }
  .ctahint { flex-basis: 100%; text-align: center; }
  .cmp td.num { width: 64px; }
}
"""

def gurl(g, *parts):
    """게임 기준 URL. path가 ''이면 사이트 루트."""
    segs = [BASE_URL] + ([g["path"]] if g["path"] else []) + [p for p in parts if p]
    url = "/".join(segs)
    return url if any(parts) else url + "/"   # 디렉터리 URL은 슬래시로 (301 회피)

def gdir(g):
    return ROOT / g["path"] if g["path"] else ROOT

def gnav_html(cur_key):
    links = ""
    for k in GAMES_CFG["order"]:
        g = GAMES_CFG["games"][k]
        cls = " class=\"on\"" if k == cur_key else ""
        links += f'<a{cls} href="{gurl(g, "")}">{esc(g["nav"])}</a>'
    links += '<a class="soon" href="#" onclick="return false">오버워치 · 준비 중</a>'
    return f'<nav class="gnav">{links}</nav>'

def page(g, title, desc, body, canonical, jsonld=None, noindex=False, crumbs=None):
    blocks = [] if not jsonld else (jsonld if isinstance(jsonld, list) else [jsonld])
    if crumbs:
        blocks.append({"@context": "https://schema.org", "@type": "BreadcrumbList",
                       "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                                           for i, (n, u) in enumerate(crumbs)]})
    jsonld = blocks
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="프로셋업">
<meta property="og:image" content="{BASE_URL}/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{BASE_URL}/icon.svg" type="image/svg+xml">
<link rel="icon" href="{BASE_URL}/favicon.ico" sizes="32x32">
{'<meta name="robots" content="noindex,follow">' if noindex else ''}
{f'<meta name="google-site-verification" content="{VERIFY_GOOGLE}">' if VERIFY_GOOGLE else ''}
{f'<meta name="naver-site-verification" content="{VERIFY_NAVER}">' if VERIFY_NAVER else ''}
{f'<script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>' if jsonld else ''}
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="site"><a href="{BASE_URL}/" class="logo">프로<b>셋업</b></a>
<span class="tag">{esc(g["tagline"])}</span></header>
{gnav_html(g["key"])}
<p class="disc">{DISC}</p>
<div class="updated">{game_status(g)}</div>
{body}
<footer>
비공식 팬 사이트입니다. 선수·팀·리그와 무관하며, 장비 정보는 공개 자료를 교차 확인해 정리했습니다.
잘못된 정보·추가 정보 <a href="{gurl(g, 'submit.html')}" style="color:#7A8290;border-bottom:1px dotted #566070">제보하기</a><br>
이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
</footer>
</div>
{f'<script data-goatcounter="https://{GOATCOUNTER}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>' if GOATCOUNTER else ''}
</body>
</html>"""

def raw_meta(g, full=False):
    """게임 raw 파일들의 as_of(장비 확인)·roster_check(로스터 점검) 최신값."""
    as_of, checked = [], []
    for f in (ROOT / "data" / "raw" / g["key"]).glob("*.json"):
        d = json.load(open(f, encoding="utf-8"))
        v = d.get("as_of") or (d.get("meta") or {}).get("as_of")
        if v:
            as_of.append(v)
        for k, c in d.items():
            if k.startswith("roster_check") and isinstance(c, dict) and c.get("checked"):
                checked.append(c["checked"])
    if full:   # sitemap lastmod: 장비·로스터 중 최신 날짜
        both = as_of + checked
        return max(both)[:10] if both else None
    return (max(as_of)[:7] if as_of else None), (max(checked)[:7] if checked else None)

def game_verified(g):
    return raw_meta(g)[0] or "-"

def game_status(g):
    gear, roster = raw_meta(g)
    txt = f"장비 데이터 확인: {gear or '-'}"
    if roster and roster != gear:
        txt += f" · 로스터 점검: {roster}"
    if g.get("status_note"):
        txt += f" · {esc(g['status_note'])}"
    return txt

def load_players(g):
    """{code: [players]}, {code: {kr, color, region}} 반환. 파일·키 순서를 그대로 유지한다."""
    teams, meta = {}, {}
    raw = ROOT / "data" / "raw" / g["key"]
    order = g.get("file_order")
    files = ([raw / f"{n}.json" for n in order if (raw / f"{n}.json").exists()]
             if order else sorted(raw.glob("*.json"))) if raw.exists() else []
    for f in files:
        for code, v in json.load(open(f, encoding="utf-8")).items():
            if not isinstance(v, dict) or "players" not in v:
                continue
            teams.setdefault(code, [])
            meta.setdefault(code, {"kr": v.get("team_name", code),
                                   "color": team_color(code), "region": v.get("region", "")})
            for p in v["players"]:
                p["_team"] = code
                p["role"] = (p.get("role") or "").lower()
                teams[code].append(p)
    for code, override in (g.get("teams") or {}).items():
        if code in meta:
            meta[code].update(override)
    return teams, meta

def team_color(code):
    """팀별 고정 색상 (코드 해시 기반 — 팀이 수십 개라 수동 지정은 하지 않는다)."""
    h = sum((i + 1) * ord(c) for i, c in enumerate(code)) % 360
    return f"hsl({h}, 55%, 55%)"

def player_slug(p):
    s = (p["nickname"] + ("-" + p["slug_suffix"] if p.get("slug_suffix") else "")).lower()
    return re.sub(r"\s+", "-", s.strip())   # 공백은 URL에서 깨지므로 하이픈으로

def role_suffix(roles, p):
    r = roles.get(p["role"], p["role"])
    return f' · {r}' if r else ''

def alt_html(reason, alts, ctx, track):
    if not alts:
        return ""
    rows = ""
    for a in alts:
        n = note_for(a)
        th = (f'<img class="athumb" src="{esc(a["image"])}" alt="{esc(a["name"])}" loading="lazy" '
              f'width="40" height="40">' if a.get("image") else "")
        spec = f"<small>{esc(n['spec'])}</small>" if n and n.get("spec") else ""
        rows += (f'<div class="altrow">{th}<span class="aname">{esc(a["name"])}{spec}</span>'
                 f'{buy_btn(a, ctx, track + "/alt", "최저가", "buy sm")}</div>')
    return f'<div class="alts"><div class="alttit">추천 대안 모델</div><p>{esc(reason or "")}</p>{rows}</div>'

def budget_html(cat, ctx, track):
    picks = [b for b in BUDGET.get(cat, []) if b.get("coupang_url")]
    if not picks:
        return ""
    links = []
    for b in picks[:2]:
        ev = f"coupang/{track}/budget/{slugify(b['name'])}"
        spec = f" <small>{esc(b['spec'])}</small>" if b.get("spec") else ""
        links.append(f'<a href="{esc(with_subid(b["coupang_url"], track))}" target="_blank" rel="nofollow sponsored noopener" '
                     f'data-goatcounter-click="{esc(ev)}">{esc(b["name"])}</a>{spec}')
    return f'<div class="budget">💸 부담되면 가성비 대안: {" · ".join(links)}</div>'

def item_html(cat_key, cat_label, entry, ctx="", track="", usage=None, tournament=None):
    if (not entry or not entry.get("value")) and tournament and tournament.get(cat_key):
        t = tournament[cat_key]
        entry = {"value": t, "confidence": "event"}
    if not entry or not entry.get("value"):
        return (f'<div class="item"><div class="imain"><span class="cat">{cat_label}</span>'
                f'<span class="model unknown">확인 중 — 공개 정보 수집 중</span></div>'
                f'{budget_html(cat_key, ctx, track)}</div>')
    conf = entry.get("confidence", "medium")
    name = entry["value"]
    prod = CATALOG.get(name, {})
    if entry.get("coupang_url"):
        prod = dict(prod, coupang_url=entry["coupang_url"])
    thumb = (f'<img class="thumb" src="{esc(prod["image"])}" alt="{esc(name)}" '
             f'loading="lazy" width="62" height="62">' if prod.get("image") else "")
    note = note_for(prod, name)
    succ = SUCCESSOR.get(prod.get("name", name)) or SUCCESSOR.get(name)
    badge = (f'<span class="badge">{esc(succ.get("status_kr", "후속 모델 출시"))}</span>' if succ else "")
    if conf == "event":
        badge = '<span class="badge ev">대회 지급 장비</span>'
        spec = '<div class="specline">경기장 지급 장비 기준 — 선수 개인 사용 모델은 미확인</div>'
    else:
        spec = None
    if spec is None:
        spec = f'<div class="specline">{esc(note["spec"])}</div>' if note and note.get("spec") else ""
    btn = buy_btn(prod, ctx, track, "쿠팡 최저가 확인", "buy big")
    cta = (f'<div class="ctarow">{btn}<span class="ctahint">가격·로켓배송 여부는 쿠팡에서 실시간 확인</span></div>'
           if btn else "")
    reason, alts = alternatives(prod, name, cat_key, usage or {})
    if conf == "event" and alts:
        reason = "개인 장비가 확인되지 않아, 프로들이 개인적으로 가장 많이 쓰는 같은 종류 제품을 소개합니다."
    pc = ""
    if note and (note.get("pros") or note.get("cons")):
        lis = "".join(f'<li class="pro">{esc(x)}</li>' for x in note.get("pros", []))
        lis += "".join(f'<li class="con">{esc(x)}</li>' for x in note.get("cons", []))
        pc = f'<details class="pnotes"><summary>프로 사용 관점 장단점</summary><ul>{lis}</ul></details>'
    conf_chip = ("" if conf == "event" else
                 f'<span class="conf {conf}">신뢰도 {CONF_KR.get(conf, conf)}</span>')
    return (f'<div class="item">{thumb}<div class="imain">'
            f'<span class="cat">{cat_label}</span>'
            f'<span class="model">{esc(name)}</span>{badge}'
            f'{conf_chip}</div>'
            f'{spec}{cta}{alt_html(reason, alts, ctx, track)}{budget_html(cat_key, ctx, track)}{pc}</div>')

def build_submit(g, missing):
    """제보 안내 페이지 — 증거 기준과 검증 절차를 명시."""
    miss_html = ""
    if missing:
        miss_html = ('<section><h2>특히 이런 정보가 필요합니다</h2>'
                     '<p class="note" style="margin-top:0">아래 선수들은 아직 확인된 장비 정보가 없습니다. '
                     '한 항목만 알려주셔도 큰 도움이 됩니다.</p><div class="pgrid" style="margin-top:12px">' +
                     "".join(f'<a class="pcell" href="{gurl(g, "players", s + ".html")}">'
                             f'<div class="nick">{esc(n)}</div><div class="meta">{esc(t)}</div></a>'
                             for n, s, t in missing) +
                     '</div></section>')
    other_game = "발로란트" if g["key"] == "lol" else "리그 오브 레전드"
    mailto = ("mailto:dugout26.gm@gmail.com?subject=%5B%EC%A0%9C%EB%B3%B4%5D%20%EC%84%A0%EC%88%98%EB%AA%85%20-%20%ED%95%AD%EB%AA%A9"
              "&amp;body=%EA%B2%8C%EC%9E%84%3A%20" + g["short"] +
              "%0A%EC%84%A0%EC%88%98%3A%20%0A%ED%95%AD%EB%AA%A9%3A%20%0A%EC%A0%9C%ED%92%88%EB%AA%85%3A%20"
              "%0A%EA%B7%BC%EA%B1%B0(%EB%A7%81%ED%81%AC%2B%ED%83%80%EC%9E%84%EC%8A%A4%ED%83%AC%ED%94%84)%3A%20"
              "%0A%ED%99%95%EC%9D%B8%20%EC%8B%9C%EC%A0%90%3A%20")
    body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › 정보 제보</div>
<h1>장비 정보 제보하기</h1>
<p class="sub">틀린 정보를 바로잡거나, 아직 없는 선수의 장비를 알려주실 수 있습니다.
확인된 제보만 반영하기 때문에 <b>근거 자료</b>를 함께 주셔야 합니다.</p>

<section><h2>제보에 꼭 담아주세요</h2>
<div class="tipbox">
<b>1. 게임과 선수 이름, 항목</b> — 예: "발로란트 / 스타크 / 마우스"<br>
<b>2. 제품명</b> — 가능한 한 정확한 모델명 (예: Logitech G840, 색상·사이즈까지)<br>
<b>3. 근거</b> — 아래 중 <b>하나 이상</b>
<ul>
<li>선수 개인 방송·유튜브 영상 링크 <b>+ 해당 장면 타임스탬프</b></li>
<li>선수·팀 공식 SNS 게시물 링크</li>
<li>인터뷰·기사 링크 (제품명이 언급된 부분)</li>
<li>대회·연습실 셋업 사진 (제품 식별이 가능한 화질, 출처 표기)</li>
</ul>
<b>4. (선택) 확인 시점</b> — 언제 기준인지 (장비는 시즌 중에도 바뀝니다)
</div>
</section>

<section><h2>이렇게 검증합니다</h2>
<div class="tipbox">
<ol>
<li>근거 자료를 직접 확인합니다. 링크가 없거나 확인이 안 되면 반영하지 않습니다.</li>
<li>가능하면 <b>다른 출처와 교차 확인</b>합니다. 1개 출처만 있으면 신뢰도를 '보통'으로 표기합니다.</li>
<li>선수 본인·팀 공식 자료로 확인되면 신뢰도 '확실'로 표기합니다.</li>
<li>기존 정보와 충돌하면 <b>더 최신 자료</b>를 우선합니다.</li>
</ol>
<span style="font-size:12px">추측·"어디서 봤는데" 류 제보는 반영하지 않습니다. 잘못된 정보가 올라가면
사이트 전체의 신뢰도가 떨어지기 때문입니다.</span>
</div>
</section>

{miss_html}

<section><h2>제보 보내기</h2>
<div class="tipbox" style="border-color:rgba(232,195,107,.4)">
<b style="font-size:15px">방법 1 — 구글 폼 (권장)</b><br>
셋업 <b>사진·영상을 직접 첨부</b>할 수 있어 확인이 빠릅니다. 구글 로그인이 필요합니다.
<div><a class="mailbtn" href="{GFORM_URL}" target="_blank" rel="noopener">📋 구글 폼으로 제보하기</a></div>
</div>
<div class="tipbox">
<b style="font-size:15px">방법 2 — 아래 폼 (로그인 없이)</b><br>
구글 계정이 없거나 로그인이 번거로우면 이쪽을 쓰세요. 사진은 링크로 남겨주시면 됩니다.
</div>
<div class="tipbox" style="padding-bottom:20px">
<form class="rform" action="https://formsubmit.co/dugout26.gm@gmail.com" method="POST">
<input type="hidden" name="_subject" value="[프로셋업 제보] {g['short']}">
<input type="hidden" name="_template" value="table">
<input type="hidden" name="_next" value="{gurl(g, 'thanks.html')}">
<input class="hp" type="text" name="_honey" tabindex="-1" autocomplete="off">
<div class="row">
<div><label>게임</label>
<select name="게임"><option>{g['name']}</option><option>{other_game}</option></select></div>
<div><label>선수 <b>*</b></label>
<input name="선수" required placeholder="예: 케리아"></div>
</div>
<div class="row">
<div><label>항목 <b>*</b></label>
<select name="항목" required><option>마우스</option><option>키보드</option><option>모니터</option>
<option>헤드셋</option><option>마우스패드</option><option>DPI·감도</option></select></div>
<div><label>제품명 <b>*</b></label>
<input name="제품명" required placeholder="예: Logitech G840"></div>
</div>
<label>근거 <b>*</b> — 영상 링크(타임스탬프 포함)·SNS·기사·셋업 사진 출처</label>
<textarea name="근거" required placeholder="예: https://youtu.be/xxxx?t=372 (해당 장면에서 로고 확인)"></textarea>
<div class="row">
<div><label>확인 시점 (선택)</label>
<input name="확인시점" placeholder="예: 2026년 8월 방송"></div>
<div><label>회신받을 메일 (선택)</label>
<input type="email" name="email" placeholder="반영 여부 회신이 필요할 때만"></div>
</div>
<button type="submit">제보 보내기</button>
</form>
<p style="margin-top:14px; font-size:12px">
제보 내용은 폼 전송 서비스(FormSubmit)를 거쳐 운영자 메일로 전달됩니다. 회신용 메일을 적지 않으면
연락처는 수집되지 않습니다. 반영은 근거 확인이 끝나는 대로 진행하며, 개별 회신은 어려울 수 있습니다.</p>
</div>
</section>

<section><h2>둘 다 안 될 때</h2>
<div class="tipbox">
아래 주소로 메일을 보내주셔도 됩니다.
<div class="mailrow"><code id="mailaddr">dugout26.gm@gmail.com</code>
<button class="copybtn" onclick="navigator.clipboard.writeText('dugout26.gm@gmail.com');this.textContent='복사됨';">주소 복사</button></div>
</div>
</section>"""
    title = f"장비 정보 제보 — 프로셋업 {g['short']}"
    desc = f"{g['league']} 프로 선수 장비 정보의 오류 수정·추가 제보를 받습니다. 근거 자료 기준과 검증 절차를 안내합니다."
    out = gdir(g) / "submit.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(g, title, desc, body, gurl(g, "submit.html")), encoding="utf-8")
    return gurl(g, "submit.html")

def build_thanks(g):
    body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › 제보 완료</div>
<h1>제보 감사합니다</h1>
<p class="sub">근거 자료를 확인한 뒤 반영합니다. 확인이 어려운 제보는 반영되지 않을 수 있습니다.</p>
<div class="tipbox">확인에는 보통 며칠이 걸립니다. 반영되면 해당 선수 페이지의 '데이터 확인 시점'이 갱신됩니다.<br>
<a class="mailbtn" href="{gurl(g, '')}">돌아가기</a></div>"""
    out = gdir(g) / "thanks.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(g, f"제보 완료 — 프로셋업 {g['short']}", "제보해주셔서 감사합니다.",
                        body, gurl(g, "thanks.html"), noindex=True), encoding="utf-8")
    return gurl(g, "thanks.html")

def compare_table(g, usage, known, cat, label, ctx, track, top=5):
    """사용률 TOP 비교표: 순위·제품·사용 선수 수·사용률·스펙·구매."""
    rows = usage.get(cat, [])[:top]
    if not rows:
        return ""
    trs = ""
    for r, (prod, us) in enumerate(rows, 1):
        n = note_for(prod)
        pct = round(100 * len(us) / known[cat]) if known.get(cat) else 0
        th = (f'<img class="athumb" src="{esc(prod["image"])}" alt="" loading="lazy" width="40" height="40">'
              if prod.get("image") else "")
        who = ", ".join(f'<a href="{gurl(g, "players", sl + ".html")}">{esc(nk)}</a>' for nk, sl in us[:3])
        if len(us) > 3:
            who += f" 외 {len(us) - 3}"
        btn = buy_btn(prod, ctx, f"{track}/{cat}/top{r}", "최저가", "buy sm")
        if not btn:
            _, alts = alternatives(prod, prod["name"], cat, usage, 1)
            btn = (f'<small class="na">대안</small>{buy_btn(alts[0], ctx, f"{track}/{cat}/top{r}/alt", "최저가", "buy sm")}'
                   if alts else '<span class="na">미판매</span>')
        spec = esc(n["spec"]) if n and n.get("spec") else ""
        trs += (f'<tr><td class="rk">{r}</td><td class="pn">{th}<span><b>{esc(prod["name"])}</b>'
                f'<small>{spec}</small><small class="who">{who}</small></span></td>'
                f'<td class="num"><b>{len(us)}명</b><small>{pct}%</small><i style="width:{pct}%"></i></td>'
                f'<td class="cta">{btn}</td></tr>')
    return (f'<div class="cmp"><div class="cmptit">사용률 TOP{len(rows)} {label} '
            f'<small>{label} 데이터가 있는 {known[cat]}명 기준</small></div>'
            f'<table><thead><tr><th>#</th><th>제품</th><th>사용률</th><th></th></tr></thead>'
            f'<tbody>{trs}</tbody></table></div>')

def build_rankings(g, teams, usage, known):
    """해당 게임 선수 데이터 기준 카테고리별 사용 순위 + 상단 TOP 비교표."""
    ctx, track = f"{g['key']}_rank", f"{g['key']}/rank"
    total_players = sum(len(v) for v in teams.values())
    tables = "".join(compare_table(g, usage, known, k, l, ctx, track)
                     for k, l in GUIDE_CATS[:3])
    sections, top_mouse = "", []
    for key, label in GEAR_LABELS:
        rows = usage.get(key, [])
        main = [(p, u) for p, u in rows if len(u) >= 2]
        rest = [(p, u) for p, u in rows if len(u) == 1]
        if key == "mouse":
            top_mouse = [p["name"] for p, _ in main[:5]]
        rhtml = ""
        for rank, (prod, names) in enumerate(main, 1):
            SHOW = 8
            chips = " ".join(f'<a href="{gurl(g, "players", s + ".html")}">{esc(n)}</a>'
                             for n, s in names[:SHOW])
            if len(names) > SHOW:
                chips += f' <span>외 {len(names) - SHOW}명</span>'
            buy = buy_btn(prod, ctx, f"{track}/{key}", "최저가 보기")
            th = (f'<img class="thumb" src="{esc(prod["image"])}" alt="{esc(prod["name"])}" '
                  f'loading="lazy" width="46" height="46">' if prod.get("image") else "")
            rhtml += (f'<div class="rankrow"><span class="rk{" top1" if rank == 1 else ""}">{rank}</span>{th}'
                      f'<span class="info"><span class="pname">{esc(prod["name"])}</span>'
                      f'<span class="users">{chips}</span></span>'
                      f'<span class="cnt">{len(names)}명</span>{buy}</div>')
        if rest:
            rhtml += ('<p class="etc1">1명 사용: ' +
                      " · ".join(esc(p["name"]) for p, _ in rest) + "</p>")
        if rhtml:
            guide = f'<a class="more" href="{gurl(g, "guides", key + ".html")}">{label} 추천 가이드 보기 →</a>'
            sections += f'<section><h2>가장 많이 쓰는 {label}</h2>{rhtml}{guide}</section>'

    title = f"{g['league']} 프로게이머 사용률 TOP 키보드·마우스·헤드셋 순위 ({SEASON})"
    desc = (f"{g['league']} {total_players}명 선수 데이터 기준 — {g['name']} 프로들이 실제 사용하는 "
            "게이밍 키보드·마우스·헤드셋·모니터·마우스패드 사용률 비교표와 쿠팡 최저가 링크.")
    body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › 장비 랭킹</div>
<h1>{esc(g['league'])} 프로들이 가장 많이 쓰는 장비는?</h1>
<p class="sub">{total_players}명의 확인된 장비 데이터를 집계한 실사용 순위입니다.
사용률은 해당 장비 정보가 확인된 선수 수 대비 비율이며, 같은 모델의 색상판은 별도 항목입니다.</p>
{guide_nav(g)}
{tables}
{sections}"""
    jsonld = {"@context": "https://schema.org", "@type": "ItemList", "name": title,
              "itemListElement": [{"@type": "ListItem", "position": r + 1, "name": f"{l} 순위",
                                   "url": gurl(g, "guides", k + ".html")}
                                  for r, (k, l) in enumerate(GUIDE_CATS) if usage.get(k)]}
    out = gdir(g) / "rankings.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(g, title, desc, body, gurl(g, "rankings.html"), jsonld,
                        crumbs=[(f"{g['short']} 홈", gurl(g, "")), ("장비 랭킹", gurl(g, "rankings.html"))]),
                   encoding="utf-8")
    return gurl(g, "rankings.html")

def guide_nav(g, cur=None):
    links = "".join(f'<a{" class=on" if k == cur else ""} href="{gurl(g, "guides", k + ".html")}">{l}</a>'
                    for k, l in GUIDE_CATS)
    return f'<nav class="gnav sm"><a href="{gurl(g, "rankings.html")}"{" class=on" if cur == "rank" else ""}>전체 랭킹</a>{links}</nav>'

GUIDE_TITLES = {
    "keyboard": "프로게이머 키보드 추천 — {league} 선수 사용률 순위",
    "mouse": "{league} 선수 마우스 순위 — 프로게이머 마우스 추천",
    "headset": "프로게이머 헤드셋 추천 — {league} 선수 사용률 순위",
    "monitor": "프로게이머 모니터 추천 — {league} 선수 사용 모니터 순위",
    "mousepad": "프로게이머 마우스패드 추천 — {league} 선수 사용 순위",
}

def build_guides(g, teams, usage, known):
    """검색 유입용 카테고리 가이드 정적 페이지. 본문은 전부 데이터에서 생성(추측 문구 없음)."""
    urls = []
    ctx = f"{g['key']}_guide"
    for cat, label in GUIDE_CATS:
        rows = usage.get(cat, [])
        if not rows:
            continue
        track = f"{g['key']}/guide/{cat}"
        title = GUIDE_TITLES[cat].format(league=g["league"]) + f" ({SEASON})"
        top = rows[0]
        n_known = known.get(cat, 0)
        top_pct = round(100 * len(top[1]) / n_known) if n_known else 0
        cards = ""
        for r, (prod, us) in enumerate(rows[:10], 1):
            n = note_for(prod)
            th = (f'<img class="thumb" src="{esc(prod["image"])}" alt="{esc(prod["name"])}" loading="lazy" '
                  f'width="62" height="62">' if prod.get("image") else "")
            who = ", ".join(f'<a href="{gurl(g, "players", sl + ".html")}">{esc(nk)}</a>' for nk, sl in us[:12])
            if len(us) > 12:
                who += f" 외 {len(us) - 12}명"
            lis = ""
            if n:
                lis = "".join(f'<li class="pro">{esc(x)}</li>' for x in n.get("pros", []))
                lis += "".join(f'<li class="con">{esc(x)}</li>' for x in n.get("cons", []))
            reason, alts = alternatives(prod, prod["name"], cat, usage)
            btn = buy_btn(prod, ctx, f"{track}/top{r}", "쿠팡 최저가 확인", "buy big")
            spec_div = f'<div class="specline">{esc(n["spec"])}</div>' if n and n.get("spec") else ""
            pc_ul = f'<ul class="pc">{lis}</ul>' if lis else ""
            cta = f'<div class="ctarow">{btn}</div>' if btn else ""
            cards += (f'<div class="item gcard" id="top{r}">{th}<div class="imain">'
                      f'<span class="cat">{r}위 · {len(us)}명</span>'
                      f'<span class="model">{esc(prod["name"])}</span></div>'
                      f'{spec_div}<div class="who">사용 선수: {who}</div>{pc_ul}{cta}'
                      f'{alt_html(reason, alts, ctx, track)}</div>')
        faq = [
            (f"{g['league']} 프로게이머가 가장 많이 쓰는 {topic(label)}?",
             f"{top[0]['name']}입니다. {label} 정보가 확인된 {n_known}명 중 {len(top[1])}명({top_pct}%)이 사용합니다."),
        ]
        if len(rows) > 2:
            faq.append((f"{label} 사용률 2·3위는?",
                        f"2위 {rows[1][0]['name']}({len(rows[1][1])}명), 3위 {rows[2][0]['name']}({len(rows[2][1])}명)입니다."))
        faq.append(("데이터는 언제 기준인가요?",
                    f"{game_verified(g)} 확인 기준이며, 로스터·장비 변경 시 갱신합니다. 출처는 각 선수 페이지에 표기합니다."))
        faq_html = "".join(f'<details class="faq"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
        body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › <a href="{gurl(g, 'rankings.html')}">장비 랭킹</a> › {label}</div>
<h1>{esc(title)}</h1>
<p class="sub">{g['league']} 선수 {n_known}명의 {label} 데이터를 집계했습니다.
1위는 <b>{esc(top[0]['name'])}</b>({len(top[1])}명, {top_pct}%). 프로 사용률 순서대로 스펙·장단점·구매 링크를 정리했습니다.</p>
{guide_nav(g, cat)}
{compare_table(g, usage, known, cat, label, ctx, track + "/table")}
<section><h2>순위별 상세</h2><div class="gear">{cards}</div></section>
<section><h2>자주 묻는 질문</h2>{faq_html}</section>"""
        desc = (f"{g['league']} 프로게이머 {n_known}명이 실제 쓰는 {label} 순위. 1위 {top[0]['name']} "
                f"({top_pct}%) 등 TOP10 스펙·장단점·쿠팡 최저가 링크.")
        jsonld = [
            {"@context": "https://schema.org", "@type": "ItemList", "name": title,
             "itemListElement": [{"@type": "ListItem", "position": r + 1, "name": p["name"]}
                                 for r, (p, _) in enumerate(rows[:10])]},
        ]
        out = gdir(g) / "guides" / f"{cat}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(g, title, desc, body, gurl(g, "guides", f"{cat}.html"), jsonld,
                            crumbs=[(f"{g['short']} 홈", gurl(g, "")), ("장비 랭킹", gurl(g, "rankings.html")),
                                    (label, gurl(g, "guides", f"{cat}.html"))]), encoding="utf-8")
        urls.append(gurl(g, "guides", f"{cat}.html"))
    return urls

def build_transfers(g, teams, tmeta):
    """스토브리그 페이지: 공식 이적·재계약·거취 미정 선수와 그 장비. 루머는 싣지 않는다."""
    data = (load_json("data/transfers.json") or {}).get(g["key"])
    if not data:
        return None
    by_nick = {p["nickname"].casefold(): p for ps in teams.values() for p in ps}
    ctx, season = f"{g['key']}_stove", data["season"]
    slug_page = f"stove-{season}.html"

    def gear_cell(p, key):
        e = (p.get("gear") or {}).get(key)
        if not (e and e.get("value")):
            return '<span class="na">확인 중</span>'
        prod = CATALOG.get(e["value"], {})
        btn = buy_btn(prod, ctx, f"{g['key']}/stove/{player_slug(p)}/{key}", "최저가", "buy sm") if prod else ""
        return f'<span>{esc(e["value"])}</span>{btn}'

    def rows(entries, show_from=False):
        out = ""
        for x in entries:
            p = by_nick.get(x["nickname"].casefold())
            if not p:
                continue
            team = tmeta.get(x.get("to") or x["team"], {}).get("kr", x.get("to") or x["team"])
            src = f' <a class="src" href="{esc(x["source"])}" rel="nofollow">근거</a>' if x.get("source") else ""
            status = (f'{esc(tmeta.get(x["from"], {}).get("kr", x["from"]))} → {esc(team)}' if show_from
                      else esc(x.get("status", "")))
            out += (f'<tr><td class="pn"><span><a href="{gurl(g, "players", player_slug(p) + ".html")}">'
                    f'<b>{esc(p["nickname"])}</b></a><small>{esc(p.get("name_kr", ""))} · {esc(team)}</small>'
                    f'<small>{status}{src}</small></span></td>'
                    f'<td class="gc">{gear_cell(p, "mouse")}</td><td class="gc">{gear_cell(p, "keyboard")}</td></tr>')
        return out

    def table(entries, show_from=False):
        r = rows(entries, show_from)
        return (f'<div class="cmp"><table><thead><tr><th>선수</th><th>마우스</th><th>키보드</th></tr></thead>'
                f'<tbody>{r}</tbody></table></div>') if r else ""

    moves = data.get("moves", [])
    moves_html = (table(moves, True) if moves else
                  f'<div class="tipbox">아직 공식 발표된 이적이 없습니다. FA 시장({data["fa_open"]}) 개시 후 '
                  '구단 공식 발표가 나오는 대로 반영합니다. 루머·보도 단계 소식은 싣지 않습니다.</div>')
    title = f"{season} {g['league']} 스토브리그 — FA·이적·재계약 선수 장비 총정리"
    desc = (f"{season} {g['league']} 스토브리그 FA 대상·재계약·이적 확정 선수와 각 선수가 쓰는 마우스·키보드. "
            f"구단 공식 발표 기준, {data['checked']} 확인.")
    body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › {season} 스토브리그</div>
<h1>{esc(title)}</h1>
<p class="sub">{data['checked']} 기준 계약 현황입니다. 선수 이름을 누르면 장비·감도 전체를 볼 수 있습니다.
이적이 확정되면 해당 선수의 팀 정보와 장비를 함께 갱신합니다.</p>
<section><h2>이적 확정</h2>{moves_html}</section>
<section><h2>FA 대상·거취 미정 ({len(data.get('pending', []))}명)</h2>{table(data.get('pending', []))}</section>
<section><h2>{season} 계약 확인 ({len(data.get('stay', []))}명)</h2>{table(data.get('stay', []))}</section>
<p class="note">계약 정보는 구단 공식 발표와 계약 공시 정리 자료를 기준으로 하며, 각 행의 '근거'에서 확인할 수 있습니다.</p>"""
    jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "dateModified": data["checked"]}
    out = gdir(g) / slug_page
    out.write_text(page(g, title, desc, body, gurl(g, slug_page), jsonld,
                        crumbs=[(f"{g['short']} 홈", gurl(g, "")), (f"{season} 스토브리그", gurl(g, slug_page))]),
                   encoding="utf-8")
    return gurl(g, slug_page)

def build_game(g):
    teams, tmeta = load_players(g)
    if not teams:
        print(f"  [{g['key']}] 로스터 데이터 없음 — 건너뜀")
        return []
    roles, sets = g["roles"], [tuple(s) for s in g["settings"]]
    cfg_order = g.get("team_order") or []
    order = [c for c in cfg_order if c in teams] + [c for c in teams if c not in cfg_order]
    pdir = gdir(g) / "players"
    pdir.mkdir(parents=True, exist_ok=True)
    written = set()
    urls = [gurl(g, "")]

    usage, known = compute_usage(teams)
    rank_url = build_rankings(g, teams, usage, known)
    if rank_url:
        urls.append(rank_url)
    urls += build_guides(g, teams, usage, known)
    stove = build_transfers(g, teams, tmeta)
    if stove:
        urls.append(stove)
    missing = [(p["nickname"], player_slug(p), tmeta.get(code, {}).get("kr", code))
               for code in order for p in teams.get(code, [])
               if not any(p.get("gear", {}).get(k) and p["gear"][k].get("value") for k, _ in GEAR_LABELS)]
    build_submit(g, missing)   # 검색 가치 낮음 → sitemap 제외
    build_thanks(g)

    for code, players in teams.items():
        tinfo = tmeta.get(code, {"kr": code, "color": "#888"})
        for p in players:
            nick, slug = p["nickname"], player_slug(p)
            kr = p.get("name_kr", "")
            role = roles.get(p["role"], p["role"]) or "선수"
            gear, setting = p.get("gear", {}), p.get("settings", {})
            has_any = any(gear.get(k) and gear[k].get("value") for k, _ in GEAR_LABELS)

            who = kr or nick
            title = f"{who}({nick}) 마우스·키보드·감도(DPI) — {tinfo['kr']} {role} 장비 | 프로셋업"
            named = [f"{lab} {gear[k]['value']}" for k, lab in GEAR_LABELS[:2]
                     if gear.get(k) and gear[k].get("value")]
            dpi = (setting.get("dpi") or {}).get("value") if isinstance(setting.get("dpi"), dict) else None
            desc = (f"{tinfo['kr']} {role} {who}({nick})의 " +
                    (", ".join(named) + (f", DPI {dpi}" if dpi else "") + " 등 " if named else "") +
                    "실사용 게이밍 장비와 인게임 감도를 출처와 함께 정리했습니다.")
            gear_html = "".join(item_html(key, label, gear.get(key), f"{g['key']}_player",
                                          f"{g['key']}/player/{slug}/{key}", usage,
                                          g.get("tournament_gear"))
                                for key, label in GEAR_LABELS)
            guide_links = " · ".join(f'<a href="{gurl(g, "guides", k + ".html")}">{g["league"]} {l} 순위</a>'
                                     for k, l in GUIDE_CATS[:3])
            set_html = ""
            for key, label in sets:
                e = setting.get(key)
                v = e.get("value") if isinstance(e, dict) else None
                set_html += (f'<div class="set"><div class="k">{label}</div>'
                             f'<div class="v{"" if v is not None else " unknown"}">'
                             f'{esc(v) if v is not None else "확인 중"}</div></div>')
            srcs = []
            for sec in (gear, setting):
                for e in sec.values():
                    if isinstance(e, dict) and e.get("source"):
                        s = e["source"].split(",")[0].strip()
                        if s not in srcs:
                            srcs.append(s)
            srcs_html = ("<div class='srcs'>출처: " +
                         " · ".join(f'<a href="{esc(s)}" rel="nofollow">{esc(s.split("//")[-1].split("/")[0])}</a>'
                                    for s in srcs) + "</div>") if srcs else ""
            note = p.get("note")
            note_html = f'<p class="note">{esc(note)}</p>' if note else ""
            empty_html = ("" if has_any else
                          '<p class="note">아직 공개된 장비 정보가 확인되지 않았습니다. '
                          f'<a href="{gurl(g, "submit.html")}" style="color:var(--gold)">알고 계시면 제보해주세요.</a></p>')
            jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": title,
                      "dateModified": raw_meta(g, full=True),
                      "about": {"@type": "Person", "name": who, "alternateName": nick,
                                "affiliation": {"@type": "SportsTeam", "name": tinfo["kr"]},
                                "jobTitle": f"프로게이머({role})"}}
            body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › {tinfo['kr']}</div>
<div class="phead"><h1>{esc(nick)}</h1><span class="kr">{esc(kr)}</span>
<span class="rolechip">{tinfo['kr']} · {role}</span></div>
{note_html}
<section><h2>장비</h2><div class="gear">{gear_html}</div>{empty_html}</section>
<section><h2>인게임 세팅</h2><div class="settings">{set_html}</div></section>
<p class="more">다른 프로들은 뭘 쓸까? {guide_links}</p>
{srcs_html}"""
            written.add(f"{slug}.html")
            (pdir / f"{slug}.html").write_text(
                page(g, title, desc, body, gurl(g, "players", f"{slug}.html"), jsonld,
                     noindex=not has_any,
                     crumbs=[(f"{g['short']} 홈", gurl(g, "")), (who, gurl(g, "players", f"{slug}.html"))]),
                encoding="utf-8")
            if has_any:   # 장비 0건 페이지는 얇은 콘텐츠 → noindex + sitemap 제외, 채워지면 자동 포함
                urls.append(gurl(g, "players", f"{slug}.html"))

    stale = [f for f in pdir.glob("*.html") if f.name not in written]
    for f in stale:
        f.unlink()
    if stale:
        print(f"  [{g['key']}] 이전 빌드 잔여 페이지 {len(stale)}개 삭제")

    # 게임 인덱스
    blocks, cur_region = "", None
    for code in order:
        if code not in teams:
            continue
        tinfo = tmeta[code]
        if tinfo.get("region") and tinfo["region"] != cur_region:
            cur_region = tinfo["region"]
            blocks += f'<h2 class="region">{esc(cur_region)}</h2>' 
        cells = ""
        for p in teams[code]:
            has_any = any(p.get("gear", {}).get(k) and p["gear"][k].get("value") for k, _ in GEAR_LABELS)
            extra = "" if has_any else '<div class="none">정보 수집 중</div>'
            cells += (f'<a class="pcell" href="{gurl(g, "players", player_slug(p) + ".html")}">'
                      f'<div class="nick">{esc(p["nickname"])}</div>'
                      f'<div class="meta">{esc(p.get("name_kr", ""))}{role_suffix(roles, p)}</div>{extra}</a>')
        blocks += (f'<div class="teamblock"><div class="teamname">'
                   f'<i style="background:{tinfo["color"]}"></i>{tinfo["kr"]}</div>'
                   f'<div class="pgrid">{cells}</div></div>')

    n_players = sum(len(v) for v in teams.values())
    stove_banner = (f'<a class="rankbanner" href="{stove}">🔥 2027 스토브리그 — FA·이적 선수 장비'
                    '<small>FA 대상·재계약 선수와 그들이 쓰는 마우스·키보드</small></a>') if stove else ""
    body = f"""<h1>{esc(g['headline'])}</h1>
<p class="sub">{esc(g['lede'])}</p>
<a class="rankbanner" href="{gurl(g, 'rankings.html')}">🏆 프로들이 가장 많이 쓰는 장비 랭킹
<small>{n_players}명 데이터 집계 — 키보드·마우스·헤드셋 사용률 TOP 비교표</small></a>
{guide_nav(g)}
{stove_banner}
<a class="rankbanner" href="{gurl(g, 'submit.html')}" style="background:linear-gradient(90deg,rgba(255,255,255,.07),transparent);border-color:rgba(255,255,255,.16)">📮 아는 장비 정보 제보하기
<small>근거 자료와 함께 보내주시면 확인 후 반영합니다</small></a>
{blocks}"""
    if g["path"]:
        jsonld = {"@context": "https://schema.org", "@type": "CollectionPage", "name": f"프로셋업 {g['short']}",
                  "url": gurl(g, ""), "isPartOf": {"@type": "WebSite", "url": BASE_URL + "/"}}
    else:
        jsonld = [{"@context": "https://schema.org", "@type": "WebSite", "name": "프로셋업",
                   "url": BASE_URL + "/", "inLanguage": "ko",
                   "description": "LCK·VCT 프로 선수 장비·세팅 정리 (비공식 팬 사이트)"},
                  {"@context": "https://schema.org", "@type": "Organization", "name": "프로셋업",
                   "url": BASE_URL + "/", "logo": BASE_URL + "/og.png"}]
    idx = gdir(g) / "index.html"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(page(g, f"프로셋업 {g['short']} — {g['league']} 프로 선수 장비·세팅 총정리",
                        f"{g['league']} 선수 {n_players}명이 실제 사용하는 게이밍 장비와 인게임 세팅을 팀별로 정리했습니다.",
                        body, gurl(g, ""), jsonld), encoding="utf-8")
    print(f"  [{g['key']}] 선수 {n_players}명 + 인덱스·랭킹·제보")
    return urls

def build():
    urls, lastmod = [], {}
    for key in GAMES_CFG["order"]:
        g = dict(GAMES_CFG["games"][key], key=key)
        gu = build_game(g)
        d = raw_meta(g, full=True)
        lastmod.update({u: d for u in gu if d})
        urls += gu
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"<url><loc>{u}</loc><lastmod>{lastmod.get(u, date.today().isoformat())}</lastmod></url>\n"
                for u in urls) +
        "</urlset>\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")
    print(f"총 URL {len(urls)}개 · sitemap 갱신")

if __name__ == "__main__":
    build()
