"""암호가 걸린 원본: 비밀번호 없음/틀림/맞음, 원본 불변, 비밀번호 비노출. 합성 파일 + 가짜 비밀번호만 사용."""
import hashlib
from pathlib import Path

import pytest
from msoffcrypto.format.ooxml import OOXMLFile
from openpyxl import load_workbook

from scholarship_payment import __main__ as cli
from scholarship_payment.adapters.base import InputValidationFailed
from scholarship_payment.adapters.daechung import DaechungAdapter
from scholarship_payment.app.controller import run_conversion
from scholarship_payment.app.convert import ConversionFailed, convert

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
PW = "가짜-pw-0000!"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture
def enc(make_input, tmp_path):
    plain = make_input(n=4)
    dst = tmp_path / "encrypted_input.xlsx"
    with open(plain, "rb") as f, open(dst, "wb") as o:
        OOXMLFile(f).encrypt(PW, o)
    return plain, dst


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


def codes(exc):
    return [e.code for e in exc.value.errors]


def test_fixture_is_really_encrypted(enc):
    with pytest.raises(Exception):
        load_workbook(enc[1])


def test_no_password_is_reported_as_required(enc):
    with pytest.raises(InputValidationFailed) as e:
        DaechungAdapter().read(enc[1])
    assert codes(e) == ["INPUT_PASSWORD_REQUIRED"]


@pytest.mark.parametrize("pw", ["", None])
def test_empty_password_is_required(enc, pw):
    with pytest.raises(InputValidationFailed) as e:
        DaechungAdapter().read(enc[1], pw)
    assert codes(e) == ["INPUT_PASSWORD_REQUIRED"]


def test_wrong_password_is_rejected(enc):
    with pytest.raises(InputValidationFailed) as e:
        DaechungAdapter().read(enc[1], "틀린비밀번호")
    assert codes(e) == ["INPUT_PASSWORD_WRONG"]


def test_correct_password_gives_same_batch_as_plain_file(enc):
    plain, dst = enc
    a, b = DaechungAdapter().read(plain), DaechungAdapter().read(dst, PW)
    assert a.batch == b.batch and a.source_totals == b.source_totals


def test_password_on_unencrypted_file_is_ignored(enc):
    assert DaechungAdapter().read(enc[0], PW).batch.rows


def test_corrupt_file_is_unreadable_not_password(tmp_path):
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not an excel file")
    with pytest.raises(InputValidationFailed) as e:
        DaechungAdapter().read(bad, PW)
    assert codes(e) == ["FILE_UNREADABLE"]


def test_convert_with_password_writes_output_and_keeps_source(enc, out):
    before = sha(enc[1])
    res = convert("daechung", enc[1], out, TEMPLATE, password=PW)
    assert res.count == 4 and sha(enc[1]) == before
    assert not any(c.data_type == "f" for ws in load_workbook(res.output_path) for r in ws.iter_rows() for c in r)
    # 출력은 암호 없이 열린다
    load_workbook(res.output_path)


def test_failures_leave_no_file_and_never_echo_the_password(enc, out):
    for pw in (None, "틀린비밀번호", PW + "x"):
        with pytest.raises(ConversionFailed) as e:
            convert("daechung", enc[1], out, TEMPLATE, password=pw)
        text = str(e.value) + repr(e.value) + " ".join(str(x) + repr(x) for x in e.value.errors)
        assert PW not in text and "틀린비밀번호" not in text
    assert list(out.iterdir()) == []


def test_controller_flags_needs_password(enc, out):
    o = run_conversion("daechung", enc[1], out, TEMPLATE)
    assert not o.ok and o.needs_password and PW not in o.summary and list(out.iterdir()) == []
    o = run_conversion("daechung", enc[1], out, TEMPLATE, password="틀림")
    assert o.needs_password and "틀렸" in o.summary
    o = run_conversion("daechung", enc[1], out, TEMPLATE, password=PW)
    assert o.ok and not o.needs_password


def _argv(enc, out, *extra):
    return ["convert", "--program", "daechung", "--input", str(enc[1]), "--out-dir", str(out), "--template", str(TEMPLATE), *extra]


def test_cli_without_flag_hints_and_fails(enc, out, capsys):
    assert cli.main(_argv(enc, out)) == 1
    assert "--ask-password" in capsys.readouterr().err and list(out.iterdir()) == []


def test_cli_prompts_with_getpass_and_gives_up_after_three(enc, out, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": calls.append(1) or "틀림")
    assert cli.main(_argv(enc, out, "--ask-password")) == 1
    assert len(calls) == 3 and list(out.iterdir()) == []
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": PW)
    assert cli.main(_argv(enc, out, "--ask-password")) == 0
    assert PW not in capsys.readouterr().out
