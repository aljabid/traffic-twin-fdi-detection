import pytest

from smart_city_security.pqc import BackendUnavailableError, PQCBackend
from smart_city_security.pqc import pqc_backend as pqc_backend_module


def test_package_imports_even_without_native_liboqs():
    assert PQCBackend is not None


def test_pqc_backend_raises_backend_unavailable_when_oqs_missing(monkeypatch):
    monkeypatch.setattr(pqc_backend_module, "oqs", None)
    with pytest.raises(BackendUnavailableError):
        PQCBackend()
