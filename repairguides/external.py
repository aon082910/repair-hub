"""Search free/open external repair-guide sources.

iFixit publishes a free, public API (https://www.ifixit.com/api/2.0/) for
searching their guide library, which is published under a Creative Commons
license and explicitly intended for third-party search/linking. We only
fetch a title/summary/link per result and send the user to iFixit's own
site for the full guide -- we never mirror or store their content.

This module deliberately does NOT attempt to search or scrape paid/
ToS-restricted providers (ALLDATA, Mitchell1, Chilton, RepairPal, etc).
"""
import requests

IFIXIT_SEARCH_URL = "https://www.ifixit.com/api/2.0/search/{query}"
COMMONS_API_URL = "https://commons.wikimedia.org/w/api.php"


def search_ifixit(query: str, limit: int = 15, timeout: float = 6.0) -> list:
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = requests.get(
            IFIXIT_SEARCH_URL.format(query=requests.utils.quote(query)),
            params={"filter": "guide", "limit": limit},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return []

    results = []
    for item in data.get("results", [])[:limit]:
        url = item.get("url") or ""
        if not url:
            continue
        results.append(
            {
                "title": item.get("title") or "Untitled guide",
                "summary": item.get("summary") or "",
                "url": url,
                "image": (item.get("image") or {}).get("thumbnail", ""),
                "source": "iFixit",
            }
        )
    return results


def search_commons_images(query: str, limit: int = 12, timeout: float = 6.0) -> list:
    """Search Wikimedia Commons for freely-licensed (mostly CC) reference
    photos/diagrams. Generic component/system images, not vehicle-specific
    repair photos. We only link to the Commons file page -- no hotlinking
    of full-resolution files without attribution context."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = requests.get(
            COMMONS_API_URL,
            params={
                "action": "query",
                "format": "json",
                "generator": "search",
                "gsrsearch": f"{query} filetype:bitmap",
                "gsrnamespace": 6,
                "gsrlimit": limit,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": 300,
            },
            timeout=timeout,
            headers={"User-Agent": "Repair-Hub/1.0 (self-hosted repair reference app)"},
        )
        resp.raise_for_status()
        pages = (resp.json().get("query") or {}).get("pages") or {}
    except (requests.RequestException, ValueError):
        return []

    results = []
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        title = (page.get("title") or "").replace("File:", "")
        results.append(
            {
                "title": title,
                "thumb_url": info.get("thumburl", ""),
                "page_url": info.get("descriptionurl", ""),
                "source": "Wikimedia Commons",
            }
        )
    return results
