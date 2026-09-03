"""Recalls and complaints via NHTSA's free, public API (api.nhtsa.gov).

Public government data, not ALLDATA content. No API key required. All
functions return {} / [] on any network failure so pages stay usable when
the server has no internet access (e.g. an air-gapped Unraid box).
"""
import requests

RECALLS_URL = "https://api.nhtsa.gov/recalls/recallsByVehicle"
COMPLAINTS_URL = "https://api.nhtsa.gov/complaints/complaintsByVehicle"


def get_recalls(make: str, model: str, year, timeout: float = 6.0) -> list:
    if not (make and model and year):
        return []
    try:
        resp = requests.get(
            RECALLS_URL, params={"make": make, "model": model, "modelYear": year}, timeout=timeout
        )
        resp.raise_for_status()
        return resp.json().get("results", []) or []
    except (requests.RequestException, ValueError):
        return []


def get_complaints(make: str, model: str, year, timeout: float = 6.0) -> list:
    if not (make and model and year):
        return []
    try:
        resp = requests.get(
            COMPLAINTS_URL, params={"make": make, "model": model, "modelYear": year}, timeout=timeout
        )
        resp.raise_for_status()
        results = resp.json().get("results", []) or []
        return results[:50]
    except (requests.RequestException, ValueError):
        return []
