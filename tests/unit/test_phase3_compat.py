"""Phase 3 추가 검증: 기존 변환 계약 호환(정책 경로 없는 호출 포함), 템플릿 바이트 경로·임시 파일, 지문 계산 예외, 기존 CLI/Tk 공용 경로의 신규 오류 처리.
입력·템플릿·정책은 모두 합성이다."""
import dataclasses
import hashlib
import inspect
import os
import tempfile
from pathlib import Path

import pytest

from scholarship_payment import __main__ as cli
from scholarship_payment.app import convert as conv
from scholarship_payment.app import workflow as wf
from scholarship_payment.app.controller import run_conversion
from scholarship_payment.app.convert import ConversionFailed, PolicySource, check_unchanged, convert, diagnose_changes, finish, prepare
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.config.policy_file import load_policy
from prep_helpers import TEMPLATE, flip_byte_keep_size_and_mtime, make_policy

BASE = "2099.10.07"


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def tpl(tmp_path):
    p = tmp_path / "tpl.xlsx"
    p.write_bytes(TEMPLATE.read_bytes())
    return p


@pytest.fixture
def sandbox_tmp(tmp_path, monkeypatch):
    d = tmp_path / "sys_tmp"
    d.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(d))
    return d


# ---------- 1. 기존 변환 계약 ----------
def test_convert_signature_and_defaults_are_unchanged():
    sig = inspect.signature(convert)
    assert list(sig.parameters) == ["program", "input_path", "out_dir", "template_path", "policy", "base_date", "today", "password"]
    d = {k: v.default for k, v in sig.parameters.items()}
    assert d["policy"] is SYNTHETIC_POLICY and d["base_date"] is None and d["today"] is None and d["password"] is None
    assert [p for p, v in sig.parameters.items() if v.default is inspect.Parameter.empty] == ["program", "input_path", "out_dir", "template_path"]


def test_calls_without_any_policy_path_work_for_default_and_object_policies(make_input, tpl, out, tmp_path):
    src = make_input(n=3)
    r1 = convert("daechung", src, out, tpl, base_date=BASE)                                           # 기본 SYNTHETIC_POLICY
    pol = dataclasses.replace(SYNTHETIC_POLICY, file_prefix="다른접두")
    r2 = convert("daechung", src, out, tpl, policy=pol, base_date=BASE)                                 # OutputPolicy 객체
    assert r1.count == r2.count == 3 and r2.output_path.name.startswith("다른접두")


def test_policy_object_calls_carry_no_policy_fingerprint_and_ignore_policy_files(make_input, tpl, out, tmp_path):
    pol_path = make_policy(tmp_path)
    src = make_input(n=3)
    p = prepare("daechung", src, tpl, policy=load_policy(pol_path), base_date=BASE)                    # 기존 CLI 방식: 정책 객체만 전달
    assert p.policy_fp is None and p._policy_path is None
    flip_byte_keep_size_and_mtime(pol_path)                                                            # 정책 파일이 바뀌어도(객체는 이미 메모리에 있음)
    assert check_unchanged(p) == () and finish(p, out).count == 3


def test_gui_style_policy_source_is_checked_but_object_style_is_not(make_input, tpl, out, tmp_path):
    pol_path = make_policy(tmp_path)
    src = make_input(n=3)
    gui = prepare("daechung", src, tpl, policy=load_policy(pol_path), base_date=BASE, policy_source=PolicySource(pol_path, conv.fingerprint_file(pol_path)))
    cli_style = prepare("daechung", src, tpl, policy=load_policy(pol_path), base_date=BASE)
    flip_byte_keep_size_and_mtime(pol_path)
    assert check_unchanged(gui) == ("policy",) and check_unchanged(cli_style) == ()


def test_controller_and_cli_without_policy_path_still_succeed(make_input, tpl, out, tmp_path, capsys):
    src = make_input(n=3)
    o = run_conversion("daechung", src, out, tpl, base_date=BASE)
    assert o.ok and o.count == 3 and o.stage == "ok"
    out2 = tmp_path / "o2"
    out2.mkdir()
    assert cli.main(["convert", "--program", "daechung", "--input", str(src), "--out-dir", str(out2), "--template", str(tpl), "--base-date", BASE]) == 0
    assert capsys.readouterr().err == ""                                                               # 불필요한 오류 출력 없음


def test_controller_with_policy_path_still_loads_policy_without_hashing_it(make_input, tpl, out, tmp_path, monkeypatch):
    pol_path = make_policy(tmp_path)
    calls = []
    real = conv.fingerprint_file
    monkeypatch.setattr(conv, "fingerprint_file", lambda p: (calls.append(os.fspath(p)), real(p))[1])
    o = run_conversion("daechung", make_input(n=3), out, tpl, policy_path=pol_path, base_date=BASE)
    assert o.ok and os.fspath(pol_path) not in calls                                                  # 기존 경로는 정책 파일을 해시하지 않는다


# ---------- 2. 템플릿 바이트: 실제 경로와 임시 파일 ----------
def test_writer_receives_a_memory_copy_whose_hash_equals_the_recorded_fingerprint(make_input, tpl, out, monkeypatch):
    seen = {}
    real = conv.build_workbook

    def spy(validated, template, policy, base_date=None):
        seen["type"] = type(template).__name__
        seen["sha"] = hashlib.sha256(template.getvalue()).hexdigest()
        return real(validated, template, policy, base_date)

    monkeypatch.setattr(conv, "build_workbook", spy)
    p = prepare("daechung", make_input(n=2), tpl, base_date=BASE)
    finish(p, out)
    assert seen["type"] == "BytesIO" and seen["sha"] == p.template_fp.sha256 == hashlib.sha256(tpl.read_bytes()).hexdigest()


def test_no_temporary_file_is_created_for_template_or_inputs_on_success(make_input, tpl, out, sandbox_tmp):
    src, before_src_dir = make_input(n=3), None
    siblings = sorted(x.name for x in tpl.parent.iterdir())
    p = prepare("daechung", src, tpl, base_date=BASE)
    res = finish(p, out)
    assert list(sandbox_tmp.iterdir()) == []                                                          # 시스템 임시 폴더에 아무것도 만들지 않는다
    assert [x.name for x in out.iterdir()] == [res.output_path.name]                                  # 저장 폴더에는 최종 파일만(저장용 임시 파일은 정리됨)
    assert sorted(x.name for x in tpl.parent.iterdir()) == siblings and before_src_dir is None        # 템플릿·원본 폴더에도 새 파일이 없다


@pytest.mark.parametrize("failure", ["layout", "verify", "changed", "missing_dir"])
def test_failures_leave_no_temp_files_anywhere(failure, make_input, tpl, out, sandbox_tmp, tmp_path, monkeypatch):
    from openpyxl import load_workbook
    src = make_input(n=3)
    if failure == "layout":
        wb = load_workbook(tpl)
        del wb["WINS"]
        wb.save(tpl)
    p = prepare("daechung", src, tpl, base_date=BASE)
    target = out
    if failure == "verify":
        monkeypatch.setattr(conv, "verify_output", lambda *a, **k: (_ for _ in ()).throw(conv.ValidationFailed([conv.ValidationError("OUTPUT_MISMATCH", "x")])))
    if failure == "changed":
        flip_byte_keep_size_and_mtime(src)
    if failure == "missing_dir":
        target = tmp_path / "no_dir"
    with pytest.raises(ConversionFailed):
        finish(p, target)
    assert list(sandbox_tmp.iterdir()) == [] and list(out.iterdir()) == [] and not (tmp_path / "no_dir").exists()


def test_template_bytes_are_not_kept_in_prepared_or_leaked_into_errors(make_input, tpl, out):
    p = prepare("daechung", make_input(n=2), tpl, base_date=BASE)
    data = tpl.read_bytes()
    assert not [f for f in dataclasses.fields(p) if isinstance(getattr(p, f.name), (bytes, bytearray))]
    tpl.write_bytes(b"x" + data)
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert str(tpl) not in repr(e.value) + str(e.value) and [x.field for x in e.value.errors] == ["template"]


# ---------- 2. 변경·삭제 시 생성 차단, 지문 계산 예외 ----------
@pytest.mark.parametrize("which", ["source", "template", "policy"])
@pytest.mark.parametrize("action", ["modify", "delete"])
def test_modified_or_deleted_inputs_block_generation_and_create_nothing(which, action, make_input, tpl, out, tmp_path, sandbox_tmp):
    pol_path = make_policy(tmp_path)
    src = make_input(n=3)
    p = prepare("daechung", src, tpl, policy=load_policy(pol_path), base_date=BASE, policy_source=PolicySource(pol_path, conv.fingerprint_file(pol_path)))
    target = {"source": src, "template": tpl, "policy": pol_path}[which]
    flip_byte_keep_size_and_mtime(target) if action == "modify" else Path(target).unlink()
    assert diagnose_changes(p) == {which: "INPUT_FILE_CHANGED"}
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert e.value.stage == "changed" and [(x.code, x.field) for x in e.value.errors] == [("INPUT_FILE_CHANGED", which)]
    assert list(out.iterdir()) == [] and list(sandbox_tmp.iterdir()) == []


def _deny(monkeypatch, target_path):
    """target_path 에 대한 지문 계산·읽기만 PermissionError 로 만든다."""
    real_fp, real_read = conv.fingerprint_file, Path.read_bytes
    t = os.fspath(target_path)

    def fp(path):
        if os.fspath(path) == t:
            raise PermissionError(f"denied: {t}")
        return real_fp(path)

    def rb(self):
        if os.fspath(self) == t:
            raise PermissionError(f"denied: {t}")
        return real_read(self)

    monkeypatch.setattr(conv, "fingerprint_file", fp)
    monkeypatch.setattr(Path, "read_bytes", rb)


@pytest.mark.parametrize("which", ["source", "template", "policy"])
def test_permission_error_while_fingerprinting_is_reported_as_unreadable_not_crash(which, make_input, tpl, out, tmp_path, monkeypatch):
    pol_path = make_policy(tmp_path)
    src = make_input(n=3)
    p = prepare("daechung", src, tpl, policy=load_policy(pol_path), base_date=BASE, policy_source=PolicySource(pol_path, conv.fingerprint_file(pol_path)))
    _deny(monkeypatch, {"source": src, "template": tpl, "policy": pol_path}[which])
    assert diagnose_changes(p) == {which: "INPUT_FILE_UNREADABLE"} and check_unchanged(p) == (which,)
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert e.value.stage == "changed" and [(x.code, x.field) for x in e.value.errors] == [("INPUT_FILE_UNREADABLE", which)]
    assert str(tpl) not in repr(e.value) + str(e.value) and list(out.iterdir()) == []


def test_oserror_other_than_permission_is_also_contained(make_input, tpl, out, monkeypatch):
    src = make_input(n=3)
    p = prepare("daechung", src, tpl, base_date=BASE)
    monkeypatch.setattr(conv, "fingerprint_file", lambda path: (_ for _ in ()).throw(OSError(5, "input/output error")))
    assert set(diagnose_changes(p).values()) == {"INPUT_FILE_UNREADABLE"}
    with pytest.raises(ConversionFailed):
        finish(p, out)


def test_prepare_with_unhashable_source_fails_closed_as_unreadable(make_input, tpl, monkeypatch):
    src = make_input(n=3)
    _deny(monkeypatch, src)                                                                  # 읽기 전후 지문을 모두 못 만든다(어댑터는 읽을 수 있다고 가정)
    real_read = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes", real_read)
    with pytest.raises(ConversionFailed) as e:
        prepare("daechung", src, tpl, base_date=BASE)
    assert e.value.stage == "input" and [x.code for x in e.value.errors] == ["FILE_UNREADABLE"] and str(src) not in repr(e.value) + str(e.value)


def test_prepare_template_permission_error_keeps_the_old_error(make_input, tpl, monkeypatch):
    src = make_input(n=3)
    _deny(monkeypatch, tpl)
    with pytest.raises(ConversionFailed) as e:
        prepare("daechung", src, tpl, base_date=BASE)
    assert e.value.stage == "template" and [x.code for x in e.value.errors] == ["TEMPLATE_UNREADABLE"]


def test_workflow_policy_fingerprint_errors_are_contained_and_distinguished(make_input, tpl, tmp_path, monkeypatch):
    pol_path = make_policy(tmp_path)
    src = make_input(n=2)
    missing = wf.run_prepare("daechung", src, tpl, tmp_path / "none.json", BASE)
    assert missing.status == "failed" and missing.errors[0].code == "POLICY_FILE_MISSING"
    monkeypatch.setattr(wf, "fingerprint_file", lambda path: (_ for _ in ()).throw(PermissionError("denied")))
    denied = wf.run_prepare("daechung", src, tpl, pol_path, BASE)
    assert denied.status == "failed" and denied.stage == "policy" and denied.errors[0].code == "POLICY_UNREADABLE" and str(pol_path) not in repr(denied)


# ---------- 2·4. 기존 CLI·공용 경로: 원본 파싱 중 파일 변경, 신규 단계 ----------
def _flip_during_read(monkeypatch):
    from scholarship_payment.adapters.daechung import DaechungAdapter
    real = DaechungAdapter.read

    def modify(self, path, password=None):
        r = real(self, path, password)
        flip_byte_keep_size_and_mtime(path)
        return r

    monkeypatch.setattr(DaechungAdapter, "read", modify)


def test_controller_handles_source_change_during_parse_safely(make_input, tpl, out, monkeypatch):
    _flip_during_read(monkeypatch)
    src = make_input(n=3)
    o = run_conversion("daechung", src, out, tpl, base_date=BASE)
    assert not o.ok and o.stage == "changed" and not o.needs_password and "바뀌" in o.summary and "만들지 않았습니다" in o.summary
    assert any("INPUT_FILE_CHANGED" in d for d in o.details) and str(src) not in o.summary + " ".join(o.details)
    assert list(out.iterdir()) == []


def test_cli_exits_nonzero_with_guidance_and_no_output_on_source_change(make_input, tpl, out, monkeypatch, capsys):
    _flip_during_read(monkeypatch)
    src = make_input(n=3)
    code = cli.main(["convert", "--program", "daechung", "--input", str(src), "--out-dir", str(out), "--template", str(tpl), "--base-date", BASE])
    err = capsys.readouterr().err
    assert code == 1 and "changed" in err and "INPUT_FILE_CHANGED" in err and str(src) not in err and list(out.iterdir()) == []


def test_controller_reports_unreadable_input_stage_for_unhashable_source(make_input, tpl, out, monkeypatch):
    src = make_input(n=3)
    _deny(monkeypatch, src)
    o = run_conversion("daechung", src, out, tpl, base_date=BASE)
    assert not o.ok and o.stage in ("input", "changed") and list(out.iterdir()) == []
