"""联网搜索：多源回退（360 → Bing → 搜狗）。

为什么 360 优先：
    实测 Bing 对中文查询返回大量泛化结果（搜 "AI Agent" 返回"什么是人工智能"），
    而 360 的中文相关度明显更好。因此默认先试 360，不行再退到 Bing。

局限：
- 只抓标题/摘要，不抓正文全文
- 结果上限 5 条，控制 prompt 长度
- 依赖对方页面结构，改版可能失效（有多源回退）
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_TIMEOUT = 12


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = ""

    def to_prompt(self, index: int) -> str:
        return f"[{index}] {self.title}\n    {self.snippet}\n    来源: {self.url}"


def _clean(raw: str) -> str:
    """去标签、反转义、压缩空白。"""
    text = re.sub(r"<[^>]+>", "", raw or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _get(url: str, timeout: int = _TIMEOUT) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _search_360(query: str, limit: int) -> list[SearchResult]:
    """360 搜索。

    关键字段：
    - <a data-mdurl="真实地址">  跳转链接在 href，真实地址在 data-mdurl
    - <span class="res-list-summary">  摘要
    """
    url = "https://www.so.com/s?" + urllib.parse.urlencode({"q": query})
    page = _get(url)

    out: list[SearchResult] = []
    seen: set[str] = set()

    for block in re.findall(r'<li[^>]*class="[^"]*res-list[^"]*"[^>]*>(.*?)</li>', page, re.S):
        if len(out) >= limit:
            break

        m = re.search(r'<h3[^>]*class="[^"]*res-title[^"]*"[^>]*>\s*<a([^>]*)>(.*?)</a>', block, re.S)
        if not m:
            continue
        attrs, title_html = m.group(1), m.group(2)
        title = _clean(title_html)
        if len(title) < 6 or "浏览器版本过低" in title:
            continue

        # 优先取 data-mdurl（真实地址），否则用 href
        real = re.search(r'data-mdurl="([^"]+)"', attrs)
        href = re.search(r'href="([^"]+)"', attrs)
        link = real.group(1) if real else (href.group(1) if href else "")
        link = html.unescape(link)

        # 摘要
        s = re.search(r'<span[^>]*class="[^"]*res-list-summary[^"]*"[^>]*>(.*?)</span>', block, re.S)
        snippet = _clean(s.group(1)) if s else ""
        if not snippet:
            p = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
            snippet = _clean(p.group(1)) if p else ""

        key = title[:25]
        if key in seen:
            continue
        seen.add(key)

        out.append(SearchResult(title, link, snippet[:400], "360"))

    return out


def _search_bing(query: str, limit: int) -> list[SearchResult]:
    """Bing：结构稳定，但中文相关性一般，作为第二选择。"""
    url = "https://cn.bing.com/search?" + urllib.parse.urlencode(
        {"q": query, "count": 10, "setlang": "zh-CN"}
    )
    page = _get(url)

    out: list[SearchResult] = []
    seen: set[str] = set()
    for block in re.split(r'<li[^>]*class="[^"]*b_algo[^"]*"', page)[1:]:
        if len(out) >= limit:
            break
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        title = _clean(m.group(2))
        if len(title) < 6:
            continue
        cap = re.search(r'<p[^>]*class="[^"]*b_lineclamp[^"]*"[^>]*>(.*?)</p>', block, re.S)
        if not cap:
            cap = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _clean(cap.group(1)) if cap else ""
        key = title[:25]
        if key in seen:
            continue
        seen.add(key)
        out.append(SearchResult(title, m.group(1), snippet[:400], "bing"))
    return out


def _search_sogou(query: str, limit: int) -> list[SearchResult]:
    """搜狗：兜底。"""
    url = "https://www.sogou.com/web?" + urllib.parse.urlencode({"query": query})
    page = _get(url)

    out: list[SearchResult] = []
    for block in re.findall(r'<div[^>]*class="[^"]*vrwrap[^"]*"[^>]*>(.*?)</div>\s*</div>', page, re.S):
        if len(out) >= limit:
            break
        t = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
        if not t:
            continue
        title = _clean(t.group(1))
        if len(title) < 6:
            continue
        a = re.search(r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"', block, re.S)
        d = re.search(r'<p[^>]*class="[^"]*str_info[^"]*"[^>]*>(.*?)</p>', block, re.S)
        snippet = _clean(d.group(1)) if d else ""
        out.append(SearchResult(title, a.group(1) if a else "", snippet[:400], "sogou"))
    return out


# 顺序即优先级：中文场景 360 最好用
_ENGINES = [
    ("360", _search_360),
    ("bing", _search_bing),
    ("sogou", _search_sogou),
]


def search(query: str, limit: int = 5) -> list[SearchResult]:
    """多源搜索。

    Args:
        query: 搜索词
        limit: 最多返回几条

    Returns:
        SearchResult 列表；全部失败返回 []
    """
    query = (query or "").strip()
    if not query:
        return []

    for _name, fn in _ENGINES:
        try:
            results = fn(query, limit)
        except Exception:
            continue
        if len(results) >= 2:
            return results
    return []


def format_for_prompt(results: list[SearchResult]) -> str:
    """把搜索结果转成给模型读的文本。"""
    if not results:
        return "（没有检索到相关结果）"
    return "\n\n".join(r.to_prompt(i + 1) for i, r in enumerate(results))


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "AI Agent 发展趋势"
    print(f"搜索：{q}\n")
    res = search(q)
    if not res:
        print("没有结果")
    for i, r in enumerate(res, 1):
        print(f"[{i}] ({r.source}) {r.title}")
        print(f"    {r.snippet[:180]}")
        print(f"    {r.url[:110]}\n")
