"""안전 저장: 무덮어쓰기, 검증 실패 시 흔적 없음, 오류 구분."""
import hashlib
import os
import stat

import pytest
from openpyxl import Workbook

from scholarship_payment.errors import ValidationFailed
from scholarship_payment.io import safe_save
from scholarship_payment.io.safe_save import save_new


def wb(tag="a"):
    w = Workbook()
    w.active["A1"] = tag
    return w


def ok(_path):
    return None


def names(d):
    return sorted(p.name for p in d.iterdir())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_creates_the_file_and_leaves_no_temp(tmp_path):
    p = save_new(wb(), tmp_path, "결과.xlsx", ok)
    assert p == tmp_path / "결과.xlsx" and names(tmp_path) == ["결과.xlsx"]


def test_existing_file_is_never_overwritten(tmp_path):
    existing = tmp_path / "결과.xlsx"
    existing.write_bytes(b"precious")
    p = save_new(wb(), tmp_path, "결과.xlsx", ok)
    assert existing.read_bytes() == b"precious" and p.name == "결과_2.xlsx"
    p3 = save_new(wb(), tmp_path, "결과.xlsx", ok)
    assert p3.name == "결과_3.xlsx" and names(tmp_path) == ["결과.xlsx", "결과_2.xlsx", "결과_3.xlsx"]
    assert existing.read_bytes() == b"precious"


def test_verification_receives_the_temp_file_and_failure_leaves_nothing(tmp_path):
    seen = []

    def verify(path):
        seen.append(path)
        assert path.exists() and path.name != "결과.xlsx"
        raise ValidationFailed([])
    with pytest.raises(ValidationFailed):
        save_new(wb(), tmp_path, "결과.xlsx", verify)
    assert names(tmp_path) == [] and len(seen) == 1


def test_failure_does_not_touch_existing_files(tmp_path):
    existing = tmp_path / "결과.xlsx"
    existing.write_bytes(b"precious")
    with pytest.raises(RuntimeError):
        save_new(wb(), tmp_path, "결과.xlsx", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    assert names(tmp_path) == ["결과.xlsx"] and existing.read_bytes() == b"precious"


def test_missing_output_folder(tmp_path):
    with pytest.raises(ValidationFailed) as ei:
        save_new(wb(), tmp_path / "없는폴더", "x.xlsx", ok)
    assert [(e.code, e.field) for e in ei.value.errors] == [("OUTPUT_DIR_MISSING", "out_dir")]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="POSIX 권한 모델 필요")
def test_unwritable_folder(tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(stat.S_IREAD | stat.S_IEXEC)
    try:
        with pytest.raises(ValidationFailed) as ei:
            save_new(wb(), d, "x.xlsx", ok)
        assert ei.value.errors[0].code == "OUTPUT_PERMISSION"
    finally:
        d.chmod(stat.S_IRWXU)


def test_fallback_when_hard_links_are_unsupported(tmp_path, monkeypatch):
    def no_link(*a, **k):
        raise OSError("no links")
    monkeypatch.setattr(safe_save.os, "link", no_link)
    (tmp_path / "x.xlsx").write_bytes(b"precious")
    p = save_new(wb(), tmp_path, "x.xlsx", ok)
    assert p.name == "x_2.xlsx" and (tmp_path / "x.xlsx").read_bytes() == b"precious" and p.stat().st_size > 100
    assert names(tmp_path) == ["x.xlsx", "x_2.xlsx"]


def test_name_exhaustion_is_reported_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(safe_save, "MAX_SUFFIX", 3)
    for n in ("x.xlsx", "x_2.xlsx", "x_3.xlsx"):
        (tmp_path / n).write_bytes(b"p")
    with pytest.raises(ValidationFailed) as ei:
        save_new(wb(), tmp_path, "x.xlsx", ok)
    assert ei.value.errors[0].code == "OUTPUT_NAME_EXHAUSTED"
    assert names(tmp_path) == ["x.xlsx", "x_2.xlsx", "x_3.xlsx"]
    assert all(sha(tmp_path / n) == hashlib.sha256(b"p").hexdigest() for n in names(tmp_path))
