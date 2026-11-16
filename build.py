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
# 제보 메일·FormSubmit 엔드포인트. 익명 문자열(https://formsubmit.co/<랜덤>)을 받으면 FORMSUBMIT_ENDPOINT에 넣는다.
# None이면 로그인 없는 폼을 숨기고 구글 폼 안내만 남긴다(운영 메일이 폼 action에 평문으로 노출되지 않게).
CONTACT_EMAIL = "dugout26.gm@gmail.com"
FORMSUBMIT_ENDPOINT = None
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
nav.gnav a.hot { color: #FFB4B4; border-color: rgba(255,107,107,.4); }
.tag { display: inline-block; font-size: 10.5px; font-weight: 800; padding: 1px 7px; border-radius: 999px; margin-right: 6px; }
.tag.off { color: #14171D; background: #FF6B6B; }
.tag.rumor { color: #FFE066; border: 1px solid rgba(255,224,102,.45); }
.tag.dead { color: #868E96; border: 1px solid #495057; text-decoration: line-through; }
tr.dead { opacity: .55; }
.cmp td.dt { font-size: 11.5px; color: var(--mut); white-space: nowrap; width: 70px; }
.cmp td small { display: block; }
.legend { font-size: 11.5px; color: var(--mut); margin: 6px 0 4px; line-height: 2; }
.h2s { font-size: 11px; color: var(--mut); font-weight: 500; margin-left: 6px; }
.slots { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
.slot { background: var(--card); border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; }
.slot.ok { border-color: rgba(81,207,102,.45); }
.slot.tbd { border-color: rgba(255,224,102,.35); }
.slot.empty { border-style: dashed; }
.slot .sh { display: flex; justify-content: space-between; font-weight: 900; font-size: 13px; margin-bottom: 6px; }
.st { font-size: 10.5px; padding: 1px 8px; border-radius: 999px; }
.st.ok { background: #51CF66; color: #0E1117; }
.st.tbd { color: #FFE066; border: 1px solid rgba(255,224,102,.5); }
.st.empty { color: #868E96; border: 1px dashed #495057; }
.sp { padding: 5px 0; border-top: 1px dashed var(--line); font-size: 13.5px; }
.sp:first-of-type { border-top: 0; }
.sp small { display: block; font-size: 11px; color: var(--mut); }
.sp.rum b::before { content: "🟡 "; } .sp.out b::before { content: "↗ "; } .sp.pend b { color: var(--mut); }
.sp.none { color: #566070; font-size: 12px; }
.tlink { margin-left: auto; font-size: 11.5px; color: var(--mut); font-weight: 700; }
.tlink:hover { color: var(--gold); }
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
.glink { color: inherit; border-bottom: 1px dotted var(--gold); }
.psum { background: var(--card); border: 1px solid var(--line); border-left: 3px solid var(--gold); border-radius: 12px; padding: 10px 14px; margin: 10px 0 14px; }
.psum ul { list-style: none; } .psum li { font-size: 13.5px; line-height: 1.7; }
.psum a { color: var(--tx); border-bottom: 1px dotted var(--gold); }
.fullset { background: linear-gradient(90deg, rgba(232,195,107,.12), rgba(232,195,107,.02)); border: 1px solid rgba(232,195,107,.35); border-radius: 14px; padding: 12px 14px; margin-bottom: 16px; }
.fstit { font-weight: 900; margin-bottom: 6px; } .fstit small { color: var(--mut); font-weight: 500; margin-left: 6px; font-size: 11.5px; }
.fsrow { display: flex; align-items: center; gap: 8px; padding: 5px 0; border-top: 1px dashed var(--line); font-size: 13px; }
.fsrow .cat { min-width: 64px; } .fsrow .fsn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
h3.lg { font-size: 13px; color: var(--mut); margin: 10px 0 6px; }
.pchips { display: flex; flex-wrap: wrap; gap: 6px; }
.pchip { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 5px 10px; font-size: 13px; }
.pchip small { display: block; font-size: 10.5px; color: var(--mut); }
.pchip:hover { border-color: var(--gold); }
.tool { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; margin: 12px 0 18px; }
.trow { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.trow label { flex: 1 1 140px; font-size: 12px; color: var(--mut); display: flex; flex-direction: column; gap: 4px; }
.trow input, .trow select { background: var(--bg); color: var(--tx); border: 1px solid var(--line); border-radius: 8px; padding: 9px 10px; font-size: 15px; }
.tout { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
.tout div { background: var(--bg); border-radius: 10px; padding: 10px; } .tout small { display: block; font-size: 11px; color: var(--mut); }
.tout b { font-size: 22px; color: var(--gold); }
.tipbox code { background: var(--bg); padding: 1px 6px; border-radius: 5px; }
.tag.comm { color: #FFA94D; border: 1px solid rgba(255,169,77,.5); }
tr.comm td { background: rgba(255,169,77,.04); }
.sp.comm b::before { content: "🟠 "; }
.seen { font-size: 10.5px; color: #7A8290; }
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
    tr = load_json("data/transfers.json") or {}
    for k in GAMES_CFG["order"]:
        if k in tr and not k.startswith("_"):
            g = GAMES_CFG["games"][k]
            cls = ' class="hot on"' if cur_key == "stove" else ' class="hot"'
            links += f'<a{cls} href="{gurl(dict(g, key=k), "stove-" + tr[k]["season"] + ".html")}">🔥 {esc(g["league"])} 이적시장</a>'
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
    if g.get("status_text"):
        return g["status_text"]
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
            f'<span class="model">{esc(name) if conf == "event" else gear_link(cat_key, name)}</span>{badge}'
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
    form_html = (f"""<div class="tipbox">
<b style="font-size:15px">방법 2 — 아래 폼 (로그인 없이)</b><br>
구글 계정이 없거나 로그인이 번거로우면 이쪽을 쓰세요. 사진은 링크로 남겨주시면 됩니다.
</div>
<div class="tipbox" style="padding-bottom:20px">
<form class="rform" action="{FORMSUBMIT_ENDPOINT}" method="POST">
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
""" if FORMSUBMIT_ENDPOINT else
                 '<div class="tipbox"><b style="font-size:15px">방법 2 — 로그인 없는 폼 (준비 중)</b><br>'
                 '로그인 없이 보내는 폼은 스팸 방지 설정을 마치는 대로 열립니다. 그 전까지는 구글 폼이나 아래 메일을 이용해 주세요.</div>')
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
{form_html}</section>

<section><h2>둘 다 안 될 때</h2>
<div class="tipbox">
아래 주소로 메일을 보내주셔도 됩니다.
<div class="mailrow"><code id="mailaddr">{CONTACT_EMAIL}</code>
<button class="copybtn" onclick="navigator.clipboard.writeText('{CONTACT_EMAIL}');this.textContent='복사됨';">주소 복사</button></div>
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

POS = [("top", "탑"), ("jungle", "정글"), ("mid", "미드"), ("adc", "원딜"), ("support", "서포터")]

def build_teams(g, teams, tmeta, usage):
    """팀 페이지: 다음 시즌 포지션별 칸(확정·거취 미정·루머·공석) + 현 로스터 장비."""
    data = (load_json("data/transfers.json") or {}).get(g["key"])
    if not data:
        return []
    season = data["season"]
    by_nick = {p["nickname"].casefold(): p for ps in teams.values() for p in ps}
    ctx = f"{g['key']}_team"

    def norm_role(r):
        return "adc" if r in ("bot", "adc") else r

    def role_of(x):
        if x.get("role"):
            return norm_role(x["role"])
        p = by_nick.get(x["nickname"].casefold())
        return norm_role((p or {}).get("role", ""))

    def pl_link(nick):
        p = by_nick.get(nick.casefold())
        return (f'<a href="{gurl(g, "players", player_slug(p) + ".html")}">{esc(nick)}</a>' if p else esc(nick))

    def tk(code):
        return tmeta.get(code, {}).get("kr", code)

    off = data.get("official", [])
    leaving = {x["nickname"].casefold() for x in off
               if x.get("from") and x.get("to") != x.get("from") and x.get("type") in ("이적", "방출", "은퇴")}
    urls = []
    order = [c for c in (g.get("team_order") or []) if c in teams]
    for code in order:
        tinfo = tmeta.get(code, {"kr": code, "color": "#888"})
        slots = {r: {"ok": [], "pending": [], "rumor": [], "comm": [], "out": []} for r, _ in POS}
        for x in data.get("stay", []):
            if x["team"] == code and x["nickname"].casefold() not in leaving and role_of(x) in slots:
                slots[role_of(x)]["ok"].append((x["nickname"], x.get("status", "계약 확인"), x.get("source")))
        for x in off:
            if x.get("to") == code and x.get("type") in ("이적", "영입", "재계약") and role_of(x) in slots:
                lab = "재계약" if x["type"] == "재계약" else f'{x["type"]} 오피셜'
                if not any(n.casefold() == x["nickname"].casefold() for n, _, _ in slots[role_of(x)]["ok"]):
                    slots[role_of(x)]["ok"].append((x["nickname"], lab, x.get("source")))
        for x in data.get("pending", []):
            if x["team"] == code and x["nickname"].casefold() not in leaving and role_of(x) in slots:
                slots[role_of(x)]["pending"].append((x["nickname"], x.get("status", "거취 미정"), x.get("source")))
        for x in data.get("reports", []):
            if x.get("status") != "보도" or role_of(x) not in slots:
                continue
            cm = x.get("tier") == "community"
            if cm and not (x.get("source") and x.get("outlet")):
                continue
            if x.get("to") == code:
                slots[role_of(x)]["comm" if cm else "rumor"].append(
                    (x["nickname"], f'{tk(x.get("from", ""))}에서 · {x.get("outlet", "")}', x.get("source")))
            elif x.get("from") == code:
                slots[role_of(x)]["out"].append((x["nickname"], f'{tk(x.get("to", ""))}행 {"썰" if cm else "보도"} · {x.get("outlet", "")}', x.get("source")))

        def chip(n, sub, src, cls):
            s_ = f' <a class="src" href="{esc(src)}" rel="nofollow">근거</a>' if src else ""
            return f'<div class="sp {cls}"><b>{pl_link(n)}</b><small>{esc(sub)}{s_}</small></div>'

        cards, n_ok = "", 0
        for r, rk in POS:
            sl = slots[r]
            if sl["ok"]:
                n_ok += 1
                state, scls = "확정", "ok"
            elif sl["pending"] or sl["rumor"] or sl["comm"]:
                state, scls = "미정", "tbd"
            else:
                state, scls = "공석", "empty"
            inner = "".join(chip(n, sub, src, "ok") for n, sub, src in sl["ok"])
            inner += "".join(chip(n, sub, src, "pend") for n, sub, src in sl["pending"])
            inner += "".join(chip(n, "이적설 — " + sub, src, "out") for n, sub, src in sl["out"])
            inner += "".join(chip(n, "보도 — " + sub, src, "rum") for n, sub, src in sl["rumor"])
            inner += "".join(chip(n, "썰(미확인) — " + sub, src, "comm") for n, sub, src in sl["comm"])
            if not inner:
                inner = '<div class="sp none">발표된 선수 없음</div>'
            cards += (f'<div class="slot {scls}"><div class="sh"><span>{rk}</span>'
                      f'<span class="st {scls}">{state}</span></div>{inner}</div>')

        rows = ""
        for p in teams[code]:
            gcells = ""
            for key, label in GEAR_LABELS[:4]:
                e = (p.get("gear") or {}).get(key)
                if e and e.get("value"):
                    prod = CATALOG.get(e["value"], {})
                    btn = buy_btn(prod, ctx, f"{g['key']}/team/{code.lower()}/{key}", "최저가", "buy sm") if prod else ""
                    gcells += f'<td class="gc"><span>{esc(e["value"])}</span>{btn}</td>'
                else:
                    gcells += '<td class="gc"><span class="na">확인 중</span></td>'
            rk = dict(POS).get(norm_role(p["role"]), p["role"])
            rows += (f'<tr><td class="pn"><span><a href="{gurl(g, "players", player_slug(p) + ".html")}"><b>{esc(p["nickname"])}</b></a>'
                     f'<small>{esc(p.get("name_kr", ""))} · {esc(rk)}</small></span></td>{gcells}</tr>')
        gear_tbl = (f'<div class="cmp"><table><thead><tr><th>선수</th><th>마우스</th><th>키보드</th><th>모니터</th>'
                    f'<th>헤드셋</th></tr></thead><tbody>{rows}</tbody></table></div>')
        name = tinfo["kr"]
        title = f"{name} {season} 로스터·선수 장비 — 확정·루머·공석 포지션별 정리"
        desc = (f"{name} {season} 시즌 로스터 현황(확정 {n_ok}/5)과 이적 루머, 선수별 마우스·키보드·모니터·헤드셋을 "
                f"포지션별로 정리했습니다. {data['checked']} 갱신.")
        body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › <a href="{gurl(g, 'stove-' + season + '.html')}">이적시장</a> › {esc(name)}</div>
<div class="phead"><h1>{esc(name)}</h1><span class="rolechip" style="color:{tinfo['color']}">{season} 로스터 확정 {n_ok}/5</span></div>
<p class="sub">{data['checked']} 기준. <b>확정</b>=계약 확인·오피셜, <b>미정</b>=기존 선수 거취 미정 또는 보도·썰만 있음, <b>공석</b>=발표된 선수 없음.</p>
<section><h2>{season} 포지션별 로스터</h2><div class="slots">{cards}</div></section>
<section><h2>현 로스터 장비</h2>{gear_tbl}</section>
<p class="note">🟡 보도는 매체 기사, 🟠 썰은 커뮤니티·방송 발언(미확인)이며 구단 공식 발표 전까지 확정이 아닙니다.
다른 팀: {" · ".join(f'<a href="{gurl(g, "teams", c.lower() + ".html")}">{esc(tmeta.get(c, {}).get("kr", c))}</a>' for c in order if c != code)}</p>"""
        jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "dateModified": data["checked"],
                  "about": {"@type": "SportsTeam", "name": name}}
        out = gdir(g) / "teams" / f"{code.lower()}.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page(g, title, desc, body, gurl(g, "teams", f"{code.lower()}.html"), jsonld,
                            crumbs=[(f"{g['short']} 홈", gurl(g, "")), ("이적시장", gurl(g, f"stove-{season}.html")),
                                    (name, gurl(g, "teams", f"{code.lower()}.html"))]), encoding="utf-8")
        urls.append(gurl(g, "teams", f"{code.lower()}.html"))
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

    def tname(code):
        return tmeta.get(code, {}).get("kr", code)

    def who_cell(x):
        p = by_nick.get(x["nickname"].casefold())
        name = (f'<a href="{gurl(g, "players", player_slug(p) + ".html")}"><b>{esc(x["nickname"])}</b></a>'
                if p else f'<b>{esc(x["nickname"])}</b>')
        kr = x.get("name_kr") or (p or {}).get("name_kr", "")
        mouse = ((p or {}).get("gear") or {}).get("mouse") or {}
        gear = f'<small>마우스: {esc(mouse["value"])}</small>' if mouse.get("value") else ""
        return f'<span>{name}<small>{esc(kr)}</small>{gear}</span>'

    off = sorted(data.get("official", []), key=lambda x: x.get("date", ""), reverse=True)
    off_rows = "".join(
        f'<tr><td class="dt">{esc(x.get("date", ""))}</td><td class="pn">{who_cell(x)}</td>'
        f'<td><span class="tag off">{esc(x["type"])}</span><small>'
        f'{esc(tname(x["from"])) + " → " if x.get("from") else ""}{esc(tname(x.get("to") or x.get("team", "")))}'
        f'{" · " + esc(x["detail"]) if x.get("detail") else ""}</small>'
        f'<a class="src" href="{esc(x["source"])}" rel="nofollow">출처</a></td></tr>' for x in off)
    off_html = (f'<div class="cmp"><table><tbody>{off_rows}</tbody></table></div>' if off_rows else
                '<div class="tipbox">아직 공식 발표가 없습니다.</div>')
    reps = sorted(data.get("reports", []), key=lambda x: x.get("seen_at") or x.get("date", ""), reverse=True)

    def rep_rows(lst):
        out = ""
        for x in lst:
            st = x.get("status", "보도")
            comm = x.get("tier") == "community"
            cls = {"오피셜 확정": "off", "무산": "dead"}.get(st, "comm" if comm else "rumor")
            lab = st if st != "보도" else ("썰·미확인" if comm else x.get("grade", "보도"))
            seen = x.get("seen_at") or x.get("date", "")
            out += (f'<tr class="{cls}"><td class="dt">{esc(x.get("date", ""))}</td><td class="pn">{who_cell(x)}</td>'
                    f'<td><span class="tag {cls}">{esc(lab)}</span>'
                    f'<small>{esc(tname(x.get("from", "")))} → <b>{esc(tname(x.get("to", "")))}</b></small>'
                    f'<small>{esc(x.get("note", ""))}</small>'
                    f'<a class="src" href="{esc(x["source"])}" rel="nofollow">{esc(x.get("outlet", "출처"))}</a>'
                    f' <span class="seen">확인 {esc(seen)}</span></td></tr>')
        return out
    media = [x for x in reps if x.get("tier") != "community"]
    comm = [x for x in reps if x.get("tier") == "community" and x.get("source") and x.get("outlet")]
    rep_rows_m, rep_rows_c = rep_rows(media), rep_rows(comm)
    rep_html = (f'<div class="cmp"><table><tbody>{rep_rows_m}</tbody></table></div>' if rep_rows_m else
                '<div class="tipbox">수집된 보도가 없습니다.</div>')
    comm_html = (f'<div class="cmp"><table><tbody>{rep_rows_c}</tbody></table></div>' if rep_rows_c else
                 '<div class="tipbox">수집된 썰이 아직 없습니다. FA 개장(11/17) 이후 유력 썰쟁이·커뮤니티 글을 출처와 함께 모읍니다.</div>')
    sec_off = f'<section><h2>🔴 오피셜</h2>{off_html}</section>'
    sec_rep = (f'<section><h2>🟡 매체 보도 <small class="h2s">기자·매체 기사 · 오피셜이 뜨면 옮깁니다</small></h2>'
               f'{rep_html}</section>'
               f'<section><h2>🟠 커뮤니티·썰 <small class="h2s">미확인 · 작성자·원문 링크·확인 시각 표기</small></h2>'
               f'{comm_html}</section>')
    # 이적·영입 오피셜이 나오기 전엔 루머가 더 궁금한 소식이라 위로
    has_move = any(x.get("type") != "재계약" for x in off)
    sections_top = sec_off + sec_rep if has_move else sec_rep + sec_off
    title = f"{season} {g['league']} 이적시장 — FA 명단 · 스토브리그 · 로스터 총정리 (오피셜·루머·선수 장비)"
    updated = data.get("checked_at") or data["checked"]
    fa_at = data["fa_open"] + (" " + data["fa_open_time"] if data.get("fa_open_time") else "")
    coaches = data.get("coaches") or []
    coach_rows = "".join(
        f'<tr><td class="pn"><span><b>{esc(c["nickname"])}</b><small>{esc(c.get("name_kr", ""))} · {esc(c.get("role", ""))}</small></span></td>'
        f'<td>{esc(tname(c.get("team", "")))}</td><td><small>{esc(c.get("status", ""))}</small>'
        f'<a class="src" href="{esc(c["source"])}" rel="nofollow">출처</a></td></tr>'
        for c in coaches if c.get("source"))
    sec_coach = (f'<section><h2>감독·코치 계약 현황 <small class="h2s">출처 확인분만</small></h2>'
                 f'<div class="cmp"><table><thead><tr><th>이름</th><th>팀</th><th>계약</th></tr></thead>'
                 f'<tbody>{coach_rows}</tbody></table></div></section>') if coach_rows else ""
    ups = sorted(data.get("updates") or [], key=lambda u: u.get("at", ""), reverse=True)[:5]
    log_html = ('<details class="tipbox"><summary>업데이트 기록 (최근 ' + str(len(ups)) + '건)</summary><ul>' +
                "".join(f'<li><b>{esc(u["at"])}</b> — {esc(u["text"])}</li>' for u in ups) +
                '</ul></details>') if ups else ""
    desc = (f"{season} {g['league']} 스토브리그 오피셜(이적·재계약)과 언론·소식통 루머, FA 대상 선수와 각 선수의 "
            f"마우스·키보드를 한 번에. {updated} 갱신.")
    body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › {season} 이적시장</div>
<h1>{esc(title)}</h1>
<p class="sub">최근 갱신 {updated} · FA 시장 {fa_at} 개시. 선수 이름을 누르면 장비·감도 전체를 볼 수 있습니다.</p>
<div class="legend"><span class="tag off">오피셜</span> 구단·리그 공식 발표
<span class="tag rumor">소식통·보도</span> 언론 보도 단계(확정 아님)
<span class="tag comm">썰·미확인</span> 썰쟁이·커뮤니티 글(사실 확인 안 됨) <span class="tag dead">무산</span></div>
{log_html}
{sections_top}
<section><h2>팀별 로스터 현황</h2><nav class="gnav sm">{"".join(f'<a href="{gurl(g, "teams", c.lower() + ".html")}">{esc(tmeta.get(c, {}).get("kr", c))}</a>' for c in (g.get("team_order") or []) if c in teams)}</nav></section>
<section><h2>FA 대상·거취 미정 ({len(data.get('pending', []))}명)</h2>{table(data.get('pending', []))}</section>
<section><h2>{season} 계약 확인 ({len(data.get('stay', []))}명)</h2>{table(data.get('stay', []))}</section>
{sec_coach}
<p class="note">🟡 보도는 매체명이 확인된 기사, 🟠 썰은 작성자·원문 링크가 있는 커뮤니티·방송 발언만 싣습니다.
둘 다 해당 출처의 주장이며 구단 공식 발표 전까지 확정이 아닙니다. 사생활·비방성 글은 싣지 않습니다. 삭제 요청은 제보하기로 보내주세요.</p>"""
    jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "dateModified": data["checked"]}  # ISO 날짜 유지
    out = gdir(g) / slug_page
    out.write_text(page(g, title, desc, body, gurl(g, slug_page), jsonld,
                        crumbs=[(f"{g['short']} 홈", gurl(g, "")), (f"{season} 이적시장", gurl(g, slug_page))]),
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
    team_urls = build_teams(g, teams, tmeta, usage)
    urls += team_urls
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
                                     for k, l in GUIDE_CATS[:3]) + f' · <a href="{BASE_URL}/tools/sens.html">감도 변환기</a>'
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
            summary_html, faq_html = player_summary(g, p, teams)
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
            tcrumb = (f'<a href="{gurl(g, "teams", code.lower() + ".html")}">{tinfo["kr"]}</a>'
                      if (load_json("data/transfers.json") or {}).get(g["key"]) else tinfo["kr"])
            body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › {tcrumb}</div>
<div class="phead"><h1>{esc(nick)}</h1><span class="kr">{esc(kr)}</span>
<span class="rolechip">{tinfo['kr']} · {role}</span></div>
{note_html}
{summary_html}
{fullset_html(g, p, slug)}
<section><h2>장비</h2><div class="gear">{gear_html}</div>{empty_html}</section>
<section><h2>인게임 세팅</h2><div class="settings">{set_html}</div></section>
{faq_html}
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
        tlink = (f' <a class="tlink" href="{gurl(g, "teams", code.lower() + ".html")}">로스터·루머 →</a>'
                 if team_urls else "")
        blocks += (f'<div class="teamblock"><div class="teamname">'
                   f'<i style="background:{tinfo["color"]}"></i>{tinfo["kr"]}{tlink}</div>'
                   f'<div class="pgrid">{cells}</div></div>')

    n_players = sum(len(v) for v in teams.values())
    stove_banner = (f'<a class="rankbanner" href="{stove}">🔥 이적시장 — 오피셜·루머 실시간 정리'
                    '<small>FA 대상·이적설 선수와 그들이 쓰는 마우스·키보드</small></a>') if stove else ""
    body = f"""<h1>{esc(g['headline'])}</h1>
<p class="sub">{esc(g['lede'])}</p>
<a class="rankbanner" href="{gurl(g, 'rankings.html')}">🏆 프로들이 가장 많이 쓰는 장비 랭킹
<small>{n_players}명 데이터 집계 — 키보드·마우스·헤드셋 사용률 TOP 비교표</small></a>
{guide_nav(g)}
{tools_nav()}
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


# ───────────── 제품 페이지 · 도구 · 가이드 (2026-11-16 슬랙 2번 확장) ─────────────
COLOR_RE = re.compile(r"\s*[\(\[][^\)\]]*[\)\]]\s*$")
GEAR_MIN = 3            # 게임 합산 이 인원 이상 쓰는 제품만 페이지 생성 (얇은 페이지 방지)
GEAR = {}               # (cat, base) -> {"base", "cat", "variants": {name: count}, "users": [...]}
GEAR_URL = {}           # (cat, base) -> url

def model_base(name):
    """색상·에디션 괄호 제거 → 같은 모델로 합산 (예: Superlight 2 (Magenta) → Superlight 2)."""
    return COLOR_RE.sub("", name or "").strip()

def prod_name(value):
    pr = CATALOG.get(value)
    return pr["name"] if pr else value

def gear_key(cat, value):
    return (cat, model_base(prod_name(value)))

def gear_link(cat, value, text=None, cls="glink"):
    u = GEAR_URL.get(gear_key(cat, value))
    t = esc(text if text is not None else value)
    return f'<a class="{cls}" href="{u}">{t}</a>' if u else t

def site_g(key, status):
    """게임에 속하지 않는 사이트 공용 페이지용 g (루트 경로, LoL 탭 설정 재사용)."""
    base = GAMES_CFG["games"][GAMES_CFG["order"][0]]
    return dict(base, key=key, path="", status_text=status)

def all_games():
    return [dict(GAMES_CFG["games"][k], key=k) for k in GAMES_CFG["order"]]

def collect_gear():
    """모든 게임 선수의 장비를 모델 단위로 집계 (제품 페이지·선수 요약·도구가 공유)."""
    GEAR.clear(); GEAR_URL.clear()
    for g in all_games():
        teams, tmeta = load_players(g)
        for code, ps in teams.items():
            for p in ps:
                for cat, _ in GEAR_LABELS:
                    e = (p.get("gear") or {}).get(cat)
                    if not (e and e.get("value")):
                        continue
                    k = gear_key(cat, e["value"])
                    d = GEAR.setdefault(k, {"base": k[1], "cat": cat, "variants": {}, "users": []})
                    n = prod_name(e["value"])
                    d["variants"][n] = d["variants"].get(n, 0) + 1
                    d["users"].append({"game": g["key"], "league": g["league"], "nick": p["nickname"],
                                       "slug": player_slug(p), "team": tmeta.get(code, {}).get("kr", code),
                                       "role": g["roles"].get(p["role"], p["role"]),
                                       "url": gurl(g, "players", player_slug(p) + ".html")})
    seen = set()
    for k, d in GEAR.items():
        if len(d["users"]) >= GEAR_MIN:
            s = slugify(d["base"])
            if s in seen:
                s = f"{s}-{k[0]}"
            seen.add(s)
            d["slug"] = s
            GEAR_URL[k] = f"{BASE_URL}/gear/{s}.html"

def gear_main_prod(d):
    """대표 제품: 쿠팡 링크 있는 변형 중 사용자 많은 것 → 없으면 최다 사용 변형."""
    vs = sorted(d["variants"].items(), key=lambda kv: -kv[1])
    for n, _ in vs:
        if buy_url(BY_NAME.get(n, {})):
            return BY_NAME[n]
    return BY_NAME.get(vs[0][0], {"name": vs[0][0], "category": d["cat"]})

def cat_label(cat):
    return dict(GEAR_LABELS).get(cat, cat)

def build_gear_pages():
    out_dir = ROOT / "gear"
    out_dir.mkdir(exist_ok=True)
    g = site_g("gear", f"LCK·VCT 선수 장비 합산 · 장비 데이터 확인: {max(game_verified(x) for x in all_games())}")
    ctx = "gear_page"
    urls, written = [], set()
    pages = sorted([d for k, d in GEAR.items() if k in GEAR_URL], key=lambda d: -len(d["users"]))
    by_cat = {}
    for d in pages:
        by_cat.setdefault(d["cat"], []).append(d)
    usage_like = {c: [(gear_main_prod(d), d["users"]) for d in lst] for c, lst in by_cat.items()}
    for d in pages:
        cat, lab, n = d["cat"], cat_label(d["cat"]), len(d["users"])
        rank = by_cat[cat].index(d) + 1
        prod = gear_main_prod(d)
        note = note_for(prod, d["base"]) or note_for({"name": d["base"]})
        track = f"gear/page/{d['slug']}/{cat}"
        leagues = {}
        for u in d["users"]:
            leagues.setdefault(u["league"], []).append(u)
        lg_txt = " · ".join(f"{lg} {len(us)}명" for lg, us in leagues.items())
        th = (f'<img class="thumb" src="{esc(prod["image"])}" alt="{esc(d["base"])}" loading="lazy" width="62" height="62">'
              if prod.get("image") else "")
        spec = f'<div class="specline">{esc(note["spec"])}</div>' if note and note.get("spec") else ""
        btn = buy_btn(prod, ctx, track, "쿠팡 최저가 확인", "buy big")
        cta = (f'<div class="ctarow">{btn}<span class="ctahint">가격·로켓배송 여부는 쿠팡에서 실시간 확인</span></div>'
               if btn else "")
        reason, alts = alternatives(prod, d["base"], cat, usage_like)
        pc = ""
        if note and (note.get("pros") or note.get("cons")):
            lis = "".join(f'<li class="pro">{esc(x)}</li>' for x in note.get("pros", []))
            lis += "".join(f'<li class="con">{esc(x)}</li>' for x in note.get("cons", []))
            pc = f'<ul class="pc">{lis}</ul>'
        card = (f'<div class="item gcard">{th}<div class="imain"><span class="cat">{lab} 사용률 {rank}위</span>'
                f'<span class="model">{esc(d["base"])}</span></div>{spec}{pc}{cta}'
                f'{alt_html(reason, alts, ctx, track)}</div>')
        var_html = ""
        if len(d["variants"]) > 1:
            rows = ""
            for vn, c in sorted(d["variants"].items(), key=lambda kv: -kv[1]):
                vp = BY_NAME.get(vn, {})
                rows += (f'<tr><td>{esc(vn)}</td><td class="num">{c}명</td>'
                         f'<td>{buy_btn(vp, ctx, track + "/variant", "최저가", "buy sm") if vp else ""}</td></tr>')
            var_html = (f'<section><h2>색상·에디션별</h2><div class="cmp"><table><tbody>{rows}</tbody></table></div>'
                        f'<p class="note">색상·에디션만 다른 제품은 같은 모델로 합산했습니다.</p></section>')
        who = ""
        for lg, us in leagues.items():
            chips = "".join(f'<a class="pchip" href="{u["url"]}"><b>{esc(u["nick"])}</b><small>{esc(u["team"])}'
                            f'{" · " + esc(u["role"]) if u["role"] else ""}</small></a>'
                            for u in sorted(us, key=lambda u: u["nick"].casefold()))
            who += f'<h3 class="lg">{esc(lg)} {len(us)}명</h3><div class="pchips">{chips}</div>'
        others = [x for x in by_cat[cat] if x is not d][:6]
        oth = " · ".join(f'<a href="{GEAR_URL[(x["cat"], x["base"])]}">{esc(x["base"])}</a> ({len(x["users"])}명)'
                         for x in others)
        title = f"{d['base']} 쓰는 프로게이머 {n}명 — {' · '.join(leagues)} 선수 목록 ({SEASON})"
        desc = (f"{d['base']}를 실제로 쓰는 프로 선수 {n}명({lg_txt}). {lab} 사용률 {rank}위. "
                f"{note['spec'] + '. ' if note and note.get('spec') else ''}선수별 페이지와 쿠팡 최저가 링크.")
        body = f"""<div class="crumb"><a href="{BASE_URL}/">홈</a> › <a href="{BASE_URL}/gear/">프로 사용 장비</a> › {esc(lab)}</div>
<h1>{esc(d['base'])} 쓰는 프로게이머</h1>
<p class="sub">데이터가 있는 프로 선수 중 <b>{n}명</b>이 사용합니다({esc(lg_txt)}). 프로 {lab} 사용률 {rank}위.</p>
<section><div class="gear">{card}</div></section>
<section><h2>사용 선수 {n}명</h2>{who}</section>
{var_html}
<section><h2>다른 인기 {esc(lab)}</h2><p class="more">{oth}</p></section>
<p class="note">선수별 출처와 확인 시점은 각 선수 페이지에 있습니다. 대회 지급 장비는 집계에서 뺐습니다.</p>"""
        jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": title,
                  "about": {"@type": "Thing", "name": d["base"]}}
        fn = f"{d['slug']}.html"
        written.add(fn)
        (out_dir / fn).write_text(page(g, title, desc, body, GEAR_URL[(cat, d["base"])], jsonld,
                                       crumbs=[("홈", BASE_URL + "/"), ("프로 사용 장비", BASE_URL + "/gear/"),
                                               (d["base"], GEAR_URL[(cat, d["base"])])]), encoding="utf-8")
        urls.append(GEAR_URL[(cat, d["base"])])
    for f in out_dir.glob("*.html"):
        if f.name not in written and f.name != "index.html":
            f.unlink()
    # 인덱스
    secs = ""
    for cat, lab in GEAR_LABELS:
        lst = by_cat.get(cat, [])
        if not lst:
            continue
        rows = "".join(f'<tr><td class="rk">{i}</td><td><a href="{GEAR_URL[(cat, x["base"])]}"><b>{esc(x["base"])}</b></a></td>'
                       f'<td class="num">{len(x["users"])}명</td></tr>' for i, x in enumerate(lst, 1))
        secs += (f'<section><h2>{lab} ({len(lst)}종)</h2><div class="cmp"><table><tbody>{rows}</tbody></table></div></section>')
    title = f"프로게이머가 쓰는 장비 {len(pages)}종 — 제품별 사용 선수 목록 ({SEASON})"
    desc = f"LCK·VCT 프로 선수 {GEAR_MIN}명 이상이 쓰는 마우스·키보드·모니터·헤드셋·마우스패드 {len(pages)}종과 각 제품을 쓰는 선수 목록."
    body = f"""<div class="crumb"><a href="{BASE_URL}/">홈</a> › 프로 사용 장비</div>
<h1>{esc(title)}</h1>
<p class="sub">제품 이름을 누르면 그 제품을 쓰는 선수 전체와 최저가 링크가 나옵니다. 색상만 다른 제품은 합산했습니다.</p>
{tools_nav()}
{secs}"""
    (out_dir / "index.html").write_text(page(g, title, desc, body, BASE_URL + "/gear/",
                                             crumbs=[("홈", BASE_URL + "/"), ("프로 사용 장비", BASE_URL + "/gear/")]),
                                        encoding="utf-8")
    print(f"  [gear] 제품 페이지 {len(pages)}개")
    return [BASE_URL + "/gear/"] + urls

def tools_nav(cur=None):
    items = [("gear", BASE_URL + "/gear/", "제품별 사용 선수"), ("sens", BASE_URL + "/tools/sens.html", "감도 변환기"),
             ("accel", BASE_URL + "/guides/mouse-acceleration.html", "마우스 가속 끄기"),
             ("monitor", BASE_URL + "/guides/lol-monitor.html", "LoL 모니터 가이드"),
             ("adc", BASE_URL + "/guides/adc-mouse.html", "원딜 마우스")]
    return '<nav class="gnav sm">' + "".join(
        f'<a{" class=on" if k == cur else ""} href="{u}">{l}</a>' for k, u, l in items) + '</nav>'

def num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None

def sval(p, key):
    e = (p.get("settings") or {}).get(key)
    return num(e.get("value")) if isinstance(e, dict) else None

def player_summary(g, p, teams):
    """선수 페이지 상단 요약 3줄 + 같은 장비 선수 + 보이는 FAQ (데이터에서만 생성)."""
    gear = p.get("gear") or {}
    who = p.get("name_kr") or p["nickname"]
    lines, faq = [], []
    m = (gear.get("mouse") or {}).get("value")
    if m:
        d = GEAR.get(gear_key("mouse", m))
        same = [u for u in (d or {}).get("users", []) if u["slug"] != player_slug(p) or u["game"] != g["key"]]
        lg = [u for u in same if u["game"] == g["key"]]
        ml = gear_link("mouse", m, model_base(prod_name(m)))
        if lg:
            lines.append(f'마우스는 {ml} — {g["league"]}에서 {len(lg)}명, 전체 프로 {len(same)}명이 같은 모델을 씁니다.')
        elif same:
            lines.append(f'마우스는 {ml} — {g["league"]}에선 혼자 쓰고, 다른 리그 프로 {len(same)}명이 같은 모델을 씁니다.')
        else:
            lines.append(f'마우스는 {ml} — 데이터가 있는 프로 중 이 모델을 쓰는 건 이 선수뿐입니다.')
        if lg:
            ch = " · ".join(f'<a href="{u["url"]}">{esc(u["nick"])}</a>' for u in lg[:6])
            lines.append(f"같은 마우스: {ch}{' 외 ' + str(len(lg) - 6) + '명' if len(lg) > 6 else ''}")
        faq.append((f"{who} 마우스 뭐 써요?", f"{prod_name(m)}입니다. 출처는 아래 장비 카드와 페이지 하단에 있습니다."))
    dpi = sval(p, "dpi")
    if g["key"] == "valorant":
        ed = sval(p, "edpi") or (dpi * sval(p, "in_game_sens") if dpi and sval(p, "in_game_sens") else None)
        pool = [x for ps in teams.values() for x in ps]
        eds = [v for v in ((sval(x, "edpi") or ((sval(x, "dpi") or 0) * (sval(x, "in_game_sens") or 0)) or None)
                           for x in pool) if v]
        if ed and eds:
            avg = sum(eds) / len(eds)
            diff = round(100 * (ed - avg) / avg)
            cm = 2.54 * 360 / (ed * 0.07)
            lines.append(f"eDPI {ed:g} (360° 회전 {cm:.1f}cm) — VCT 평균 {avg:.0f}보다 "
                         f"{'높은' if diff > 0 else '낮은'} 감도({diff:+d}%). "
                         f'<a href="{BASE_URL}/tools/sens.html">내 감도와 비교 →</a>')
            faq.append((f"{who} 감도(eDPI)는?", f"DPI {dpi:g} · 인게임 감도 {sval(p, 'in_game_sens'):g} · eDPI {ed:g}입니다."
                        if dpi and sval(p, "in_game_sens") else f"eDPI {ed:g}입니다."))
    elif dpi:
        core = set(g.get("team_order") or teams)   # 해외 팀(INTL.json)은 리그 평균에서 제외
        teams = {c: ps for c, ps in teams.items() if c in core}
        same_role = [sval(x, "dpi") for ps in teams.values() for x in ps if ({"bot": "adc"}.get(x["role"], x["role"]) == {"bot": "adc"}.get(p["role"], p["role"])) and sval(x, "dpi")]
        allr = [sval(x, "dpi") for ps in teams.values() for x in ps if sval(x, "dpi")]
        base = same_role if len(same_role) >= 3 else allr
        role = g["roles"].get(p["role"], "선수") if len(same_role) >= 3 else "전체"
        if base:
            avg = sum(base) / len(base)
            lines.append(f"DPI {dpi:g} — {g['league']} {role} 평균 {avg:.0f}({len(base)}명 기준)"
                         f"{'보다 높음' if dpi > avg * 1.05 else '보다 낮음' if dpi < avg * 0.95 else '과 비슷'}.")
        faq.append((f"{who} DPI는?", f"{dpi:g}입니다." + (f" 인게임 마우스 속도는 {sval(p, 'in_game_sens'):g}." if sval(p, "in_game_sens") is not None else "")))
    k = (gear.get("keyboard") or {}).get("value")
    if k:
        faq.append((f"{who} 키보드는?", f"{prod_name(k)}입니다."))
    faq_html = "".join(f'<details class="faq"><summary>{esc(q)}</summary><p>{esc(a)}</p></details>' for q, a in faq)
    return ((f'<div class="psum"><ul>{"".join(f"<li>{l}</li>" for l in lines[:3])}</ul></div>' if lines else ""),
            (f'<section><h2>자주 찾는 질문</h2>{faq_html}</section>' if faq_html else ""))

def fullset_html(g, p, slug):
    """선수 풀세트 묶음 CTA — 링크 있는 장비만 한 상자에."""
    items = []
    for cat, lab in GEAR_LABELS:
        e = (p.get("gear") or {}).get(cat)
        if not (e and e.get("value")):
            continue
        prod = CATALOG.get(e["value"], {})
        if e.get("coupang_url"):
            prod = dict(prod, coupang_url=e["coupang_url"])
        b = buy_btn(prod, f"{g['key']}_player", f"{g['key']}/fullset/{slug}/{cat}", "최저가", "buy sm") if prod else ""
        if b:
            items.append(f'<div class="fsrow"><span class="cat">{lab}</span><span class="fsn">{esc(e["value"])}</span>{b}</div>')
    if len(items) < 2:
        return ""
    return (f'<div class="fullset"><div class="fstit">🛒 {esc(p["nickname"])} 풀세트 따라 하기 '
            f'<small>{len(items)}개 제품 · 쿠팡 최저가</small></div>{"".join(items)}</div>')

SENS_GAMES = [("valorant", "발로란트", 0.07), ("cs2", "CS2", 0.022), ("ow2", "오버워치 2", 0.0066),
              ("apex", "에이펙스 레전드", 0.022)]

def build_sens_tool():
    g = site_g("tools", "감도 계산은 브라우저에서만 처리 · 프로 데이터: VCT 선수 eDPI")
    vg = next((x for x in all_games() if x["key"] == "valorant"), None)
    pros = []
    if vg:
        teams, tmeta = load_players(vg)
        for code, ps in teams.items():
            for p in ps:
                dpi, s = sval(p, "dpi"), sval(p, "in_game_sens")
                ed = sval(p, "edpi") or (dpi * s if dpi and s else None)
                if not ed:
                    continue
                m = ((p.get("gear") or {}).get("mouse") or {}).get("value")
                mp = CATALOG.get(m, {}) if m else {}
                url = buy_url(mp)
                pros.append({"n": p["nickname"], "t": tmeta.get(code, {}).get("kr", code), "e": round(ed, 1),
                             "d": dpi, "s": s, "m": m or "", "u": gurl(vg, "players", player_slug(p) + ".html"),
                             "b": with_subid(url, "valorant/tool/mouse") if url else "",
                             "g": GEAR_URL.get(gear_key("mouse", m), "") if m else ""})
    opts = "".join(f'<option value="{y}">{esc(n)}</option>' for _, n, y in SENS_GAMES)
    yaws = json.dumps({k: y for k, _, y in SENS_GAMES})
    body = f"""<div class="crumb"><a href="{BASE_URL}/">홈</a> › 감도 변환기</div>
<h1>감도 변환기 · eDPI 계산기 — 발로란트·CS2·오버워치 2·에이펙스</h1>
<p class="sub">게임을 바꿔도 손에 익은 감도를 그대로. 같은 cm/360(마우스를 움직인 거리당 회전량)이 되도록 변환하고,
eDPI가 비슷한 VCT 프로 5명과 그들의 마우스를 보여줍니다. 계산은 브라우저 안에서만 합니다.</p>
{tools_nav("sens")}
<div class="tool">
<div class="trow"><label>지금 게임<select id="fg">{opts}</select></label>
<label>인게임 감도<input id="fs" type="number" step="0.001" value="0.4" inputmode="decimal"></label>
<label>DPI<input id="fd" type="number" step="50" value="800" inputmode="numeric"></label></div>
<div class="trow"><label>바꿀 게임<select id="tg">{opts}</select></label>
<label>새 DPI<input id="td" type="number" step="50" value="800" inputmode="numeric"></label></div>
<div class="tout" id="out"></div>
</div>
<section><h2>나와 eDPI가 비슷한 VCT 프로</h2><div class="cmp"><table><thead><tr><th>선수</th><th>eDPI</th><th>마우스</th></tr></thead>
<tbody id="near"></tbody></table></div><p class="note">발로란트 기준 eDPI(DPI × 인게임 감도)로 비교합니다. 다른 게임 감도는 발로란트 값으로 환산해 비교합니다.</p></section>
<section><h2>계산 방법</h2><div class="tipbox">
<ul><li>cm/360 = 2.54 × 360 ÷ (DPI × 감도 × 게임 계수)</li>
<li>게임 계수(1감도당 회전 각도): {" · ".join(f"{esc(n)} {y}" for _, n, y in SENS_GAMES)}</li>
<li>새 감도 = (지금 DPI × 지금 감도 × 지금 계수) ÷ (새 DPI × 새 계수)</li>
<li>LoL은 3D 시점 감도가 없어 변환 대상이 아닙니다. 배틀그라운드는 시야각·배율별 감도가 따로라 아직 넣지 않았습니다.</li></ul></div></section>
<script>
const P={json.dumps(pros, ensure_ascii=False)};
const $=id=>document.getElementById(id);
$("tg").selectedIndex=1;
function esc(s){{return String(s).replace(/[&<>"]/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}})[c])}}
function run(){{
 const fy=+$("fg").value, ty=+$("tg").value, fs=+$("fs").value, fd=+$("fd").value, td=+$("td").value||fd;
 if(!(fy&&ty&&fs>0&&fd>0)){{$("out").innerHTML="감도와 DPI를 입력하세요.";return}}
 const deg=fd*fs*fy, cm=2.54*360/deg, ns=deg/(td*ty), ev=deg/0.07;
 $("out").innerHTML=`<div><small>바꿀 게임 감도</small><b>${{ns.toFixed(3)}}</b></div><div><small>cm/360</small><b>${{cm.toFixed(1)}}cm</b></div>`+
  `<div><small>eDPI (지금 게임)</small><b>${{(fd*fs).toFixed(0)}}</b></div><div><small>발로란트 환산 eDPI</small><b>${{ev.toFixed(0)}}</b></div>`;
 const near=P.slice().sort((a,b)=>Math.abs(a.e-ev)-Math.abs(b.e-ev)).slice(0,5);
 $("near").innerHTML=near.map(p=>`<tr><td class="pn"><span><a href="${{p.u}}"><b>${{esc(p.n)}}</b></a><small>${{esc(p.t)}}</small></span></td>`+
  `<td class="num">${{p.e}}</td><td class="gc"><span>${{p.g?`<a href="${{p.g}}">${{esc(p.m)}}</a>`:esc(p.m||"확인 중")}}</span>`+
  (p.b?`<a class="buy sm" href="${{p.b}}" target="_blank" rel="nofollow sponsored noopener" data-goatcounter-click="coupang/valorant/tool/mouse">최저가 →</a>`:"")+`</td></tr>`).join("");
}}
["fg","tg","fs","fd","td"].forEach(i=>$(i).addEventListener("input",run));run();
</script>"""
    title = "감도 변환기 · eDPI 계산기 — 발로란트 ↔ CS2 ↔ 오버워치 2 감도 변환"
    desc = "발로란트·CS2·오버워치 2·에이펙스 감도를 cm/360 기준으로 변환하고 eDPI를 계산합니다. eDPI가 비슷한 VCT 프로 5명의 마우스도 함께."
    out = ROOT / "tools" / "sens.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page(g, title, desc, body, BASE_URL + "/tools/sens.html",
                        {"@context": "https://schema.org", "@type": "WebApplication", "name": "감도 변환기",
                         "applicationCategory": "UtilitiesApplication", "operatingSystem": "Web",
                         "offers": {"@type": "Offer", "price": "0", "priceCurrency": "KRW"}},
                        crumbs=[("홈", BASE_URL + "/"), ("감도 변환기", BASE_URL + "/tools/sens.html")]),
                   encoding="utf-8")
    return [BASE_URL + "/tools/sens.html"]

def build_extra_guides():
    """마우스 가속 끄기 · LoL 모니터 · 원딜 마우스. 수치는 전부 데이터에서."""
    lol = next((x for x in all_games() if x["key"] == "lol"), None)
    if not lol:
        return []
    teams, tmeta = load_players(lol)
    core = set(lol.get("team_order") or teams)   # 가이드는 LCK 팀만 (해외 팀 제외)
    players = [p for c, ps in teams.items() if c in core for p in ps]
    g = dict(lol, status_text=game_status(lol))
    urls = []
    gdir_ = ROOT / "guides"
    gdir_.mkdir(exist_ok=True)

    def write(fn, title, desc, body, label):
        u = f"{BASE_URL}/guides/{fn}"
        (gdir_ / fn).write_text(page(g, title, desc, body, u, {"@context": "https://schema.org", "@type": "Article",
                                                                "headline": title, "dateModified": raw_meta(lol, full=True)},
                                     crumbs=[("홈", BASE_URL + "/"), (label, u)]), encoding="utf-8")
        urls.append(u)

    # 1) 마우스 가속
    dpis = sorted(sval(p, "dpi") for p in players if sval(p, "dpi"))
    med = dpis[len(dpis) // 2] if dpis else None
    dist = {}
    for v in dpis:
        dist[int(v)] = dist.get(int(v), 0) + 1
    top_d = sorted(dist.items(), key=lambda kv: -kv[1])[:4]
    dline = (f"LCK 선수 중 DPI가 확인된 {len(dpis)}명의 중앙값은 <b>{med:g}</b>이고, 많이 쓰는 값은 "
             + ", ".join(f"{d}({c}명)" for d, c in top_d) + "입니다.") if dpis else ""
    body = f"""<div class="crumb"><a href="{BASE_URL}/">홈</a> › 마우스 가속 끄기</div>
<h1>윈도우 마우스 가속 끄는 법 — '포인터 정확도 향상' 해제 (프로 세팅 기준)</h1>
<p class="sub">마우스 가속은 손을 빨리 움직일수록 커서가 더 멀리 가게 만드는 기능입니다. 같은 거리를 움직여도 속도에 따라
결과가 달라져 에임·클릭 위치가 일정하지 않게 됩니다. 프로 세팅 가이드는 대부분 이 기능을 끄는 것에서 시작합니다.</p>
{tools_nav("accel")}
<section><h2>윈도우 11</h2><div class="tipbox"><ol>
<li>시작 → <b>설정</b> → <b>Bluetooth 및 장치</b> → <b>마우스</b></li>
<li>아래쪽 <b>추가 마우스 설정</b> 클릭 → '마우스 속성' 창이 열림</li>
<li><b>포인터 옵션</b> 탭 → <b>포인터 정확도 향상</b> 체크 해제 → 확인</li></ol></div></section>
<section><h2>윈도우 10</h2><div class="tipbox"><ol>
<li>시작 → <b>설정</b> → <b>장치</b> → <b>마우스</b> → <b>추가 마우스 옵션</b></li>
<li><b>포인터 옵션</b> 탭 → <b>포인터 정확도 향상</b> 체크 해제 → 확인</li></ol>
<p>빠르게 여는 법: <b>Win + R</b> → <code>main.cpl</code> 입력 → 엔터.</p></div></section>
<section><h2>같이 확인할 것</h2><div class="tipbox"><ul>
<li><b>포인터 속도</b>는 기본값(가운데, 11칸 중 6번째)이 1:1입니다. 감도는 마우스 DPI와 게임 안에서 조절하는 편이 계산하기 쉽습니다.</li>
<li><b>LoL</b>은 윈도우 커서를 그대로 쓰는 게임이라 윈도우 가속·포인터 속도가 체감에 바로 영향을 줍니다. {dline}</li>
<li>마우스 제조사 소프트웨어(G HUB, Synapse 등)에 가속·각도 보정 옵션이 따로 있으면 그것도 끕니다.</li>
<li>설정을 바꾼 뒤에는 <a href="{BASE_URL}/tools/sens.html">감도 변환기</a>로 cm/360을 확인해 두면 장비를 바꿔도 같은 감도를 맞출 수 있습니다.</li></ul></div></section>"""
    write("mouse-acceleration.html", "윈도우 마우스 가속 끄는 법 — 포인터 정확도 향상 해제 (윈도우 11·10)",
          "윈도우 11·10에서 마우스 가속(포인터 정확도 향상)을 끄는 방법과 LCK 프로 DPI 분포. 게임 감도를 일정하게 맞추는 첫 단계.",
          body, "마우스 가속 끄기")

    # 2) LoL 모니터
    mons = {}
    for p in players:
        v = ((p.get("gear") or {}).get("monitor") or {}).get("value")
        if v:
            k = model_base(prod_name(v))
            mons.setdefault(k, []).append(p)
    rows, inch, hz = "", {}, {}
    for k, ps in sorted(mons.items(), key=lambda kv: -len(kv[1])):
        full = prod_name(ps[0]["gear"]["monitor"]["value"])
        n = note_for({"name": k}) or note_for(BY_NAME.get(full, {}), full)
        spec = (n or {}).get("spec", "")
        mi = re.search(r"([\d.]+)인치", spec); mh = re.search(r"(\d+)Hz", spec) or re.search(r"(\d+)Hz", k)
        if mi:
            inch[mi.group(1)] = inch.get(mi.group(1), 0) + len(ps)
        if mh:
            hz[mh.group(1)] = hz.get(mh.group(1), 0) + len(ps)
        prod = BY_NAME.get(k) or BY_NAME.get(full) or CATALOG.get(k, {})
        btn = buy_btn(prod, "lol_guide", "lol/guide/monitor-lol", "최저가", "buy sm") if prod else ""
        who = ", ".join(f'<a href="{gurl(lol, "players", player_slug(p) + ".html")}">{esc(p["nickname"])}</a>' for p in ps)
        rows += (f'<tr><td class="pn"><span><b>{gear_link("monitor", k)}</b><small>{esc(spec) or "스펙 미표기"}</small>'
                 f'<small>{who}</small></span></td><td class="num">{len(ps)}명</td><td>{btn}</td></tr>')
    n_mon = sum(len(v) for v in mons.values())
    tg = (lol.get("tournament_gear") or {}).get("monitor")
    def dist_txt(d, unit):
        return " · ".join(f"{k}{unit} {v}명" for k, v in sorted(d.items(), key=lambda kv: -kv[1])) or "-"
    body = f"""<div class="crumb"><a href="{BASE_URL}/">홈</a> › LoL 모니터 가이드</div>
<h1>LoL 프로게이머 모니터 — 인치·주사율(Hz)·거리 가이드</h1>
<p class="sub">LCK 선수 중 개인 모니터가 확인된 <b>{n_mon}명</b>의 모델을 집계했습니다.
크기: {esc(dist_txt(inch, "인치"))}. 주사율: {esc(dist_txt(hz, "Hz"))} (스펙이 표기된 모델만).</p>
{tools_nav("monitor")}
<section><h2>LCK 선수 개인 모니터</h2><div class="cmp"><table><thead><tr><th>모델 · 사용 선수</th><th>인원</th><th></th></tr></thead>
<tbody>{rows}</tbody></table></div>
{f'<p class="note">LCK 경기장에서는 {esc(tg)}가 지급됩니다. 위 표는 선수 개인(연습·방송) 모니터 기준입니다.</p>' if tg else ''}</section>
<section><h2>고를 때 기준</h2><div class="tipbox"><ul>
<li><b>크기</b>: 프로들은 24~25인치급이 대부분입니다. 미니맵·스킬 아이콘까지 시선 이동 없이 한눈에 들어오는 크기라서입니다.</li>
<li><b>주사율</b>: LoL은 FPS만큼 빠른 화면 전환이 적지만, 높은 주사율이 커서·스킬샷 움직임을 부드럽게 보여줍니다. 그래픽카드가 그 프레임을 낼 수 있어야 의미가 있습니다.</li>
<li><b>거리</b>: 일반적으로 화면 전체가 눈을 크게 돌리지 않고 보이는 거리(24~25인치 기준 대략 팔 길이, 50~70cm)를 권장합니다. 화면 위쪽 끝이 눈높이와 같거나 조금 아래가 되게 맞추면 목 부담이 적습니다.</li></ul></div></section>
<p class="more">더 보기: <a href="{gurl(lol, 'guides', 'monitor.html')}">LCK 모니터 사용률 순위</a> · <a href="{BASE_URL}/gear/">제품별 사용 선수</a></p>"""
    write("lol-monitor.html", "LoL 프로게이머 모니터 — LCK 선수 인치·주사율(Hz) 정리 + 거리 가이드",
          f"LCK 선수 {n_mon}명의 개인 모니터 모델·크기·주사율 집계와 LoL 모니터 고르는 기준(크기·Hz·거리).", body, "LoL 모니터 가이드")

    # 3) 원딜 마우스
    adcs = [p for p in players if p["role"] in ("adc", "bot")]
    rows, cnt = "", {}
    for p in adcs:
        tm = tmeta.get(p["_team"], {}).get("kr", p["_team"])
        e = (p.get("gear") or {}).get("mouse") or {}
        v = e.get("value")
        if v:
            k = model_base(prod_name(v)); cnt[k] = cnt.get(k, 0) + 1
        prod = CATALOG.get(v, {}) if v else {}
        n = note_for(prod, v or "") if v else None
        btn = buy_btn(prod, "lol_guide", f"lol/guide/adc-mouse/{player_slug(p)}/mouse", "최저가", "buy sm") if prod else ""
        rows += (f'<tr><td class="pn"><span><a href="{gurl(lol, "players", player_slug(p) + ".html")}"><b>{esc(p["nickname"])}</b></a>'
                 f'<small>{esc(p.get("name_kr", ""))} · {esc(tm)}</small></span></td>'
                 f'<td class="gc"><span>{gear_link("mouse", v) if v else "<span class=na>확인 중</span>"}</span>'
                 f'{"<small>" + esc(n["spec"]) + "</small>" if n and n.get("spec") else ""}{btn}</td>'
                 f'<td class="num">{sval(p, "dpi") and format(sval(p, "dpi"), "g") or "-"}</td></tr>')
    known_n = sum(cnt.values())
    top = sorted(cnt.items(), key=lambda kv: -kv[1])
    brand = {}
    for k, c in cnt.items():
        brand[k.split()[0]] = brand.get(k.split()[0], 0) + c
    btxt = ", ".join(f"{b} {c}명" for b, c in sorted(brand.items(), key=lambda kv: -kv[1]))
    body = f"""<div class="crumb"><a href="{BASE_URL}/">홈</a> › 원딜 마우스</div>
<h1>원딜 마우스 추천 — LCK 원딜 프로 {len(adcs)}명이 쓰는 마우스</h1>
<p class="sub">LCK 원딜 {len(adcs)}명 중 마우스가 확인된 {known_n}명 기준. 브랜드: {esc(btxt) or "-"}.
{"가장 많이 쓰는 모델은 <b>" + gear_link("mouse", top[0][0]) + f"</b>({top[0][1]}명)." if top else ""}</p>
{tools_nav("adc")}
<section><h2>LCK 원딜 마우스 · DPI</h2><div class="cmp"><table><thead><tr><th>선수</th><th>마우스</th><th>DPI</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>
<section><h2>원딜이 마우스를 고르는 기준</h2><div class="tipbox"><ul>
<li>원딜은 무빙과 평타를 번갈아 찍는 클릭이 많은 포지션이라, 오래 써도 손이 덜 피곤한 <b>가벼운 무선 마우스</b>가 많습니다.</li>
<li>위 표처럼 오래 써서 손에 익은 구형 모델을 계속 쓰는 선수도 많습니다. 스펙보다 손 크기·그립에 맞는지가 먼저입니다.</li>
<li>DPI는 선수마다 400~2,000 이상으로 넓게 갈립니다. 윈도우 가속은 끄고 쓰는 게 기본입니다 → <a href="{BASE_URL}/guides/mouse-acceleration.html">마우스 가속 끄는 법</a></li></ul></div></section>
<p class="more">전체 포지션: <a href="{gurl(lol, 'guides', 'mouse.html')}">LCK 마우스 순위</a></p>"""
    write("adc-mouse.html", "원딜 마우스 추천 — LCK 원딜 프로게이머가 쓰는 마우스·DPI 정리",
          f"LCK 원딜 {len(adcs)}명이 실제로 쓰는 마우스와 DPI. 가장 많이 쓰는 모델과 쿠팡 최저가 링크.", body, "원딜 마우스")
    return urls

def build():
    urls, lastmod = [], {}
    collect_gear()
    for key in GAMES_CFG["order"]:
        g = dict(GAMES_CFG["games"][key], key=key)
        gu = build_game(g)
        d = raw_meta(g, full=True)
        lastmod.update({u: d for u in gu if d})
        urls += gu
    site_d = max(filter(None, (raw_meta(x, full=True) for x in all_games())), default=None)
    for u in build_gear_pages() + build_sens_tool() + build_extra_guides():
        urls.append(u)
        if site_d:
            lastmod[u] = site_d
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
