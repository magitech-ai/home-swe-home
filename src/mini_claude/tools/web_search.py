"""Search the web using DuckDuckGo HTML (no API key required)."""

import re
import urllib.error
import urllib.parse
import urllib.request

from mini_claude.tools import tool


@tool(
    name="web_search",
    manual=(
        "Search the web using DuckDuckGo (no API key required). "
        "Returns result titles and URLs.\n"
        "Manual:\n"
        "  - Provide a search query string.\n"
        "  - Returns up to 8 results as 'title: url' lines.\n"
        "  - Returns 'No web results found.' if nothing matches.\n"
        "  - On network failure the result starts with 'Error:';\n"
        "    check your connection and retry the query.\n"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query string.",
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)
def web_search(*, query: str) -> str:
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
        return "No web results found. Try rephrasing the query."
    return "\n".join(results)
