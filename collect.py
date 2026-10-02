"""구글 뉴스 RSS에서 급식 관련 기사를 모아 news.json, history.json으로 저장합니다.

- 외부 패키지 설치가 필요 없습니다 (파이썬 기본 기능만 사용).
- API 키도 필요 없고 비용이 들지 않습니다.
- 주제나 검색어를 바꾸고 싶으면 아래 TOPICS만 고치세요.
- 제목에 KEYWORDS 중 하나가 없는 기사는 제외됩니다.
- 기업별 기사는 아래 COMPANIES 목록으로 수집하고, 월별로 누적해서 history.json에 기록합니다.
"""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

# 탭 이름: [검색어, ...]  (검색어는 자유롭게 추가/삭제 가능)
TOPICS = {
    "업계 동향": ["위탁급식", "단체급식", "위탁급식 시장", "구내식당 위탁운영"],
    "트렌드·급식문화": ["급식 트렌드", "구내식당 트렌드", "구내식당 신메뉴", "단체급식 트렌드", "구내식당 메뉴"],
    "식자재·원가": ["식자재 가격", "급식 식재료 물가", "급식 단가"],
    "입찰·제도": ["구내식당 입찰", "집단급식소 식품위생법", "급식 위탁 계약"],
}

# 제목에 이 단어 중 하나라도 있어야 목록에 남습니다 (엉뚱한 기사 제거용)
KEYWORDS = [
    "급식", "구내식당", "식단", "케이터링", "식자재", "식재료", "푸드서비스",
    "웰스토리", "아워홈", "프레시웨이", "그린푸드", "신세계푸드", "푸디스트",
]

# ---------------------------------------------------------------
# 기업별 뉴스 설정
# (그룹, 기업명, [제목에서 찾을 이름들], 동음이의어 주의 여부)
#  - 이름들: 기사 제목에 이 중 하나가 있어야 합니다. (띄어쓰기·대소문자 무시)
#  - 동음이의어 주의 True: 제목에 급식 관련 단어도 함께 있어야 통과합니다.
# ---------------------------------------------------------------
COMPANIES = [
    # 1. Big9
    ("Big9", "웰스토리", ["삼성웰스토리", "웰스토리"], False),
    ("Big9", "아워홈", ["아워홈"], False),
    ("Big9", "CJ프레시웨이", ["CJ프레시웨이", "씨제이프레시웨이"], False),
    ("Big9", "동원홈푸드", ["동원홈푸드"], False),
    ("Big9", "사조푸디스트", ["사조푸디스트", "푸디스트"], False),
    ("Big9", "고메드갤러리아", ["고메드갤러리아", "신세계푸드"], False),
    ("Big9", "아라마크", ["아라마크"], False),
    ("Big9", "풀무원푸드앤컬처", ["풀무원푸드앤컬처", "푸드앤컬처"], False),
    ("Big9", "현대그린푸드", ["현대그린푸드"], False),
    # 2. FD Big3
    ("FD Big3", "롯데웰푸드", ["롯데웰푸드"], False),
    ("FD Big3", "에스피씨지에프에스", ["SPC GFS", "SPC지에프에스", "에스피씨지에프에스"], False),
    ("FD Big3", "하림(네이처델리)", ["네이처델리"], False),
    # 3. 중견·중소
    ("중견·중소", "본푸드", ["본푸드", "본푸드서비스", "본우리집밥"], False),
    ("중견·중소", "진주랑", ["진주랑"], False),
    ("중견·중소", "아이비푸드", ["아이비푸드"], False),
    ("중견·중소", "LSC푸드", ["LSC푸드"], False),
    ("중견·중소", "가온에프앤에스", ["가온에프앤에스"], False),
    ("중견·중소", "한울에프앤에스", ["한울에프앤에스"], False),
    ("중견·중소", "신성푸드서비스", ["신성푸드서비스"], False),
    ("중견·중소", "후니드", ["후니드"], False),
    ("중견·중소", "삼주외식산업", ["삼주외식산업"], False),
    ("중견·중소", "브라운에프엔비", ["브라운에프엔비"], False),
    ("중견·중소", "명성에프엠씨", ["명성에프엠씨", "명성에프에스"], False),
    ("중견·중소", "정진홈푸드", ["정진홈푸드"], False),
    ("중견·중소", "제이에스지", ["제이에스지"], True),
    ("중견·중소", "휴먼푸드서비스", ["휴먼푸드서비스"], False),
    ("중견·중소", "웰리브에프앤에스", ["웰리브에프앤에스"], False),
    ("중견·중소", "제이제이케터링", ["제이제이케터링"], False),
    ("중견·중소", "대한에프에쓰에쓰", ["대한에프에쓰에쓰"], False),
    ("중견·중소", "비앤에스푸드", ["비앤에스푸드"], False),
    ("중견·중소", "델리에프에스", ["델리에프에스"], True),
    ("중견·중소", "가람푸드써비스", ["가람푸드써비스"], False),
    ("중견·중소", "웰스프레쉬", ["웰스프레쉬"], False),
    ("중견·중소", "LIG홈앤밀", ["LIG홈앤밀", "엘아이지홈앤밀"], False),
    ("중견·중소", "정우푸드", ["정우푸드"], True),
    ("중견·중소", "빌텍", ["빌텍"], True),
    ("중견·중소", "에이치앤포세카", ["에이치앤포세카", "H&포세카"], False),
    ("중견·중소", "한솔(양산)", ["한솔"], True),
    ("중견·중소", "다온푸드서비스", ["다온푸드서비스"], False),
    ("중견·중소", "진풍푸드서비스", ["진풍푸드서비스"], False),
    ("중견·중소", "초록푸드서비스", ["초록푸드서비스"], False),
    ("중견·중소", "금강웰빙푸드", ["금강웰빙푸드"], False),
    ("중견·중소", "미셸푸드", ["미셸푸드"], False),
    ("중견·중소", "지씨에스", ["지씨에스"], True),
    ("중견·중소", "온정에프앤비", ["온정에프앤비"], False),
]

# 동음이의어 주의 기업은 제목에 이 단어 중 하나가 함께 있어야 합니다
CATERING_KW = ["급식", "구내식당", "단체급식", "푸드서비스", "식자재", "케이터링", "위탁", "식단"]

DAYS = 14             # 최근 며칠 이내 기사만 가져올지 (주제별 뉴스)
MAX_PER_TOPIC = 30    # 주제별 최대 기사 수
COMPANY_DAYS = 30     # '기업별 뉴스' 탭에 보여줄 기간
MAX_PER_COMPANY = 10  # '기업별 뉴스' 탭에 보여줄 기업당 최대 기사 수
MAX_COMPANY_TOTAL = 200  # '기업별 뉴스' 탭 전체 최대 기사 수
COMPANY_TOPIC = "기업별 뉴스"

START_MONTH = "2026-10"   # 월별 기사 수 기록을 시작하는 달
RECENT_DAYS = 7           # 평소 수집 때 되돌아볼 기간 (하루 2번 수집이므로 넉넉하게)
HISTORY_FILE = "history.json"
KST = timezone(timedelta(hours=9))


def fetch(query: str, days: int = DAYS) -> list[dict]:
    q = urllib.parse.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as res:
        root = ET.fromstring(res.read())

    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        source = (it.findtext("source") or "").strip()
        pub = it.findtext("pubDate")
        if not title or not link or not pub:
            continue
        # 제목 끝의 " - 언론사" 부분 제거
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            dt = parsedate_to_datetime(pub).astimezone(KST)
        except Exception:
            continue
        items.append(
            {"title": title, "link": link, "source": source, "date": dt.isoformat()}
        )
    return items


def norm(title: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]", "", title)


def squash(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def relevant(title: str) -> bool:
    return any(k in title for k in KEYWORDS)


def match_company(title: str, aliases: list[str], strict: bool) -> bool:
    t = squash(title)
    if not any(squash(a) in t for a in aliases):
        return False
    if strict and not any(k in title for k in CATERING_KW):
        return False
    return True


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def prev_month_key(dt: datetime) -> str:
    y, m = dt.year, dt.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def load_history() -> dict:
    """history.json을 읽습니다. 파일이 깨졌으면 기록을 지우지 않도록 중단합니다."""
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            h = json.load(f)
    except FileNotFoundError:
        return {"start": START_MONTH, "companies": {}}
    except Exception as e:
        raise SystemExit(f"history.json을 읽지 못해 중단합니다 (기록 보호): {e}")
    if not isinstance(h, dict) or not isinstance(h.get("companies"), dict):
        raise SystemExit("history.json 형식이 달라 중단합니다 (기록 보호)")
    return h


def add_articles(months: dict, items: list[dict], cur: str, prev: str) -> int:
    """새 기사만 월별 기록에 더합니다. 이미 있는 기사(같은 제목)는 건너뜁니다."""
    seen_by_month: dict[str, set] = {}
    touched = set()
    added = 0
    for i in items:
        mk = i["date"][:7]
        # 시작 달 이전, 미래, 이미 마감된 달(지난달보다 이전)은 건드리지 않습니다
        if mk < START_MONTH or mk > cur or mk < prev:
            continue
        bucket = months.setdefault(mk, {"n": 0, "articles": []})
        if "articles" not in bucket:
            continue
        if mk not in seen_by_month:
            seen_by_month[mk] = {norm(a["title"]) for a in bucket["articles"]}
        k = norm(i["title"])
        if k in seen_by_month[mk]:
            continue
        seen_by_month[mk].add(k)
        bucket["articles"].append(
            {"title": i["title"], "link": i["link"], "source": i["source"], "date": i["date"]}
        )
        touched.add(mk)
        added += 1
    for mk in touched:
        b = months[mk]
        b["articles"].sort(key=lambda x: x["date"], reverse=True)
        b["n"] = len(b["articles"])
    return added


def collect_companies(history: dict, now: datetime) -> None:
    """기업별로 따로 검색해서 history에 새 기사만 누적합니다."""
    cur, prev = month_key(now), prev_month_key(now)
    start_date = datetime(int(START_MONTH[:4]), int(START_MONTH[5:7]), 1, tzinfo=KST)
    backfill_days = min(30, max(RECENT_DAYS, (now - start_date).days + 2))
    companies = history.setdefault("companies", {})

    for group, name, aliases, strict in COMPANIES:
        is_new = name not in companies
        entry = companies.setdefault(name, {"group": group, "months": {}})
        entry["group"] = group
        months = entry.setdefault("months", {})
        days = backfill_days if is_new else RECENT_DAYS

        terms = " OR ".join(f'"{a}"' for a in aliases)
        query = terms if len(aliases) == 1 else f"({terms})"
        if strict:
            query += " 급식"
        try:
            raw = fetch(query, days)
        except Exception as e:  # 한 기업이 실패해도 계속 진행 (다음 수집 때 자동으로 따라잡습니다)
            print(f"[경고] '{name}' 수집 실패: {e}")
            time.sleep(1)
            continue

        items = [i for i in raw if match_company(i["title"], aliases, strict)]
        added = add_articles(months, items, cur, prev)
        total = months.get(cur, {}).get("n", 0)
        print(f"{name}: +{added}건 (이번 달 누적 {total}건)")
        time.sleep(0.5)  # 구글에 부담을 주지 않도록 잠깐 쉽니다

    # 지난달보다 이전 달은 기사 목록을 지우고 건수만 남깁니다 (파일 크기 관리)
    for entry in companies.values():
        for mk, bucket in entry.get("months", {}).items():
            if mk < prev and "articles" in bucket:
                bucket["n"] = len(bucket["articles"])
                del bucket["articles"]


def build_company_feed(history: dict, now: datetime) -> list[dict]:
    """'기업별 뉴스' 탭용 목록을 history에서 만듭니다."""
    cur, prev = month_key(now), prev_month_key(now)
    cutoff = now - timedelta(days=COMPANY_DAYS)
    by_key: dict[str, dict] = {}
    for group, name, _, _ in COMPANIES:
        entry = history["companies"].get(name)
        if not entry:
            continue
        items = []
        for mk in (prev, cur):
            for a in entry.get("months", {}).get(mk, {}).get("articles", []):
                try:
                    if datetime.fromisoformat(a["date"]) >= cutoff:
                        items.append(a)
                except Exception:
                    continue
        items.sort(key=lambda x: x["date"], reverse=True)
        for a in items[:MAX_PER_COMPANY]:
            key = norm(a["title"])
            if key in by_key:
                saved = by_key[key]
                if name not in saved["companies"]:
                    saved["companies"].append(name)
                if group not in saved["groups"]:
                    saved["groups"].append(group)
                continue
            by_key[key] = {**a, "companies": [name], "groups": [group]}
    feed = sorted(by_key.values(), key=lambda x: x["date"], reverse=True)
    return feed[:MAX_COMPANY_TOTAL]


def main() -> None:
    now = datetime.now(KST)
    result = {"updated": now.isoformat(), "topics": {}}

    for topic, queries in TOPICS.items():
        seen, merged = set(), []
        for q in queries:
            try:
                items = fetch(q)
            except Exception as e:  # 한 검색어가 실패해도 계속 진행
                print(f"[경고] '{q}' 수집 실패: {e}")
                continue
            for item in items:
                if not relevant(item["title"]):
                    continue
                key = norm(item["title"])
                if key in seen:
                    continue
                seen.add(key)
                item["query"] = q
                merged.append(item)
        merged.sort(key=lambda x: x["date"], reverse=True)
        result["topics"][topic] = merged[:MAX_PER_TOPIC]
        print(f"{topic}: {len(result['topics'][topic])}건")

    # 기업별 기사: 월별 누적 기록(history.json) 갱신
    history = load_history()
    collect_companies(history, now)
    history["start"] = START_MONTH
    history["updated"] = now.isoformat()

    # '기업별 뉴스' 탭
    result["topics"][COMPANY_TOPIC] = build_company_feed(history, now)
    print(f"{COMPANY_TOPIC}: {len(result['topics'][COMPANY_TOPIC])}건")

    # 화면에서 그룹/기업 필터를 만들 때 쓸 목록
    groups: dict[str, list[str]] = {}
    for group, name, _, _ in COMPANIES:
        groups.setdefault(group, []).append(name)
    result["groups"] = groups

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
