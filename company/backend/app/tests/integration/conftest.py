from __future__ import annotations

import os

import httpx
import pytest

import app.modules.fhir_gateway.seed as fhir_seed
from app.modules.fhir_gateway.client import FhirClient


def _integration_enabled() -> bool:
    return os.getenv("RUN_FHIR_INTEGRATION_TESTS", "0") == "1"


@pytest.fixture(scope="session")
def live_fhir_base_url() -> str:
    if not _integration_enabled():
        pytest.skip("FHIR integration tests are disabled. Set RUN_FHIR_INTEGRATION_TESTS=1 to enable them.")
    return os.getenv("FHIR_INTEGRATION_BASE_URL", "http://localhost:8080/fhir").rstrip("/")


@pytest.fixture(scope="session")
def seeded_live_fhir(live_fhir_base_url: str) -> str:
    response = httpx.get(f"{live_fhir_base_url}/metadata", timeout=10.0)
    if response.status_code != 200:
        pytest.skip(f"HAPI FHIR is not ready at {live_fhir_base_url}")

    original_base_url = fhir_seed.settings.fhir_base_url
    fhir_seed.settings.fhir_base_url = live_fhir_base_url
    try:
        fhir_seed.run()
        yield live_fhir_base_url
    finally:
        fhir_seed.settings.fhir_base_url = original_base_url


@pytest.fixture()
def live_fhir_client(seeded_live_fhir: str) -> FhirClient:
    return FhirClient(base_url=seeded_live_fhir)