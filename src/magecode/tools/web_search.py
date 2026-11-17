"""Search the web via DuckDuckGo (no API key required).

Tries the HTML endpoint first, then the Lite endpoint as a fallback (both
free). Decodes DuckDuckGo's ``uddg=`` redirect wrappers so results contain
real target URLs. Detects bot challenges using several known signals.
"""

import html as html_mod
import re
import urllib.error
import urllib.parse
import urllib.request

from anima import Context, Service

_MAX_RESULTS = 8
_TIMEOUT = 15
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

# Parsers for the two free DuckDuckGo endpoints: (url template, link regex).
_ENDPOINTS = [
    (
        "https://html.duckduckgo.com/html/?{}",
        re.compile(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        ),
    ),
    (
        "https://lite.duckduckgo.com/lite/?{}",
        re.compile(
            r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            re.DOTALL,
        ),
    ),
]

_BOT_SIGNALS = ("captcha", "unusual traffic", "anomaly")


def _is_bot_challenge(page: str) -> bool:
    lower = page.lower()
    if any(signal in lower for signal in _BOT_SIGNALS):
        return True
    return "blocked" in lower and "requests" in lower


def _decode_href(href: str) -> str:
    """Return the real target URL from a DuckDuckGo result href.

    DDG wraps targets as ``//duckduckgo.com/l/?uddg=<encoded-url>``. Decode
    that; otherwise normalize protocol-relative links to https.
    """
    href = html_mod.unescape(href)
    if "uddg=" in href:
        query = href.split("?", 1)[1] if "?" in href else ""
        for pair in query.split("&"):
            if pair.startswith("uddg="):
                return urllib.parse.unquote(pair[len("uddg=") :])
    if href.startswith("//"):
        return "https:" + href
    return href


def _parse_results(page: str, pattern: re.Pattern[str]) -> list[str]:
    results: list[str] = []
    for match in pattern.finditer(page):
        href = _decode_href(match.group(1))
        title = html_mod.unescape(re.sub(r"<.*?>", "", match.group(2))).strip()
        if title and href:
            results.append(f"{title}: {href}")
        if len(results) >= _MAX_RESULTS:
            break
    return results


class WebSearchService(Service):
    """Search the web via DuckDuckGo (HTML endpoint, Lite fallback).

    Returns result titles and real URLs. No API key required.

    Args:
        query: Search query string.

    Returns:
        Up to 8 results as 'title: url' lines, or an error/no-results message.
    """

    def __init__(self, ctx: Context):
        super().__init__(ctx, "web_search")

    def __call__(self, *, query: str) -> str:
        encoded = urllib.parse.urlencode({"q": query})
        bot_blocked = False
        network_errors: list[str] = []

        for template, pattern in _ENDPOINTS:
            url = template.format(encoded)
            req = urllib.request.Request(url, headers=_UA)
            try:
                with urllib.request.urlopen(req, timeout=_TIMEOUT) as response:
                    page = response.read().decode("utf-8", errors="replace")
            except (urllib.error.URLError, OSError) as error:
                network_errors.append(str(error))
                continue  # try the next endpoint

            if _is_bot_challenge(page):
                bot_blocked = True
                continue  # try the next endpoint

            results = _parse_results(page, pattern)
            if results:
                return "\n".join(results)

        if network_errors and not bot_blocked:
            return (
                f"Error: web search failed: {network_errors[-1]}. "
                "Check your network connection and retry the query."
            )
        if bot_blocked:
            return (
                "Error: web search failed: DuckDuckGo is blocking automated "
                "requests (bot detection). Try again later or use a different "
                "query."
            )
        return "No web results found. Try rephrasing the query."
