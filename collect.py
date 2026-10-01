"""구글 뉴스 RSS에서 급식 관련 기사를 모아 news.json으로 저장합니다.

- 외부 패키지 설치가 필요 없습니다 (파이썬 기본 기능만 사용).
- API 키도 필요 없고 비용이 들지 않습니다.
- 주제나 검색어를 바꾸고 싶으면 아래 TOPICS만 고치세요.
"""
import json
import re
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

DAYS = 14             # 최근 며칠 이내 기사만 가져올지
MAX_PER_TOPIC = 30    # 주제별 최대 기사 수
KST = timezone(timedelta(hours=9))


def fetch(query: str) -> list[dict]:
    q = urllib.parse.quote(f"{query} when:{DAYS}d")
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


def main() -> None:
    result = {"updated": datetime.now(KST).isoformat(), "topics": {}}
    for topic, queries in TOPICS.items():
        seen, merged = set(), []
        for q in queries:
            try:
                items = fetch(q)
            except Exception as e:  # 한 검색어가 실패해도 계속 진행
                print(f"[경고] '{q}' 수집 실패: {e}")
                continue
            for item in items:
                key = norm(item["title"])
                if key in seen:
                    continue
                seen.add(key)
                item["query"] = q
                merged.append(item)
        merged.sort(key=lambda x: x["date"], reverse=True)
        result["topics"][topic] = merged[:MAX_PER_TOPIC]
        print(f"{topic}: {len(result['topics'][topic])}건")

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
