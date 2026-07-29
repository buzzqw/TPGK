import os
import sys

repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import pytest  # noqa: E402
from tpgk.settings import Settings  # noqa: E402
from tpgk.history import HistoryManager  # noqa: E402
import tpgk.settings as settings_mod  # noqa: E402
import tpgk.history as history_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch, tmp_path):
    cfg_dir = str(tmp_path / "tpgk_config")
    cfg_file = str(tmp_path / "tpgk_config" / "settings.json")
    monkeypatch.setattr(settings_mod, "CONFIG_DIR", cfg_dir)
    monkeypatch.setattr(settings_mod, "CONFIG_FILE", cfg_file)
    Settings._instance = None
    Settings._loaded = False
    HistoryManager._instance = None
    yield
    Settings._instance = None
    Settings._loaded = False
    HistoryManager._instance = None


@pytest.fixture
def isolated_history(monkeypatch, tmp_path):
    hist_dir = str(tmp_path / "tpgk_hist")
    hist_db = str(tmp_path / "tpgk_hist" / "history.db")
    os.makedirs(hist_dir, exist_ok=True)
    monkeypatch.setattr(history_mod, "HISTORY_DIR", hist_dir)
    monkeypatch.setattr(history_mod, "HISTORY_DB", hist_db)
    HistoryManager._instance = None
    yield HistoryManager()
    HistoryManager._instance = None
