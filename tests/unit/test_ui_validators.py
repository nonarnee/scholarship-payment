"""화면용 검증기(Qt 무관): 가벼운 검사(존재·확장자) / 무거운 검사(구조)를 구분하고, 값·경로를 메시지에 넣지 않는다."""
import zipfile
from pathlib import Path

import pytest

from scholarship_payment.ui import validators as v

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"


def test_source_light_checks(tmp_path, make_input):
    ok = make_input(n=2)
    assert v.light("source", ok).level == v.OK
    assert v.light("source", None).level == v.UNSET and v.light("source", "").level == v.UNSET
    assert v.light("source", tmp_path / "없음.xlsx").code == "SOURCE_MISSING"
    assert v.light("source", tmp_path).code == "SOURCE_NOT_FILE"
    for name in ("a.xls", "a.csv", "a.xlsm", "a.txt", "a"):
        (tmp_path / name).write_bytes(b"x")
        assert v.light("source", tmp_path / name).code == "SOURCE_NOT_XLSX_EXT"
    (tmp_path / "~$임시.xlsx").write_bytes(b"x")
    assert v.light("source", tmp_path / "~$임시.xlsx").code == "SOURCE_TEMP_FILE"
    (tmp_path / "빈.xlsx").write_bytes(b"")
    assert v.light("source", tmp_path / "빈.xlsx").code == "SOURCE_EMPTY"
    (tmp_path / "UP.XLSX").write_bytes(b"x")
    assert v.light("source", tmp_path / "UP.XLSX").level == v.OK          # 확장자는 대소문자 무시


def test_light_check_never_opens_the_file(tmp_path, monkeypatch):
    p = tmp_path / "a.xlsx"
    p.write_bytes(b"x")
    monkeypatch.setattr("builtins.open", lambda *a, **k: (_ for _ in ()).throw(AssertionError("opened")))
    assert v.light("source", p).level == v.OK


def test_source_structure_accepts_real_xlsx_without_reading_cells(make_input):
    r = v.heavy("source", make_input(n=2))
    assert r.level == v.OK and r.note is None


def test_source_structure_rejects_non_zip_and_wrong_zip(tmp_path):
    bad = tmp_path / "a.xlsx"
    bad.write_bytes(b"not a zip at all")
    assert v.heavy("source", bad).code == "SOURCE_NOT_XLSX"
    z = tmp_path / "b.xlsx"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("hello.txt", "x")
    assert v.heavy("source", z).code == "SOURCE_NOT_XLSX"


def test_ole_container_is_reported_as_possibly_encrypted_not_as_error(tmp_path):
    p = tmp_path / "enc.xlsx"
    p.write_bytes(bytes.fromhex("D0CF11E0A1B11AE1") + b"\x00" * 64)
    r = v.heavy("source", p)
    assert r.level == v.OK and r.note == "SOURCE_ENCRYPTED_POSSIBLE"


def test_structure_check_does_not_parse_amounts_or_names(make_input, monkeypatch):
    import openpyxl
    monkeypatch.setattr(openpyxl, "load_workbook", lambda *a, **k: (_ for _ in ()).throw(AssertionError("parsed")))
    assert v.heavy("source", make_input(n=2)).level == v.OK


def test_dir_check_is_advisory_and_creates_nothing(tmp_path):
    assert v.light("dir", tmp_path).level == v.OK and list(tmp_path.iterdir()) == []
    assert v.light("dir", tmp_path / "없음").code == "DIR_MISSING"
    f = tmp_path / "f.txt"
    f.write_text("x")
    assert v.light("dir", f).code == "DIR_NOT_DIR"
    assert v.light("dir", None).level == v.UNSET


def test_dir_not_writable_is_only_a_note_when_os_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(v.os, "access", lambda p, mode: False)
    r = v.light("dir", tmp_path)
    assert r.level == v.OK and r.note == "DIR_NOT_WRITABLE"          # os.access 는 확정 근거가 아니다 → 차단하지 않는다


def test_template_and_policy_checks_reuse_existing_loaders(tmp_path):
    assert v.light("template", TEMPLATE).level == v.OK and v.heavy("template", TEMPLATE).level == v.OK
    bad = tmp_path / "t.xlsx"
    bad.write_bytes(b"nope")
    assert v.heavy("template", bad).code == "TEMPLATE_UNREADABLE"
    (tmp_path / "t.txt").write_bytes(b"x")
    assert v.light("template", tmp_path / "t.txt").code == "TEMPLATE_NOT_XLSX_EXT"
    assert v.light("policy", tmp_path / "x.json").code == "POLICY_FILE_MISSING"
    p = tmp_path / "p.json"
    p.write_text("{}", encoding="utf-8")
    assert v.light("policy", p).level == v.OK and v.heavy("policy", p).level == v.ERROR and v.heavy("policy", p).code.startswith("POLICY_")
    q = tmp_path / "q.txt"
    q.write_text("{}")
    assert v.light("policy", q).code == "POLICY_NOT_JSON_EXT"


def test_messages_exist_for_every_code_and_never_embed_values(tmp_path):
    for code in ("SOURCE_MISSING", "SOURCE_NOT_XLSX", "DIR_MISSING", "TEMPLATE_LAYOUT", "POLICY_KEY_MISSING", "DATE_FORMAT", "DATE_INVALID", "SOURCE_ENCRYPTED_POSSIBLE"):
        assert v.message(code)
    secret = tmp_path / "학생홍길동_비공개.xlsx"
    assert "홍길동" not in v.message(v.light("source", secret).code)
    assert "UNKNOWN_CODE_X" in v.message("UNKNOWN_CODE_X")            # 모르는 코드는 코드만 보여 준다


@pytest.mark.parametrize("text,code", [("2099.10.07", None), ("2024.02.29", None), ("2099-10-07", "DATE_FORMAT"), ("", "DATE_FORMAT"), ("2099.13.01", "DATE_INVALID"),
                                       ("2023.02.29", "DATE_INVALID"), ("2099.1.7", "DATE_FORMAT"), ("２０９９.10.07", "DATE_FORMAT")])
def test_date_check(text, code):
    r = v.check_date(text)
    assert (r.level == v.OK) == (code is None) and r.code == code


def test_classify_drop_accepts_exactly_one_local_xlsx(tmp_path):
    f = tmp_path / "a.xlsx"
    f.write_bytes(b"x")
    assert v.classify_drop([str(f)]) == (str(f), None)
    assert v.classify_drop([]) == (None, "DROP_EMPTY")
    assert v.classify_drop([str(f), str(f)]) == (None, "DROP_MULTIPLE")
    (tmp_path / "a.csv").write_bytes(b"x")
    assert v.classify_drop([str(tmp_path / "a.csv")]) == (None, "DROP_NOT_XLSX")
    assert v.classify_drop([str(tmp_path)]) == (None, "DROP_NOT_FILE")
    assert v.classify_drop([""]) == (None, "DROP_NOT_FILE")
    assert v.classify_drop([str(tmp_path / "없는.xlsx")]) == (None, "DROP_NOT_FILE")
