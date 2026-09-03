"""Crash-test safety ratings via NHTSA's free, public SafetyRatings API
(api.nhtsa.gov). Public government data, not ALLDATA. No API key required.
"""
import requests

MODEL_URL = "https://api.nhtsa.gov/SafetyRatings/modelyear/{year}/make/{make}/model/{model}"
DETAIL_URL = "https://api.nhtsa.gov/SafetyRatings/VehicleId/{vehicle_id}"


def get_safety_ratings(make: str, model: str, year, timeout: float = 6.0) -> dict:
    if not (make and model and year):
        return {}
    try:
        resp = requests.get(MODEL_URL.format(year=year, make=make, model=model), timeout=timeout)
        resp.raise_for_status()
        variants = resp.json().get("Results", []) or []
        if not variants:
            return {}
        vehicle_id = variants[0].get("VehicleId")
        if not vehicle_id:
            return {}
        detail_resp = requests.get(DETAIL_URL.format(vehicle_id=vehicle_id), timeout=timeout)
        detail_resp.raise_for_status()
        results = detail_resp.json().get("Results", []) or []
        return results[0] if results else {}
    except (requests.RequestException, ValueError):
        return {}
