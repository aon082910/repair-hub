"""Optional VIN decoding via NHTSA's free, public vPIC API.

This calls the U.S. government's National Highway Traffic Safety
Administration API (https://vpic.nhtsa.dot.gov) which is public domain data,
not ALLDATA content. No API key required. Safe to leave disabled/offline —
callers should handle network failures gracefully.
"""
import requests

NHTSA_DECODE_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json"


def decode_vin(vin: str, timeout: float = 5.0) -> dict:
    """Return a dict with year/make/model/trim/engine best guesses, or {} on failure."""
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return {}
    try:
        resp = requests.get(NHTSA_DECODE_URL.format(vin=vin), timeout=timeout)
        resp.raise_for_status()
        results = resp.json().get("Results") or []
        if not results:
            return {}
        data = results[0]
    except (requests.RequestException, ValueError):
        return {}

    return {
        "year": data.get("ModelYear") or "",
        "make": data.get("Make") or "",
        "model": data.get("Model") or "",
        "trim": data.get("Trim") or "",
        "engine": " ".join(
            filter(None, [data.get("EngineCylinders") and f"{data.get('EngineCylinders')}cyl", data.get("DisplacementL") and f"{data.get('DisplacementL')}L", data.get("FuelTypePrimary")])
        ),
    }
