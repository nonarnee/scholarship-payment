"""합성 E2E 검증 모드(`python -m scholarship_payment.ui --synthetic-e2e-smoke --work-dir D --result-json F`): CI 에서 **패키징된 exe 안에서**
실제 Step 1 → Step 2 → Step 3 생성 경로를 프로그램적으로 구동해, 패키징에 필요한 모듈이 모두 들어 있고 생성 경로가 끝까지 동작하는지 확인한다.

- 입력은 CI 가 만든 **완전 합성** 파일뿐이다(`tools/ci/prepare_e2e_inputs.py`). 실제 자료·업무 로직 변경 없음 — 화면 위젯의 버튼·입력창을 코드로 눌러(`click`) 같은 경로를 탄다.
- 확인하는 것: 관련 모듈 로딩 / 합성 Excel 파싱·정책·템플릿 로딩·미리보기 / 실제 XLSX 생성과 출력 재검증 통과(finish 성공) / 같은 이름 무덮어쓰기(_2)와 이전 임시 파일 보존 /
  암호 파일(msoffcrypto)의 비밀번호 재입력 / 저장 폴더 오류 뒤 같은 확인 결과로 재시도(원본 재파싱 없음) / 이번 작업의 임시 파일 정리.
- 골든 출력과의 동등성은 exe 바깥에서 `tools/ci/verify_e2e_outputs.py` 가 비교한다.
- **확인하지 않는 것(미검증으로 남음)**: 실제 창 표시·글꼴·DPI, 파일 선택 대화상자, 드래그 앤 드롭, 실제 폴더 열기·클립보드, OS 수준 입력, 실제 Excel 에서 열기.
- 결과 JSON 에는 단계별 성공 여부와 출력 경로만 남긴다(예외는 종류만, 학생 값 없음). 표준 출력에는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication

from scholarship_payment.app import workflow
from scholarship_payment.config.user_settings import UserSettings
from scholarship_payment.ui import generation as gn
from scholarship_payment.ui import preview as pv
from scholarship_payment.ui import runtime_check
from scholarship_payment.ui.context import AppContext
from scholarship_payment.ui.main_window import MainWindow
from scholarship_payment.ui.navigation import Step
from scholarship_payment.ui.qt_runner import QtRunner
from scholarship_payment.ui.state import SettingsStore

WAIT_SECONDS = 90


class _Fail(Exception):
    pass


class _Chooser:
    def __init__(self) -> None:
        self.folders: list[str] = []

    def choose_folder(self, parent, start_dir=None):
        return self.folders.pop(0) if self.folders else None

    def __getattr__(self, name):
        return lambda *a, **k: None


class _NoActions:
    def open_folder(self, path) -> bool:
        return True

    def copy_text(self, text) -> bool:
        return True


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _expect(cond, detail: str) -> None:
    if not cond:
        raise _Fail(detail)


class _Driver:
    def __init__(self, work: Path) -> None:
        self.work = work
        self.manifest = json.loads((work / "manifest.json").read_text(encoding="utf-8"))
        self.app = QApplication.instance()
        self.chooser = _Chooser()
        store = SettingsStore(work / "cfg" / "settings.json")
        store.commit(UserSettings(last_program="daechung").with_paths("daechung", template_path=str(work / "template.xlsx"), policy_path=str(work / "policy.json"),
                                                                      out_dir=str(work / "out_overwrite")))
        y, m, d = (int(x) for x in self.manifest["base_date"].split("."))
        self.ctx = AppContext(store=store, runner=QtRunner(), chooser=self.chooser, today=lambda: date(y, m, d), default_dirs=[],
                              generation_runner=QtRunner(), actions=_NoActions(), now=datetime.now)
        self.w = MainWindow(context=self.ctx)
        self.w.show()

    def wait(self, cond, what: str, seconds: int | None = None) -> None:
        deadline = time.time() + (WAIT_SECONDS if seconds is None else seconds)
        while time.time() < deadline:
            self.app.processEvents()
            if cond():
                return
            time.sleep(0.01)
        raise _Fail(f"시간 초과: {what}")

    def select(self, source: Path, out_dir: Path) -> None:
        m = self.w.step1.model
        self.wait(lambda: self.w.navigator.current == Step.FILE, "Step 1")
        m.set_out_dir(str(out_dir))
        m.set_source(str(source))
        self.wait(m.ready, "Step 1 입력 확인")
        _expect(m.base_date == self.manifest["base_date"], "기준일")

    def to_ready_preview(self) -> None:
        self.w.next_button.click()                                           # Step 1 → Step 2
        s = self.w.step2.session
        self.wait(lambda: s.state in (pv.READY, pv.NEED_PASSWORD, pv.FAILED), "미리보기")

    def generate(self) -> gn.GenerationSession:
        _expect(self.w.next_button.isEnabled(), "생성 버튼 활성")
        self.w.next_button.click()                                           # Step 2 → Step 3(생성 시작)
        g = self.w.generation
        self.wait(lambda: not g.busy and g.state != gn.IDLE, "생성 완료")
        return g

    def new_conversion(self) -> None:
        self.w.step3.new_button.click()
        self.wait(lambda: self.w.navigator.current == Step.FILE and not self.w.navigator.locked, "새 변환")

    def close(self) -> None:
        self.w.close()
        for r in (self.ctx.runner, self.ctx.generation_runner):
            r.shutdown(10000)


def _step_plain_with_existing(d: _Driver, facts: dict) -> str:
    ow = d.work / "out_overwrite"
    d.select(d.work / "inputs" / "plain.xlsx", ow)
    d.to_ready_preview()
    s = d.w.step2.session
    _expect(s.state == pv.READY, "미리보기 READY")
    _expect(s.summary.count == d.manifest["rows"] and s.summary.total_amount > 0, "미리보기 인원·합계")
    g = d.generate()
    o = g.outcome
    _expect(g.state == gn.SUCCESS and o.status == "ok", "생성 성공(출력 재검증 포함)")
    out = Path(o.output_path)
    _expect(out.name == d.manifest["expected_name"].replace(".xlsx", "_2.xlsx") and o.name_changed, "같은 이름이면 _2 로 저장")
    _expect(_sha(ow / d.manifest["expected_name"]) == d.manifest["existing_sha"], "기존 결과 무덮어쓰기")
    _expect(_sha(ow / d.manifest["leftover_name"]) == d.manifest["leftover_sha"], "이전 임시 파일 보존")
    _expect(o.leftover_temp == 1 and o.count == d.manifest["rows"] and o.size_bytes and o.size_bytes > 0, "결과 값")
    facts["outputs"]["overwrite_avoided"] = str(out)
    d.new_conversion()
    return "ok"


def _step_encrypted(d: _Driver, facts: dict) -> str:
    d.select(d.work / "inputs" / "encrypted.xlsx", d.work / "out_encrypted")
    d.to_ready_preview()
    s, p = d.w.step2.session, d.w.step2
    _expect(s.state == pv.NEED_PASSWORD, "암호 파일은 비밀번호를 묻는다")
    p.password_edit.setText("wrong-synthetic-password")
    p.password_ok.click()
    d.wait(lambda: s.state == pv.NEED_PASSWORD and s.attempts == 1 and s.last_password_wrong, "잘못된 비밀번호 처리")
    p.password_edit.setText(d.manifest["password"])
    p.password_ok.click()
    d.wait(lambda: s.state == pv.READY, "올바른 비밀번호로 미리보기")
    _expect(s.summary.count == d.manifest["rows"], "암호 파일 미리보기 인원")
    g = d.generate()
    _expect(g.state == gn.SUCCESS and Path(g.outcome.output_path).name == d.manifest["expected_name"], "암호 파일에서 생성 성공")
    facts["outputs"]["encrypted"] = str(g.outcome.output_path)
    d.new_conversion()
    return "ok"


def _step_folder_error_retry(d: _Driver, facts: dict) -> str:
    missing, fresh = d.work / "out_retry_missing", d.work / "out_retry_new"
    calls: list[int] = []
    real_prepare = workflow.prepare
    workflow.prepare = lambda *a, **k: (calls.append(1), real_prepare(*a, **k))[1]           # 원본 재파싱 여부를 세기 위한 계수기(동작은 그대로)
    try:
        d.select(d.work / "inputs" / "plain.xlsx", missing)
        d.to_ready_preview()
        _expect(d.w.step2.session.state == pv.READY and len(calls) == 1, "미리보기 1회")
        shutil.rmtree(missing)                                                # 미리보기 뒤 저장 폴더가 사라짐
        g = d.generate()
        _expect(g.state == gn.FAILED and g.failure_kind == gn.KIND_FOLDER and g.can_retry, "저장 폴더 오류로 분류")
        _expect(g.outcome.errors and g.outcome.errors[0].code == "OUTPUT_DIR_MISSING" and not missing.exists(), "폴더를 만들거나 파일을 남기지 않음")
        d.chooser.folders.append(str(fresh))
        d.w.step3.change_folder_button.click()
        d.w.step3.retry_button.click()                                         # 같은 Prepared 로 재시도(생성 직전에 지문 재확인)
        d.wait(lambda: not g.busy, "재시도 완료")
        _expect(g.state == gn.SUCCESS and Path(g.outcome.output_path).parent == fresh, "폴더를 바꿔 재시도 성공")
        _expect(len(calls) == 1, "재시도에서 원본을 다시 파싱하지 않음")
    finally:
        workflow.prepare = real_prepare
    facts["outputs"]["retry_after_folder_error"] = str(g.outcome.output_path)
    d.new_conversion()
    return "ok"


STEPS = (("plain_with_existing_result", _step_plain_with_existing), ("encrypted_with_password_retry", _step_encrypted),
         ("folder_error_then_retry_with_same_prepared", _step_folder_error_retry))


def run(work_dir, result_json) -> int:
    work = Path(work_dir)
    facts: dict = {"frozen": bool(getattr(sys, "frozen", False)), "modules": {}, "steps": [], "outputs": {}}
    missing = set(runtime_check.missing_modules())
    for name in runtime_check.REQUIRED_MODULES:
        facts["modules"][name] = name not in missing
    facts["steps"].append({"name": "modules", "ok": all(facts["modules"].values())})
    ok = facts["steps"][0]["ok"]
    driver = None
    try:
        driver = _Driver(work)
        for name, fn in STEPS:
            try:
                fn(driver, facts)
                facts["steps"].append({"name": name, "ok": True})
            except _Fail as e:
                facts["steps"].append({"name": name, "ok": False, "detail": str(e)})
                ok = False
                break
        else:
            try:
                leftovers = sorted(p.name for p in work.rglob(".~*.xlsx"))
                _expect(leftovers == [driver.manifest["leftover_name"]], "이번 작업의 임시 파일이 남지 않음")
                _expect(driver.w.close() is not False and not driver.w.isVisible(), "작업이 끝난 뒤 창을 닫을 수 있음")
                facts["steps"].append({"name": "cleanup_and_close", "ok": True})
            except _Fail as e:
                facts["steps"].append({"name": "cleanup_and_close", "ok": False, "detail": str(e)})
                ok = False
    except Exception as e:                                                      # 예외 문구에는 경로가 들어갈 수 있어 종류만 남긴다
        facts["error"] = type(e).__name__
        ok = False
    finally:
        if driver is not None:
            driver.close()
        Path(result_json).write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok and all(s["ok"] for s in facts["steps"]) else 1
