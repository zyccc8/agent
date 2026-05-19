from __future__ import annotations

import html
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Callable, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


USER_AGENT = "Mozilla/5.0 (compatible; CompetitorAnalysisAgent/1.0)"
SEARCH_URL = "https://duckduckgo.com/html/?q={query}"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass
class ExtractedPage:
    title: str
    url: str
    text: str


class DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[SearchResult] = []
        self._in_link = False
        self._in_snippet = False
        self._current_title: List[str] = []
        self._current_href = ""
        self._current_snippet: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._in_link = True
            self._current_title = []
            self._current_href = attrs_dict.get("href", "")
        if tag in {"a", "div"} and "result__snippet" in classes:
            self._in_snippet = True
            self._current_snippet = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._in_link:
            self._in_link = False
        if tag in {"a", "div"} and self._in_snippet:
            self._in_snippet = False
            title = clean_text(" ".join(self._current_title))
            url = normalize_duckduckgo_url(self._current_href)
            snippet = clean_text(" ".join(self._current_snippet))
            if title and url:
                self.results.append(SearchResult(title=title, url=url, snippet=snippet))

    def handle_data(self, data: str) -> None:
        if self._in_link:
            self._current_title.append(data)
        if self._in_snippet:
            self._current_snippet.append(data)


class PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: List[str] = []
        self.text_parts: List[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        if tag in {"script", "style", "svg", "noscript", "template"}:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript", "template"} and self._skip_depth:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        stripped = clean_text(data)
        if len(stripped) >= 30:
            self.text_parts.append(stripped)


class WebResearchClient:
    def __init__(
        self,
        fetcher: Optional[Callable[[str], str]] = None,
        timeout: int = 8,
        max_pages_per_query: int = 2,
    ) -> None:
        self.fetcher = fetcher or self._fetch_url
        self.timeout = timeout
        self.max_pages_per_query = max_pages_per_query

    def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        url = SEARCH_URL.format(query=quote_plus(query))
        html_text = self.fetcher(url)
        parser = DuckDuckGoParser()
        parser.feed(html_text)
        return dedupe_results(parser.results)[:limit]

    def extract(self, url: str) -> ExtractedPage:
        html_text = self.fetcher(url)
        parser = PageTextParser()
        parser.feed(html_text)
        title = clean_text(" ".join(parser.title_parts)) or urlparse(url).netloc
        text = clean_text(" ".join(parser.text_parts))
        return ExtractedPage(title=title, url=url, text=text)

    def research_competitor(self, industry: str, competitor: str) -> List[ExtractedPage]:
        queries = [
            f"{competitor} {industry} official pricing features",
            f"{competitor} {industry} product blog review",
        ]
        pages: List[ExtractedPage] = []
        seen_urls = set()
        for query in queries:
            try:
                results = self.search(query, limit=4)
            except (HTTPError, URLError, TimeoutError, socket.timeout):
                continue
            for result in results:
                if result.url in seen_urls or not is_http_url(result.url):
                    continue
                seen_urls.add(result.url)
                try:
                    page = self.extract(result.url)
                except (HTTPError, URLError, TimeoutError, socket.timeout, UnicodeDecodeError):
                    page = ExtractedPage(
                        title=result.title,
                        url=result.url,
                        text=result.snippet,
                    )
                if page.text:
                    pages.append(page)
                if len(pages) >= self.max_pages_per_query:
                    return pages
        return pages

    def _fetch_url(self, url: str) -> str:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")


def page_to_excerpt(text: str, competitor: str, max_chars: int = 420) -> str:
    sentences = split_sentences(text)
    preferred = [
        sentence for sentence in sentences
        if competitor.lower() in sentence.lower()
        or any(keyword in sentence.lower() for keyword in ["pricing", "features", "ai", "product", "customers", "teams"])
    ]
    chosen = preferred[:3] or sentences[:3]
    return clean_text(" ".join(chosen))[:max_chars]


def infer_source_type(url: str, title: str, text: str) -> str:
    haystack = f"{url} {title} {text}".lower()
    if "pricing" in haystack or "plans" in haystack:
        return "pricing"
    if "blog" in haystack or "news" in haystack:
        return "blog"
    if "review" in haystack or "g2.com" in haystack or "capterra" in haystack:
        return "review"
    if "docs" in haystack or "help" in haystack:
        return "docs"
    return "website"


def split_sentences(text: str) -> List[str]:
    normalized = clean_text(text)
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+", normalized) if part.strip()]


def clean_text(value: str) -> str:
    unescaped = html.unescape(value)
    return re.sub(r"\s+", " ", unescaped).strip()


def normalize_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.path.startswith("/l/"):
        params = parse_qs(parsed.query)
        if "uddg" in params:
            return unquote(params["uddg"][0])
    return url


def dedupe_results(results: Iterable[SearchResult]) -> List[SearchResult]:
    seen = set()
    deduped = []
    for result in results:
        key = result.url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
