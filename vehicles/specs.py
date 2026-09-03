"""Vehicle specs via the EPA's free, public fueleconomy.gov API
(www.fueleconomy.gov/feg/ws). Public government data, XML-based, no key
required. Returns {} / [] on any failure so pages stay usable offline.
"""
import xml.etree.ElementTree as ET

import requests

MENU_MODEL_URL = "https://www.fueleconomy.gov/ws/rest/vehicle/menu/model"
MENU_MODELS_URL = "https://www.fueleconomy.gov/ws/rest/vehicle/menu/options"
VEHICLE_URL = "https://www.fueleconomy.gov/ws/rest/vehicle/{id}"


def _get_xml(url, params=None, timeout=6.0):
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError):
        return None


def _fetch_options(year, make, model, timeout):
    root = _get_xml(MENU_MODELS_URL, {"year": year, "make": make, "model": model}, timeout)
    if root is None:
        return []
    options = []
    for item in root.findall("menuItem"):
        value = item.findtext("value")
        text = item.findtext("text")
        if value:
            options.append({"id": value, "text": text or value})
    return options


def find_vehicle_options(year, make, model, timeout: float = 6.0) -> list:
    """Return [{'id':..., 'text': trim/engine description}, ...] matching a
    year/make/model -- fueleconomy.gov splits by trim/engine combo, and often
    uses a more specific model name than ours (e.g. "Civic 4Dr" vs "Civic"),
    so an exact-name miss falls back to a prefix match against their model
    list for that year/make."""
    if not (year and make and model):
        return []

    options = _fetch_options(year, make, model, timeout)
    if options:
        return options

    root = _get_xml(MENU_MODEL_URL, {"year": year, "make": make}, timeout)
    if root is None:
        return []
    model_lower = model.strip().lower()
    for item in root.findall("menuItem"):
        candidate = item.findtext("value") or ""
        if candidate.lower().startswith(model_lower):
            options = _fetch_options(year, make, candidate, timeout)
            if options:
                return options
    return []


def get_vehicle_specs(vehicle_id, timeout: float = 6.0) -> dict:
    root = _get_xml(VEHICLE_URL.format(id=vehicle_id), timeout=timeout)
    if root is None:
        return {}

    def f(tag):
        return root.findtext(tag) or ""

    return {
        "make": f("make"),
        "model": f("model"),
        "year": f("year"),
        "trim": f("trany") or f("VClass"),
        "engine": f("eng_dscr") or f("displ"),
        "cylinders": f("cylinders"),
        "transmission": f("trany"),
        "drive": f("drive"),
        "fuel_type": f("fuelType"),
        "city_mpg": f("city08"),
        "highway_mpg": f("highway08"),
        "combined_mpg": f("comb08"),
    }
