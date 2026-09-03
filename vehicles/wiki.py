"""A short background summary for a vehicle model via Wikipedia's free,
public REST API (en.wikipedia.org/api/rest_v1). No API key required.
Summary text is Wikipedia's own (CC BY-SA) -- shown with attribution and a
link back, not reproduced elsewhere.
"""
import requests

SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"


def get_model_summary(make: str, model: str, timeout: float = 6.0) -> dict:
    make = (make or "").strip()
    model = (model or "").strip()
    if not (make and model):
        return {}
    title = f"{make}_{model}".replace(" ", "_")
    try:
        resp = requests.get(SUMMARY_URL.format(title=title), timeout=timeout, headers={"User-Agent": "Repair-Hub/1.0"})
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError):
        return {}

    if data.get("type") != "standard":
        return {}

    return {
        "title": data.get("title", ""),
        "extract": data.get("extract", ""),
        "thumbnail": (data.get("thumbnail") or {}).get("source", ""),
        "page_url": (data.get("content_urls", {}).get("desktop", {}) or {}).get("page", ""),
    }
