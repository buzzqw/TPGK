import threading

import pytest

from tpgk.ai_client import AIClient, AIRequestCancelled
from tpgk.profiles import load_profile, save_profile
from tpgk.session import load_state, restore_window, save_state


class _Page:
    def __init__(self, cwd, base_title, title):
        self.cwd = cwd
        self.base_title = base_title
        self.title = title

    def get_cwd(self):
        return self.cwd


class _Notebook:
    def __init__(self, pages=()):
        self.pages = list(pages)

    def get_n_pages(self):
        return len(self.pages)

    def get_nth_page(self, index):
        return self.pages[index]


class _Window:
    def __init__(self, pages=()):
        self._notebook = _Notebook(pages)
        self._notebook2 = _Notebook()
        self._split_mode = "single"
        self._tab_base_titles = {page: page.base_title for page in pages}
        self.added = []
        self.prepared = False

    def _get_tab_text(self, page):
        return page.title

    def _add_new_tab(self, **kwargs):
        self.added.append(kwargs)

    def _set_split(self, mode, create_tab=True):
        self._split_mode = mode
        self.split_create_tab = create_tab

    def _prepare_session_restore(self):
        self.prepared = True


@pytest.fixture
def isolated_persistence(monkeypatch, tmp_path):
    import tpgk.profiles as profiles
    import tpgk.session as session

    monkeypatch.setattr(profiles, "PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(session, "SESSION_DIR", str(tmp_path / "sessions"))


def test_session_names_cannot_escape_storage(isolated_persistence):
    with pytest.raises(ValueError):
        save_state(_Window(), "../outside")
    with pytest.raises(ValueError):
        load_state("/tmp/outside")


def test_profile_names_cannot_escape_storage(isolated_persistence):
    with pytest.raises(ValueError):
        save_profile("nested/name", {})


def test_session_restore_preserves_titles_without_placeholder_tab(isolated_persistence, tmp_path):
    cwd = str(tmp_path)
    source = _Window([
        _Page(cwd, "Build 1", "build output"),
        _Page(cwd, "Logs 2", "logs output"),
    ])
    source._notebook2 = _Notebook([_Page(cwd, "Deploy 3", "deploy output")])
    source._split_mode = "vertical"
    assert save_state(source, "work")

    target = _Window()
    restore_window(target, load_state("work"))

    assert target.prepared
    assert target._split_mode == "vertical"
    assert target.split_create_tab is False
    assert [tab["display_title"] for tab in target.added] == [
        "build output", "logs output", "deploy output"
    ]
    assert target.added[-1]["target_notebook"] is target._notebook2


def test_invalid_profile_data_is_not_applied(isolated_persistence, tmp_path):
    path = tmp_path / "profiles"
    path.mkdir()
    (path / "bad.json").write_text('{"font_size": "very large"}')
    assert load_profile("bad") is None


def test_invalid_session_data_is_not_restored(isolated_persistence, tmp_path):
    path = tmp_path / "sessions"
    path.mkdir()
    (path / "bad.json").write_text('{"split_mode": "diagonal", "tabs_left": []}')
    assert load_state("bad") is None


class _Response:
    def __init__(self):
        self.closed = False
        self.encoding = None

    def raise_for_status(self):
        return None

    def close(self):
        self.closed = True

    def iter_lines(self, decode_unicode=True):
        yield 'data: {"choices":[{"delta":{"content":"first"}}]}'
        yield 'data: {"choices":[{"delta":{"content":"second"}}]}'


class _Requests:
    def __init__(self, response):
        self.response = response
        self.timeout = None

    def post(self, *args, **kwargs):
        self.timeout = kwargs["timeout"]
        return self.response


def test_cancelled_stream_closes_response_and_rolls_back_messages(monkeypatch):
    import tpgk.ai_client as module

    response = _Response()
    requests = _Requests(response)
    monkeypatch.setattr(module, "_requests", requests)
    client = AIClient("openai", "key")
    cancel_event = threading.Event()
    stream = client.chat_stream("question", cancel_event)
    assert next(stream) == "first"
    cancel_event.set()
    with pytest.raises(AIRequestCancelled):
        next(stream)
    assert response.closed
    assert client._messages == []
    assert requests.timeout == (10, 5)


def test_cli_parser_accepts_directory_and_execute(tmp_path):
    from tpgk.__main__ import _parse_cli

    options = _parse_cli(["--working-directory", str(tmp_path), "--execute", "echo", "ok"])
    assert options.start_dir == str(tmp_path)
    assert options.execute == ["echo", "ok"]


def test_cli_parser_rejects_conflicting_directories(tmp_path):
    from tpgk.__main__ import _parse_cli

    with pytest.raises(SystemExit):
        _parse_cli([str(tmp_path), "--working-directory", str(tmp_path)])
