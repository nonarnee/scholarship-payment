"""패키징된 exe 용 합성 E2E 검증(`--synthetic-e2e-smoke`)의 로직을 파이썬에서 먼저 검증한다.
CI 에서는 같은 모드를 빌드된 PySide6 onedir exe 로 실행하고, 출력은 exe 바깥에서 골든과 비교한다."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

PySide6 = pytest.importorskip("PySide6")

ROOT = Path(__file__).resolve().parents[2]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / "ci" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(ROOT / "tools" / "ci"))
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tools():
    return _load("prepare_e2e_inputs"), _load("verify_e2e_outputs")


def test_synthetic_e2e_runs_the_whole_flow_and_outputs_match_golden(qapp, tmp_path, tools):
    from scholarship_payment.ui import e2e_smoke
    prepare, verify = tools
    work = tmp_path / "e2e"
    prepare.prepare(work)
    result = work / "result.json"
    assert e2e_smoke.run(work, result) == 0
    data = json.loads(result.read_text(encoding="utf-8"))
    assert verify.verify(work, result) == []
    names = [s["name"] for s in data["steps"]]
    assert names == ["modules", "plain_with_existing_result", "encrypted_with_password_retry", "folder_error_then_retry_with_same_prepared", "cleanup_and_close"]
    assert all(data["modules"].values()) and data["frozen"] is False and not data.get("error")
    assert str(tmp_path) not in json.dumps({k: v for k, v in data.items() if k != "outputs"}, ensure_ascii=False)       # 출력 경로 외에는 경로를 남기지 않는다


def test_verifier_detects_tampered_outputs_overwritten_files_and_stray_temp_files(qapp, tmp_path, tools):
    from openpyxl import load_workbook
    from scholarship_payment.ui import e2e_smoke
    prepare, verify = tools
    work = tmp_path / "e2e"
    m = prepare.prepare(work)
    result = work / "result.json"
    e2e_smoke.run(work, result)
    out = Path(json.loads(result.read_text(encoding="utf-8"))["outputs"]["encrypted"])
    wb = load_workbook(out)
    wb.worksheets[0]["A1"] = "변조"
    wb.save(out)
    (work / "out_overwrite" / m["expected_name"]).write_bytes(b"overwritten")
    (work / "out_overwrite" / m["leftover_name"]).unlink()
    (work / "out_encrypted" / ".~stray.xlsx").write_bytes(b"x")
    problems = " | ".join(verify.verify(work, result))
    assert "골든과 다름(encrypted)" in problems and "덮어씀" in problems and "임시 파일이 바뀌거나 지워졌다" in problems and "임시 파일이 남았다" in problems


def test_entry_point_mode_returns_zero_and_writes_a_result_file(qapp, tmp_path, tools, capsys):
    from scholarship_payment.ui import __main__ as entry
    prepare, verify = tools
    work = tmp_path / "e2e"
    prepare.prepare(work)
    code = entry.main(["--synthetic-e2e-smoke", "--work-dir", str(work), "--result-json", str(work / "r.json")])
    assert code == 0 and verify.verify(work, work / "r.json") == []
    assert str(work) not in capsys.readouterr().out                           # 표준 출력에 경로를 남기지 않는다


def test_entry_point_requires_its_arguments(qapp, capsys):
    from scholarship_payment.ui import __main__ as entry
    assert entry.main(["--synthetic-e2e-smoke"]) == 2


def test_prepared_inputs_are_fully_synthetic_and_deterministic(tmp_path, tools):
    prepare, _ = tools
    a, b = tmp_path / "a", tmp_path / "b"
    ma, mb = prepare.prepare(a), prepare.prepare(b)
    assert ma["existing_sha"] == mb["existing_sha"] and (a / "template.xlsx").read_bytes() == (ROOT / "templates" / "synthetic_payment_template.xlsx").read_bytes()
    assert (a / "policy.json").read_bytes() == (ROOT / "templates" / "synthetic_policy.json").read_bytes()
    assert not (a / "inputs" / "plain.xlsx").read_bytes().startswith(b"\xd0\xcf")           # 평문 입력
    assert (a / "inputs" / "encrypted.xlsx").read_bytes().startswith(bytes.fromhex("D0CF11E0A1B11AE1"))   # 암호 입력(OLE 컨테이너)


def test_e2e_mode_reports_failure_instead_of_passing_when_the_flow_is_broken(qapp, tmp_path, tools, monkeypatch):
    """검증 모드가 '항상 통과'가 되지 않는다: 미리보기 뒤 템플릿이 바뀌면 생성이 막히고 종료 코드 1 과 실패 단계가 남는다."""
    from scholarship_payment.ui import e2e_smoke
    prepare, verify = tools
    work = tmp_path / "e2e"
    prepare.prepare(work)
    monkeypatch.setattr(e2e_smoke, "WAIT_SECONDS", 5)
    real = e2e_smoke._Driver.generate

    def tamper_then_generate(self):
        data = bytearray((self.work / "template.xlsx").read_bytes())
        data[-1] ^= 1
        (self.work / "template.xlsx").write_bytes(bytes(data))                # 미리보기 후 템플릿이 바뀜 → 생성은 막혀야 한다
        return real(self)

    monkeypatch.setattr(e2e_smoke._Driver, "generate", tamper_then_generate)
    assert e2e_smoke.run(work, work / "r.json") == 1
    data = json.loads((work / "r.json").read_text(encoding="utf-8"))
    failed = [s for s in data["steps"] if not s["ok"]]
    assert failed and failed[0]["name"] == "plain_with_existing_result" and not list((work / "out_overwrite").glob("*_2.xlsx"))
    assert verify.verify(work, work / "r.json")                                 # 바깥 검증기도 실패로 본다


def test_missing_input_files_produce_an_error_result_not_a_crash(qapp, tmp_path, tools, monkeypatch):
    from scholarship_payment.ui import e2e_smoke
    prepare, _ = tools
    work = tmp_path / "e2e"
    prepare.prepare(work)
    (work / "inputs" / "plain.xlsx").unlink()
    monkeypatch.setattr(e2e_smoke, "WAIT_SECONDS", 2)
    assert e2e_smoke.run(work, work / "r.json") == 1
    data = json.loads((work / "r.json").read_text(encoding="utf-8"))
    assert [s for s in data["steps"] if not s["ok"]] and str(tmp_path) not in json.dumps(data["steps"], ensure_ascii=False)
