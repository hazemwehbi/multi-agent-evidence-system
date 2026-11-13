import os

import pytest


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch, tmp_path):
    for name in os.environ:
        if name.upper().startswith("MAEDS_") or name.upper().startswith("OPENAI_"):
            monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)
