# 0003. Keyless web search with DuckDuckGo fallbacks

Date: 2026-11-17
Status: accepted

## Context

`web_search` must work without an API key. It originally scraped only the
DuckDuckGo HTML endpoint with a regex. Research and live testing found:

- DDG HTML scraping is fragile: CAPTCHA, 403s, and parser drift are common.
- Live requests from this environment hit DDG bot detection.
- DDG wraps result targets as `//duckduckgo.com/l/?uddg=<encoded-url>`, so the
  old parser returned redirect URLs rather than the real destinations.
- Reliable keyless alternatives exist: a second free DDG endpoint (Lite),
  and self-hosted SearXNG with a clean JSON API.

## Decision

Keep the tool keyless but harden it:

1. If `SEARXNG_URL` is set, query `{url}/search?q=...&format=json` first. The
   instance must have the `json` format enabled; a 403, network error, or
   malformed JSON falls back to DuckDuckGo rather than failing.
2. Otherwise try DuckDuckGo's HTML endpoint, then Lite; the first endpoint
   with results wins.
3. Decode `uddg=` wrappers and normalize protocol-relative links to real URLs.
4. Detect bot challenges via several signals ("captcha", "unusual traffic",
   "anomaly", "blocked"+"requests") and report a clear error when all
   endpoints are blocked.
5. Report network failures distinctly from "no results".

## Consequences

- No new dependencies; works out of the box with no configuration.
- Results now contain real target URLs instead of DDG redirect wrappers.
- Bot-blocked environments (like this one) get a clear, actionable error
  rather than silent emptiness — verified by a live CLI run.
- Residual limitation: without `SEARXNG_URL`, heavy use from one IP will still
  be rate-limited by DDG. The `SEARXNG_URL` option (self-hosted instance) is
  the implemented upgrade path for reliability; it is optional so the default
  stays zero-configuration.
