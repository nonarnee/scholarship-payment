"""사용자 설정 저장소: 허용 키만 저장, 왕복, 손상 보존(.bak 무덮어쓰기), 이동 실패에도 기본값 시작, 원자적 저장, 로그 무노출."""
import json
import logging
import os

import pytest

from scholarship_payment.config import user_settings as us


def _file(tmp_path):
    return tmp_path / "settings.json"


def test_missing_file_gives_defaults_without_creating_anything(tmp_path):
    r = us.load(_file(tmp_path))
    assert r.status == us.LOAD_MISSING and r.settings == us.UserSettings() and list(tmp_path.iterdir()) == []


def test_round_trip_keeps_per_program_paths_independent(tmp_path):
    s = us.UserSettings(last_program="ai").with_paths("daechung", template_path="/t/d.xlsx", policy_path="/p/d.json", out_dir="/o/d")
    s = s.with_paths("ai", template_path="/t/a.xlsx")
    assert us.save(s, _file(tmp_path)).ok
    r = us.load(_file(tmp_path))
    assert r.status == us.LOAD_OK and r.settings == s
    assert r.settings.paths("daechung").template_path == "/t/d.xlsx" and r.settings.paths("ai").template_path == "/t/a.xlsx"
    assert r.settings.paths("ai").policy_path is None and r.settings.paths("multicultural") == us.ProgramPaths()


def test_saved_json_contains_only_whitelisted_keys(tmp_path):
    us.save(us.UserSettings(last_program="daechung").with_paths("daechung", template_path="/t.xlsx", out_dir="/o"), _file(tmp_path))
    data = json.loads(_file(tmp_path).read_text(encoding="utf-8"))
    assert set(data) == {"version", "last_program", "programs"}
    assert set(data["programs"]["daechung"]) <= {"template_path", "policy_path", "out_dir"}
    text = _file(tmp_path).read_text(encoding="utf-8").lower()
    for forbidden in ("password", "base_date", "source", "비밀번호", "기준일"):
        assert forbidden not in text


def test_unknown_keys_are_dropped_on_load_and_not_written_back(tmp_path):
    f = _file(tmp_path)
    f.write_text(json.dumps({"version": 1, "last_program": "ai", "password": "합성비번", "source_path": "/원본.xlsx",
                             "programs": {"ai": {"template_path": "/t.xlsx", "password": "x", "base_date": "2099.01.01"}, "bogus": {"out_dir": "/o"}}}), encoding="utf-8")
    r = us.load(f)
    assert r.status == us.LOAD_OK and r.settings.paths("ai").template_path == "/t.xlsx" and r.settings == us.UserSettings(last_program="ai").with_paths("ai", template_path="/t.xlsx")
    us.save(r.settings, f)
    assert "합성비번" not in f.read_text(encoding="utf-8") and "bogus" not in f.read_text(encoding="utf-8")


@pytest.mark.parametrize("content", [b"{not json", b"[]", b'{"version": 99, "programs": {}}', b'{"version": 1, "last_program": 5}',
                                     b'{"version": 1, "programs": {"ai": {"template_path": 7}}}', b"\xff\xfe\x00", b"x" * (2 * 1024 * 1024)])
def test_corrupt_file_is_preserved_as_bak_and_defaults_are_used(tmp_path, content):
    f = _file(tmp_path)
    f.write_bytes(content)
    r = us.load(f)
    assert r.status == us.LOAD_RECOVERED and r.settings == us.UserSettings() and r.backup_name == "settings.json.bak"
    assert (tmp_path / "settings.json.bak").read_bytes() == content and not f.exists()


def test_existing_bak_is_never_overwritten(tmp_path):
    (tmp_path / "settings.json.bak").write_bytes(b"older-backup")
    (tmp_path / "settings.json.bak.1").write_bytes(b"older-backup-1")
    f = _file(tmp_path)
    f.write_bytes(b"{broken")
    r = us.load(f)
    assert r.status == us.LOAD_RECOVERED and r.backup_name == "settings.json.bak.2"
    assert (tmp_path / "settings.json.bak").read_bytes() == b"older-backup" and (tmp_path / "settings.json.bak.1").read_bytes() == b"older-backup-1"
    assert (tmp_path / "settings.json.bak.2").read_bytes() == b"{broken"


def test_backup_failure_still_starts_with_defaults(tmp_path, monkeypatch):
    f = _file(tmp_path)
    f.write_bytes(b"{broken")
    monkeypatch.setattr(us, "_preserve", lambda path: (_ for _ in ()).throw(OSError("disk")))
    r = us.load(f)
    assert r.status == us.LOAD_RESET_UNPRESERVED and r.settings == us.UserSettings() and r.backup_name is None
    assert f.read_bytes() == b"{broken"                      # 원본은 지우지 않는다


def test_unreadable_file_is_not_treated_as_corrupt_but_defaults_start(tmp_path, monkeypatch):
    f = _file(tmp_path)
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(us.Path, "read_bytes", lambda self: (_ for _ in ()).throw(PermissionError("denied")))
    r = us.load(f)
    assert r.status == us.LOAD_UNREADABLE and r.settings == us.UserSettings()


def test_load_never_logs_content_or_paths(tmp_path, caplog):
    f = _file(tmp_path)
    f.write_text('{"version": 1, "programs": {"ai": {"template_path": "/비공개/학생홍길동.xlsx", "oops": }}', encoding="utf-8")
    with caplog.at_level(logging.DEBUG):
        r = us.load(f)
    assert r.status == us.LOAD_RECOVERED and caplog.records == []
    assert "홍길동" not in repr(r) and str(tmp_path) not in repr(r)


def test_save_failure_is_reported_without_raising_or_leaking(tmp_path, monkeypatch, caplog):
    def boom(*a, **k):
        raise OSError("C:\\사용자\\홍길동\\settings 쓰기 실패")
    monkeypatch.setattr(us.os, "replace", boom)
    with caplog.at_level(logging.DEBUG):
        res = us.save(us.UserSettings(last_program="ai"), _file(tmp_path))
    assert not res.ok and res.code == us.SAVE_FAILED and "홍길동" not in repr(res) and caplog.records == []
    assert list(tmp_path.iterdir()) == []                    # 임시 파일을 남기지 않는다


def test_save_is_atomic_replace_of_previous_good_file(tmp_path, monkeypatch):
    f = _file(tmp_path)
    us.save(us.UserSettings(last_program="ai"), f)
    before = f.read_bytes()
    monkeypatch.setattr(us.json, "dumps", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    assert not us.save(us.UserSettings(last_program="daechung"), f).ok
    assert f.read_bytes() == before


def test_save_into_missing_folder_creates_it(tmp_path):
    f = tmp_path / "nested" / "dir" / "settings.json"
    assert us.save(us.UserSettings(), f).ok and f.is_file()


def test_settings_file_lives_next_to_default_policy_search_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert us.settings_path() == tmp_path / "ScholarshipPayment" / "settings.json"


def test_invalid_program_codes_are_rejected_at_the_api(tmp_path):
    with pytest.raises(ValueError):
        us.UserSettings().with_paths("nope", template_path="/x")
    assert os.fspath(tmp_path)    # keep fixture used
