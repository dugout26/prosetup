#!/usr/bin/env python3
"""data/raw/<game>/*.json → 정적 사이트 생성 (게임별 섹션 + 랭킹 + 제보 + sitemap).

게임 추가: data/games.json 에 항목을 넣고 data/raw/<key>/ 에 로스터 JSON을 두면 된다.
LoL은 path="" 라서 기존 URL(사이트 루트)을 그대로 유지한다.
쿠팡 링크·이미지: data/products.json 카탈로그에서 표기(alias) 매칭으로 해석.
"""
import html
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE_URL = "https://dugout26.github.io/prosetup"
VERIFIED = "2026-08"
VERIFY_GOOGLE = "reLU6hFD0fFzI4ciTnfyEkadi_fsno6fJLTdosq1qTA"
VERIFY_NAVER = None

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
NOTES = (load_json("data/product_notes.json") or {"notes": {}})["notes"]

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
"""

def gurl(g, *parts):
    """게임 기준 URL. path가 ''이면 사이트 루트."""
    segs = [BASE_URL] + ([g["path"]] if g["path"] else []) + [p for p in parts if p]
    return "/".join(segs)

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

def page(g, title, desc, body, canonical, jsonld=None):
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
<div class="updated">데이터 확인 시점: {VERIFIED} · 매 시즌 업데이트</div>
{body}
<footer>
비공식 팬 사이트입니다. 선수·팀·리그와 무관하며, 장비 정보는 공개 자료를 교차 확인해 정리했습니다.
잘못된 정보·추가 정보 <a href="{gurl(g, 'submit.html')}" style="color:#7A8290;border-bottom:1px dotted #566070">제보하기</a><br>
이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
</footer>
</div>
</body>
</html>"""

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
    return (p["nickname"] + ("-" + p["slug_suffix"] if p.get("slug_suffix") else "")).lower()

def role_suffix(roles, p):
    r = roles.get(p["role"], p["role"])
    return f' · {r}' if r else ''

def item_html(cat_label, entry):
    if not entry or not entry.get("value"):
        return (f'<div class="item"><div class="imain"><span class="cat">{cat_label}</span>'
                f'<span class="model unknown">확인 중 — 공개 정보 수집 중</span></div></div>')
    conf = entry.get("confidence", "medium")
    prod = CATALOG.get(entry["value"], {})
    url = entry.get("coupang_url") or prod.get("coupang_url")
    buy = (f'<a class="buy" href="{esc(url)}" target="_blank" rel="nofollow sponsored">최저가 보기</a>'
           if url else "")
    thumb = (f'<img class="thumb" src="{esc(prod["image"])}" alt="{esc(entry["value"])}" '
             f'loading="lazy" width="62" height="62">' if prod.get("image") else "")
    note = NOTES.get(prod.get("name", ""))
    notes_html = ""
    if note:
        lis = "".join(f'<li class="pro">{esc(x)}</li>' for x in note.get("pros", []))
        lis += "".join(f'<li class="con">{esc(x)}</li>' for x in note.get("cons", []))
        notes_html = (f'<div class="pnotes"><div class="spec">{esc(note["spec"])}</div>'
                      f'<ul>{lis}</ul></div>')
    return (f'<div class="item">{thumb}<div class="imain">'
            f'<span class="cat">{cat_label}</span>'
            f'<span class="model">{esc(entry["value"])}</span>'
            f'<span class="conf {conf}">신뢰도 {CONF_KR.get(conf, conf)}</span></div>'
            f'{buy}{notes_html}</div>')

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

<section><h2>보내는 곳</h2>
<div class="tipbox">
이메일로 보내주세요. 사진은 첨부해도 되고 링크로 주셔도 됩니다.<br>
<a class="mailbtn" href="{mailto}">📮 제보 메일 쓰기 (양식 자동 입력)</a>
<p style="margin-top:14px; font-size:12px">
제보 시 개인정보(이름·연락처)는 적지 않으셔도 됩니다. 회신이 필요 없는 경우 메일 주소 외 정보는 저장하지 않습니다.
반영은 확인이 끝나는 대로 진행하며, 개별 회신은 어려울 수 있습니다.</p>
</div>
</section>"""
    title = f"장비 정보 제보 — 프로셋업 {g['short']}"
    desc = f"{g['league']} 프로 선수 장비 정보의 오류 수정·추가 제보를 받습니다. 근거 자료 기준과 검증 절차를 안내합니다."
    out = gdir(g) / "submit.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(g, title, desc, body, gurl(g, "submit.html")), encoding="utf-8")
    return gurl(g, "submit.html")

def build_rankings(g, teams):
    """해당 게임 선수 데이터 기준 카테고리별 사용 순위."""
    data = load_json("data/products.json")
    if not data:
        return None
    products = data["products"]
    owner = {a: i for i, prod in enumerate(products) for a in prod["aliases"]}
    users = {i: [] for i in range(len(products))}
    for players in teams.values():
        for p in players:
            for key, _ in GEAR_LABELS:
                e = p.get("gear", {}).get(key)
                if e and e.get("value") in owner:
                    users[owner[e["value"]]].append((p["nickname"], player_slug(p)))

    total_players = sum(len(v) for v in teams.values())
    sections, top_mouse = "", []
    for key, label in GEAR_LABELS:
        rows = sorted(((i, p) for i, p in enumerate(products) if p["category"] == key),
                      key=lambda ip: -len(set(users[ip[0]])))
        main = [(i, p) for i, p in rows if len(set(users[i])) >= 2]
        rest = [(i, p) for i, p in rows if len(set(users[i])) == 1]
        if key == "mouse":
            top_mouse = [p["name"] for _, p in main[:5]]
        rhtml = ""
        for rank, (i, prod) in enumerate(main, 1):
            names = sorted(set(users[i]))
            chips = " ".join(f'<a href="{gurl(g, "players", s + ".html")}">{esc(n)}</a>' for n, s in names)
            buy = (f'<a class="buy" href="{esc(prod["coupang_url"])}" target="_blank" rel="nofollow sponsored">최저가 보기</a>'
                   if prod.get("coupang_url") else "")
            th = (f'<img class="thumb" src="{esc(prod["image"])}" alt="{esc(prod["name"])}" '
                  f'loading="lazy" width="46" height="46">' if prod.get("image") else "")
            rhtml += (f'<div class="rankrow"><span class="rk{" top1" if rank == 1 else ""}">{rank}</span>{th}'
                      f'<span class="info"><span class="pname">{esc(prod["name"])}</span>'
                      f'<span class="users">{chips}</span></span>'
                      f'<span class="cnt">{len(names)}명</span>{buy}</div>')
        if rest:
            rhtml += ('<p class="etc1">1명 사용: ' +
                      " · ".join(esc(p["name"]) for _, p in rest) + "</p>")
        if rhtml:
            sections += f'<section><h2>가장 많이 쓰는 {label}</h2>{rhtml}</section>'

    title = f"{g['league']} 프로게이머가 가장 많이 쓰는 게이밍 장비 순위 (2026)"
    desc = (f"{g['league']} {total_players}명 선수 데이터 기준 — {g['name']} 프로들이 실제 사용하는 "
            "게이밍 마우스·키보드·모니터·헤드셋·마우스패드 순위와 구매 링크.")
    body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › 장비 랭킹</div>
<h1>{esc(g['league'])} 프로들이 가장 많이 쓰는 장비는?</h1>
<p class="sub">{total_players}명의 확인된 장비 데이터를 집계한 실사용 순위입니다.
같은 모델의 색상판은 별도 항목입니다.</p>
{sections}"""
    jsonld = {"@context": "https://schema.org", "@type": "ItemList", "name": title,
              "itemListElement": [{"@type": "ListItem", "position": r + 1, "name": n}
                                  for r, n in enumerate(top_mouse)]}
    out = gdir(g) / "rankings.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page(g, title, desc, body, gurl(g, "rankings.html"), jsonld), encoding="utf-8")
    return gurl(g, "rankings.html")

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

    rank_url = build_rankings(g, teams)
    if rank_url:
        urls.append(rank_url)
    missing = [(p["nickname"], player_slug(p), tmeta.get(code, {}).get("kr", code))
               for code in order for p in teams.get(code, [])
               if not any(p.get("gear", {}).get(k) and p["gear"][k].get("value") for k, _ in GEAR_LABELS)]
    urls.append(build_submit(g, missing))

    for code, players in teams.items():
        tinfo = tmeta.get(code, {"kr": code, "color": "#888"})
        for p in players:
            nick, slug = p["nickname"], player_slug(p)
            kr = p.get("name_kr", "")
            role = roles.get(p["role"], p["role"]) or "선수"
            gear, setting = p.get("gear", {}), p.get("settings", {})
            has_any = any(gear.get(k) and gear[k].get("value") for k, _ in GEAR_LABELS)

            title = f"{kr}({nick}) 장비·세팅 — {g['short']} 마우스·키보드·DPI | 프로셋업"
            desc = (f"{tinfo['kr']} {role} {kr}({nick})가 사용하는 게이밍 장비(마우스·키보드·모니터)와 "
                    f"인게임 세팅(DPI·감도)을 정리했습니다.")
            gear_html = "".join(item_html(label, gear.get(key)) for key, label in GEAR_LABELS)
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
            jsonld = {"@context": "https://schema.org", "@type": "ProfilePage",
                      "mainEntity": {"@type": "Person", "name": kr or nick, "alternateName": nick,
                                     "affiliation": tinfo["kr"], "jobTitle": f"프로게이머({role})"}}
            body = f"""<div class="crumb"><a href="{gurl(g, '')}">{esc(g['short'])} 홈</a> › {tinfo['kr']}</div>
<div class="phead"><h1>{esc(nick)}</h1><span class="kr">{esc(kr)}</span>
<span class="rolechip">{tinfo['kr']} · {role}</span></div>
{note_html}
<section><h2>장비</h2><div class="gear">{gear_html}</div>{empty_html}</section>
<section><h2>인게임 세팅</h2><div class="settings">{set_html}</div></section>
{srcs_html}"""
            written.add(f"{slug}.html")
            (pdir / f"{slug}.html").write_text(
                page(g, title, desc, body, gurl(g, "players", f"{slug}.html"), jsonld), encoding="utf-8")
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
            cells += (f'<a class="pcell" href="{gurl(g, "players", p["nickname"].lower() + ".html")}">'
                      f'<div class="nick">{esc(p["nickname"])}</div>'
                      f'<div class="meta">{esc(p.get("name_kr", ""))}{role_suffix(roles, p)}</div>{extra}</a>')
        blocks += (f'<div class="teamblock"><div class="teamname">'
                   f'<i style="background:{tinfo["color"]}"></i>{tinfo["kr"]}</div>'
                   f'<div class="pgrid">{cells}</div></div>')

    n_players = sum(len(v) for v in teams.values())
    body = f"""<h1>{esc(g['headline'])}</h1>
<p class="sub">{esc(g['lede'])}</p>
<a class="rankbanner" href="{gurl(g, 'rankings.html')}">🏆 프로들이 가장 많이 쓰는 장비 랭킹
<small>{n_players}명 데이터 집계 — 1위 제품은 뭘까?</small></a>
<a class="rankbanner" href="{gurl(g, 'submit.html')}" style="background:linear-gradient(90deg,rgba(255,255,255,.07),transparent);border-color:rgba(255,255,255,.16)">📮 아는 장비 정보 제보하기
<small>근거 자료와 함께 보내주시면 확인 후 반영합니다</small></a>
{blocks}"""
    jsonld = {"@context": "https://schema.org", "@type": "WebSite", "name": "프로셋업",
              "url": gurl(g, ""), "description": f"{g['league']} 프로 선수 장비·세팅 정리 (비공식 팬 사이트)"}
    idx = gdir(g) / "index.html"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text(page(g, f"프로셋업 {g['short']} — {g['league']} 프로 선수 장비·세팅 총정리",
                        f"{g['league']} 선수 {n_players}명이 실제 사용하는 게이밍 장비와 인게임 세팅을 팀별로 정리했습니다.",
                        body, gurl(g, ""), jsonld), encoding="utf-8")
    print(f"  [{g['key']}] 선수 {n_players}명 + 인덱스·랭킹·제보")
    return urls

def build():
    urls = []
    for key in GAMES_CFG["order"]:
        g = dict(GAMES_CFG["games"][key], key=key)
        urls += build_game(g)
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        "".join(f"<url><loc>{u}</loc><lastmod>{date.today()}</lastmod></url>\n" for u in urls) +
        "</urlset>\n", encoding="utf-8")
    (ROOT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {BASE_URL}/sitemap.xml\n", encoding="utf-8")
    print(f"총 URL {len(urls)}개 · sitemap 갱신")

if __name__ == "__main__":
    build()
