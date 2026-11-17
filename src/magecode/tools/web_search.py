"""Search the web using DuckDuckGo HTML (no API key required)."""

import re
import urllib.error
import urllib.parse
import urllib.request

from magecode.tools.registry import tool


@tool
def web_search(*, query: str) -> str:
    """Search the web using DuckDuckGo.

    Returns result titles and URLs. No API key required.

    Args:
        query: Search query string.

    Returns:
        Up to 8 results as 'title: url' lines, or 'No web results found.'
    """
    encoded = urllib.parse.urlencode({"q": query})
    url = f"https://html.duckduckgo.com/html/?{encoded}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError) as error:
        return (
            f"Error: web search failed: {error}. "
            "Check your network connection and retry the query."
        )

    results: list[str] = []
    for match in re.finditer(
        r'<a rel="nofollow" class="result__a" href="([^"]+)">(.*?)</a>',
        html,
        re.DOTALL,
    ):
        href = match.group(1)
        title = re.sub(r"<.*?>", "", match.group(2)).strip()
        if title and href:
            results.append(f"{title}: {href}")
        if len(results) >= 8:
            break

    if not results:
        if "captcha" in html.lower() or "unusual traffic" in html.lower():
            return (
                "Error: web search failed: DuckDuckGo is blocking automated "
                "requests (bot detection). Try again later or use a different "
                "query."
            )
        return "No web results found. Try rephrasing the query."
    return "\n".join(results)
