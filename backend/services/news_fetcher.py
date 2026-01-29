from __future__ import annotations

from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re
from html import unescape

# add newsapi
from newsapi import NewsApiClient
NEWSAPI_KEY = "eadac95e4f8a43c8a5fc604319a24e51"

# add jisuapi
import requests
JISU_API_KEY = "ed6215e5750335e2"

# add newsdataio
from newsdataapi import NewsDataApiClient
NEWSDATAIO_API_KEY = "pub_4df7e6c89500414aa17065de1a370ae6"

import feedparser

# 尽量用目前还能访问的 RSS 源
SINA_FINANCE_RSS = "https://rss.sina.com.cn/finance/index.xml"
YAHOO_FINANCE_RSS = "https://www.yahoo.com/news/rss/finance"
INVESTING_RSS = "https://www.investing.com/rss/news_25.rss"  # Investing.com 财经快讯


def _clean_html(text: str) -> str:
    """去掉 RSS 中的 HTML 标签，保留纯文本。"""
    if not text:
        return ""
    text = unescape(text)
    # 常见的 <br> 换行
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    # 删除其它标签
    text = re.sub(r"<.*?>", "", text)
    # 压缩多余空白
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n\s+", "\n", text)
    return text.strip()


def _parse_published_to_utc(published: Any) -> datetime | None:
    """将各种来源的发布时间解析为 UTC aware datetime，无法解析则返回 None。"""
    if not published:
        return None

    # 如果已经是 datetime
    if isinstance(published, datetime):
        dt = published
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    s = str(published).strip()
    if not s:
        return None

    # 处理 ISO 8601 结尾的 Z
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"

    # 优先尝试 ISO
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # 再尝试 RFC2822 / RSS 常见时间格式
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_feed(url: str, source_name: str, limit: int = 30) -> List[Dict[str, Any]]:
    """通用 RSS 解析，带异常保护，并尽量抽取摘要。"""
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []

    items: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)  # 最近 7 天

    for entry in feed.entries[: limit * 2]:
        title = getattr(entry, "title", "").strip()

        # ✅ 尽量从多个字段抽取正文摘要
        raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        # 有些源把内容放在 content[0].value 里
        if not raw_summary and getattr(entry, "content", None):
            try:
                raw_summary = entry.content[0].value
            except Exception:
                raw_summary = ""

        summary = _clean_html(raw_summary)

        # 如果连 summary 也抽不出来，就用标题兜底，避免前端完全空白
        if not summary:
            summary = title

        link = getattr(entry, "link", "").strip()

        published = getattr(entry, "published", "") or getattr(entry, "updated", "")
        published_dt = None

        # feedparser 提供的结构化时间（通常没有 tzinfo）
        if getattr(entry, "published_parsed", None):
            try:
                published_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except Exception:
                published_dt = None

        # fallback：解析字符串（RFC/ISO）
        if published_dt is None and published:
            published_dt = _parse_published_to_utc(published)

        # 只保留最近 7 天（如果能解析到时间）
        if published_dt and published_dt < cutoff:
            continue

        items.append(
            {
                "title": title or "(无标题)",
                "summary": summary,  # ✅ 这里保证一定有点文字
                "link": link,
                "published": published_dt.isoformat() if published_dt else str(published),
                "source": source_name,
                # 简单按来源判断语言：新浪 = zh，其它 = en
                "lang": "zh" if source_name.lower().startswith("sina") else "en",
            }
        )

        if len(items) >= limit:
            break

    return items


def fetch_sina_finance(limit: int = 20) -> List[Dict[str, Any]]:
    return _parse_feed(SINA_FINANCE_RSS, "Sina Finance", limit=limit)


def fetch_yahoo_finance(limit: int = 20) -> List[Dict[str, Any]]:
    return _parse_feed(YAHOO_FINANCE_RSS, "Yahoo Finance", limit=limit)


def fetch_investing(limit: int = 20) -> List[Dict[str, Any]]:
    return _parse_feed(INVESTING_RSS, "Investing.com", limit=limit)


def fetch_newsapi_finance(limit: int = 20, keyword: str = None) -> List[Dict[str, Any]]:
    try:
        client = NewsApiClient(api_key=NEWSAPI_KEY)
        resp = client.get_everything(q=(keyword or "").lower(), page_size=limit)
    except Exception:
        return []

    articles = resp.get("articles", []) if isinstance(resp, dict) else []
    items: List[Dict[str, Any]] = []

    for art in articles:
        title = (art.get("title") or "").strip()
        raw_summary = art.get("description") or art.get("content") or ""
        summary = _clean_html(raw_summary)
        if not summary:
            summary = title

        link = art.get("url", "")
        published = art.get("publishedAt", "")
        source_name = (art.get("source") or {}).get("name", "NewsAPI")

        items.append(
            {
                "title": title or "(无标题)",
                "summary": summary,
                "link": link,
                "published": published,
                "source": source_name,
                "lang": "en",
            }
        )

        if len(items) >= limit:
            break

    return items


def fetch_jisu_news(keyword: str = None, limit: int = 20) -> List[Dict[str, Any]]:
    url = "http://api.jisuapi.com/news/search"
    params = {"appkey": JISU_API_KEY, "keyword": keyword}
    try:
        j = requests.get(url, params=params, timeout=10).json()
    except Exception:
        return []

    items: List[Dict[str, Any]] = []
    articles = []
    try:
        if isinstance(j, dict):
            articles = j.get("result", {}).get("list", []) or []
    except Exception:
        articles = []

    for art in articles[:limit]:
        title = (art.get("title") or "").strip()
        raw_summary = art.get("content") or art.get("summary") or ""
        summary = _clean_html(raw_summary)
        if not summary:
            summary = title

        link = art.get("url") or art.get("weburl") or ""
        published = art.get("time") or art.get("pubDate") or ""
        source_name = art.get("src") or "JisuNews"

        items.append(
            {
                "title": title or "(无标题)",
                "summary": summary,
                "link": link,
                "published": published,
                "source": source_name,
                "lang": "zh",
            }
        )

    return items


def fetch_newsdataio_finance(limit: int = 20, keyword: str = None) -> List[Dict[str, Any]]:
    try:
        api = NewsDataApiClient(apikey=NEWSDATAIO_API_KEY)
        response = api.news_api(qInMeta=keyword, size=limit)
    except Exception:
        return []

    items: List[Dict[str, Any]] = []
    articles = []

    if isinstance(response, dict):
        articles = response.get("results", []) or response.get("data", []) or []
    elif hasattr(response, "get"):
        try:
            articles = response.get("results", []) or []
        except Exception:
            articles = []

    for art in (articles or [])[:limit]:
        title = (art.get("title") or art.get("headline") or "").strip()
        raw_summary = art.get("ai_summary") or art.get("description") or art.get("content") or ""
        summary = _clean_html(raw_summary)
        if not summary:
            summary = (art.get("description") or "")[:300]

        link = art.get("link") or art.get("url") or art.get("source_url") or ""
        published = art.get("pubDate") or art.get("published") or art.get("pubDateTZ") or ""
        source_name = art.get("source_name") or art.get("source_id") or art.get("source") or "NewsData.io"
        lang = art.get("language") or art.get("lang") or "en"

        items.append(
            {
                "title": title or "(无标题)",
                "summary": summary,
                "link": link,
                "published": published,
                "source": source_name,
                "lang": "zh" if str(lang).lower().startswith("zh") or str(source_name).lower().startswith("sina") else "en",
            }
        )

    return items


def fetch_mixed_finance_news(limit: int = 40, keyword: str = None) -> List[Dict[str, Any]]:
    """
    综合多源新闻：
    - 新浪财经（中文）
    - Yahoo Finance（英文）
    - Investing.com（英文）
    - NewsAPI（英文）
    - 极速API（中文）
    """
    items: List[Dict[str, Any]] = []

    for fn in (fetch_sina_finance, fetch_yahoo_finance, fetch_investing):
        try:
            part = fn(limit=limit // 2)
        except Exception:
            part = []
        items.extend(part)

    # NewsAPI
    try:
        newsapi_items = fetch_newsapi_finance(limit=limit // 2, keyword=keyword)
    except Exception:
        newsapi_items = []
    items.extend(newsapi_items)

    # 极速API
    try:
        jisu_items = fetch_jisu_news(keyword=keyword, limit=limit // 4)
    except Exception:
        jisu_items = []
    items.extend(jisu_items)

    # NewsData.io（可选，准确度不高就先不用）
    # try:
    #     newsdata_items = fetch_newsdataio_finance(limit=limit // 4, keyword=keyword)
    # except Exception:
    #     newsdata_items = []
    # items.extend(newsdata_items)

    def _published_ts(x: Dict[str, Any]) -> float:
        dt = _parse_published_to_utc(x.get("published"))
        return dt.timestamp() if dt else 0.0

    # 去掉没有标题的，按时间倒序
    items = [it for it in items if it.get("title")]
    items.sort(key=_published_ts, reverse=True)
    return items[:limit]


def filter_news_by_keyword(
    items: List[Dict[str, Any]],
    keyword: str,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    在已抓取的新闻列表中按关键词做一次简单筛选。
    keyword 匹配 title 或 summary（不区分大小写）。
    """
    if not items:
        return []

    if not keyword:
        return items[:limit]

    kw = keyword.strip().lower()
    matched: List[Dict[str, Any]] = []

    for it in items:
        title = (it.get("title") or "").lower()
        summary = (it.get("summary") or "").lower()
        if kw in title or kw in summary:
            matched.append(it)
            if len(matched) >= limit:
                break

    return matched if matched else items[:limit]
