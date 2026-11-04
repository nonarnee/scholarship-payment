"""UI 테스트 공통: Qt 를 화면 없이(offscreen) 실행한다. PySide6 가 없으면(extra `gui` 미설치) 이 폴더의 테스트는 건너뛴다.
테스트는 완전 합성 데이터만 쓴다(실제 학생·파일 정보 없음)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    from scholarship_payment.ui.theme import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    return app


# ---- Phase 2 공용 픽스처: 실제 대화상자·실제 사용자 설정 폴더를 쓰지 않는다 ----
from ui_helpers import SYNTH_VALUES, TEMPLATE  # noqa: E402


class FakeChooser:
    """미리 넣어 둔 값을 돌려주는 선택기. 호출 기록은 calls 에 남는다."""

    def __init__(self):
        self.answers = {"source": [], "template": [], "policy": [], "folder": [], "save": []}
        self.calls = []

    def _next(self, kind, *a):
        self.calls.append(kind)
        q = self.answers[kind]
        return q.pop(0) if q else None

    def open_source(self, parent, start_dir=None):
        return self._next("source")

    def open_template(self, parent, start_dir=None):
        return self._next("template")

    def open_policy(self, parent, start_dir=None):
        return self._next("policy")

    def choose_folder(self, parent, start_dir=None):
        return self._next("folder")

    def save_policy(self, parent, suggested):
        return self._next("save")


class FakeActions:
    """폴더 열기·경로 복사를 실제로 하지 않고 기록만 한다."""

    def __init__(self):
        self.opened, self.copied = [], []
        self.open_ok = True
        self.copy_ok = True

    def open_folder(self, path):
        self.opened.append(str(path))
        return self.open_ok

    def copy_text(self, text):
        self.copied.append(str(text))
        return self.copy_ok


@pytest.fixture
def chooser():
    return FakeChooser()


@pytest.fixture
def make_context(tmp_path, chooser):
    """(settings 저장 위치·기본 탐색 폴더가 tmp_path 안인) 앱 컨텍스트 공장. runner 를 바꿀 수 있다."""
    def build(runner=None, settings=None, generation_runner=None, actions=None):
        from datetime import date, datetime

        from scholarship_payment.ui.context import AppContext
        from scholarship_payment.ui.runner import InlineRunner
        from scholarship_payment.ui.state import SettingsStore

        store = SettingsStore(tmp_path / "cfg" / "settings.json")
        if settings is not None:
            store.commit(settings)
        return AppContext(store=store, runner=runner or InlineRunner(), chooser=chooser, today=lambda: date(2099, 10, 7), default_dirs=[],
                          generation_runner=generation_runner, actions=actions or FakeActions(), now=lambda: datetime(2099, 10, 7, 12, 34, 56))
    return build


@pytest.fixture
def policy_file(tmp_path):
    from scholarship_payment.config.policy_builder import make_policy_file
    return make_policy_file(TEMPLATE, SYNTH_VALUES, tmp_path / "policy_daechung.json", "daechung")


@pytest.fixture
def out_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def ready_settings(policy_file, out_dir):
    from scholarship_payment.config.user_settings import UserSettings
    return UserSettings(last_program="daechung").with_paths("daechung", template_path=str(TEMPLATE), policy_path=str(policy_file), out_dir=str(out_dir))


@pytest.fixture(autouse=True)
def _isolate_user_settings(tmp_path_factory, monkeypatch):
    """어떤 UI 테스트도 실제 사용자 설정 폴더를 읽거나 쓰지 않는다(기본 컨텍스트를 쓰는 진입점 테스트 포함)."""
    from scholarship_payment.config import user_settings as us

    monkeypatch.setattr(us, "settings_path", lambda: tmp_path_factory.mktemp("isolated") / "settings.json")
