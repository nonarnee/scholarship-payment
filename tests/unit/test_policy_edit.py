"""정책 파일 수정(config.policy_edit): 모든 키·값 보존, 시급 두 필드 변환, 추가 시급 키 차단, 백업·원자 교체·충돌 감지, 실패 시 원본 유지.
완전 합성 값만 쓴다. 오류·repr 에는 값이 없고 코드만 있다(DI-13).
"""
import hashlib
import json
import os
from pathlib import Path

import pytest

from scholarship_payment.config import policy_edit as pe
from scholarship_payment.config.policy_builder import RATE_KEYS, build_policy_dict, parse_rate_value, rates_from_fields, save_policy_new
from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.errors import ValidationFailed

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"
VALUES = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
NEW_VALUES = {"list_title": "새 {year}-{month} 명단", "wins_work_name": "새합성근로", "wris_gub_a": "ZZ0101", "wris_gub_b": "ZZ0102", "remit_info": "새적요({month}월)"}
URBAN, RURAL = RATE_KEYS


def make_policy(tmp_path, program="daechung", rates=None, name="policy.json"):
    d = build_policy_dict(TEMPLATE, VALUES, program, rates=rates if program == "multicultural" else None)
    return save_policy_new(tmp_path / name, d)


def codes(excinfo):
    return [e.code for e in excinfo.value.errors]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------- 시급 값 → hourly_rates ----------
def test_rate_fields_become_the_two_key_table_and_nothing_else():
    assert rates_from_fields("18000", "14,000") == {URBAN: 18000, RURAL: 14000}
    assert list(rates_from_fields(" 1 ", "2")) == [URBAN, RURAL]


@pytest.mark.parametrize("bad", ["", " ", "0", "-5", "1.5", "１２３", "만원", "1e3", "12 00", None])
def test_bad_rate_input_is_rejected_with_a_code_only(bad):
    with pytest.raises(ValidationFailed) as e:
        parse_rate_value(bad)
    assert [x.code for x in e.value.errors] == ["POLICY_TYPE"]
    assert "1.5" not in repr(e.value) and "만원" not in str(e.value)


def test_rates_text_path_for_cli_and_tk_still_works(tmp_path):
    d = build_policy_dict(TEMPLATE, VALUES, "multicultural", rates_text="가상A=1000, 가상B=1500")
    assert d["hourly_rates"] == {"가상A": 1000, "가상B": 1500}


def test_rate_dict_path_is_used_for_multicultural_only(tmp_path):
    d = build_policy_dict(TEMPLATE, VALUES, "multicultural", rates={URBAN: 10, RURAL: 20})
    assert d["hourly_rates"] == {URBAN: 10, RURAL: 20} and d["hidden_list_columns"] == ["F"]
    assert "hourly_rates" not in build_policy_dict(TEMPLATE, VALUES, "daechung", rates={URBAN: 10, RURAL: 20})


# ---------- 불러오기 ----------
def test_open_keeps_every_key_value_and_order(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 18000, RURAL: 14000})
    s = pe.open_for_edit(path, "multicultural")
    assert s.data == json.loads(path.read_text(encoding="utf-8")) and list(s.data) == list(json.loads(path.read_text(encoding="utf-8")))
    assert s.sha256 == sha(path) and s.program == "multicultural"
    assert "합성근로" not in repr(s) and "18000" not in repr(s)


def test_open_reports_codes_and_never_touches_unreadable_or_foreign_files(tmp_path):
    for name, content, code in (("bad.json", "{not json", "POLICY_UNREADABLE"), ("list.json", "[1]", "POLICY_NOT_OBJECT")):
        p = tmp_path / name
        p.write_text(content, encoding="utf-8")
        before = p.read_bytes()
        with pytest.raises(ValidationFailed) as e:
            pe.open_for_edit(p, "daechung")
        assert codes(e) == [code] and p.read_bytes() == before
    with pytest.raises(ValidationFailed) as e:
        pe.open_for_edit(tmp_path / "none.json", "daechung")
    assert codes(e) == ["POLICY_FILE_MISSING"]
    assert sorted(x.name for x in tmp_path.iterdir()) == ["bad.json", "list.json"]


def test_open_rejects_unknown_keys_and_missing_structure_keys(tmp_path):
    path = make_policy(tmp_path)
    d = json.loads(path.read_text(encoding="utf-8"))
    (tmp_path / "u.json").write_text(json.dumps({**d, "extra": 1}), encoding="utf-8")
    (tmp_path / "m.json").write_text(json.dumps({k: v for k, v in d.items() if k != "wris_headers"}), encoding="utf-8")
    with pytest.raises(ValidationFailed) as e:
        pe.open_for_edit(tmp_path / "u.json", "daechung")
    assert codes(e) == ["POLICY_KEY_UNKNOWN"]
    with pytest.raises(ValidationFailed) as e:
        pe.open_for_edit(tmp_path / "m.json", "daechung")
    assert codes(e) == ["POLICY_KEY_MISSING"]


def test_a_draft_with_placeholders_can_be_opened_and_fixed(tmp_path):
    path = make_policy(tmp_path)
    d = json.loads(path.read_text(encoding="utf-8"))
    d["wins_work_name"] = "<입력 필요>"
    path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    s = pe.open_for_edit(path, "daechung")
    with pytest.raises(ValidationFailed) as e:                                  # 그대로는 저장할 수 없다
        pe.save_policy_replace(s, pe.edited_data(s, {**VALUES, "wins_work_name": "<입력 필요>"}))
    assert codes(e) == ["POLICY_PLACEHOLDER"]
    r = pe.save_policy_replace(s, pe.edited_data(s, VALUES))
    assert r.changed and load_policy(path).wins_work_name == "합성근로"


@pytest.mark.parametrize("extra", [{"가상A": 1000}, {URBAN: 1, "가상A": 2}, {URBAN: 1, RURAL: 2, "가상A": 3}])
def test_extra_rate_keys_block_editing_for_multicultural_and_change_nothing(tmp_path, extra):
    path = make_policy(tmp_path, "multicultural", extra)
    before = path.read_bytes()
    with pytest.raises(ValidationFailed) as e:
        pe.open_for_edit(path, "multicultural")
    assert codes(e) == ["POLICY_EDIT_EXTRA_RATE_KEYS"] and path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["policy.json"]


def test_rates_of_other_programs_are_not_inspected_and_are_preserved(tmp_path):
    d = build_policy_dict(TEMPLATE, VALUES, "daechung")
    d["hourly_rates"] = {"가상A": 1000}
    p = tmp_path / "p.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    s = pe.open_for_edit(p, "daechung")
    pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert json.loads(p.read_text(encoding="utf-8"))["hourly_rates"] == {"가상A": 1000}


# ---------- 편집 내용 만들기 ----------
def test_edit_replaces_only_user_values_and_keeps_all_other_keys_in_order(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 18000, RURAL: 14000})
    s = pe.open_for_edit(path, "multicultural")
    new = pe.edited_data(s, NEW_VALUES, {"rate_urban": "19000", "rate_rural": "15,000"})
    assert list(new) == list(s.data)
    for k in ("wris_headers", "excluded_sheets", "file_prefix", "hidden_list_columns"):
        assert new[k] == s.data[k]
    assert new["hourly_rates"] == {URBAN: 19000, RURAL: 15000} and new["wins_work_name"] == "새합성근로"
    assert s.data["wins_work_name"] == "합성근로"                                # 원본 객체는 변하지 않는다


def test_rate_key_order_of_the_existing_file_is_kept(tmp_path):
    path = make_policy(tmp_path, "multicultural", {RURAL: 14000, URBAN: 18000})
    s = pe.open_for_edit(path, "multicultural")
    assert list(pe.edited_data(s, VALUES, {"rate_urban": "1", "rate_rural": "2"})["hourly_rates"]) == [RURAL, URBAN]


def test_multicultural_edit_requires_both_valid_rates_and_other_programs_take_none(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 1, RURAL: 2})
    s = pe.open_for_edit(path, "multicultural")
    for rates in (None, {"rate_urban": "5"}, {"rate_urban": "5", "rate_rural": "0"}, {"rate_urban": "x", "rate_rural": "5"}):
        with pytest.raises(ValidationFailed) as e:
            pe.edited_data(s, VALUES, rates)
        assert codes(e) == ["POLICY_TYPE"]
    s2 = pe.open_for_edit(make_policy(tmp_path, "daechung", name="d.json"), "daechung")
    assert "hourly_rates" not in pe.edited_data(s2, VALUES, {"rate_urban": "5", "rate_rural": "5"})


def test_a_multicultural_file_without_rates_can_get_them(tmp_path):
    d = build_policy_dict(TEMPLATE, VALUES, "daechung")
    p = tmp_path / "p.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    s = pe.open_for_edit(p, "multicultural")
    new = pe.edited_data(s, VALUES, {"rate_urban": "1", "rate_rural": "2"})
    assert new["hourly_rates"] == {URBAN: 1, RURAL: 2}


@pytest.mark.parametrize("key", list(VALUES))
def test_blank_user_values_are_rejected(tmp_path, key):
    s = pe.open_for_edit(make_policy(tmp_path), "daechung")
    with pytest.raises(ValidationFailed) as e:
        pe.edited_data(s, {**VALUES, key: "  "})
    assert codes(e) == ["POLICY_KEY_MISSING"]


# ---------- 저장: 재로드·백업·원자 교체 ----------
def test_save_then_reload_round_trips_everything(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 18000, RURAL: 14000})
    s = pe.open_for_edit(path, "multicultural")
    new = pe.edited_data(s, NEW_VALUES, {"rate_urban": "19000", "rate_rural": "15000"})
    r = pe.save_policy_replace(s, new)
    assert r.changed and r.path == path and r.sha256 == sha(path)
    p = load_policy(path)
    assert (p.list_title, p.wins_work_name, p.wris_gub_a, p.wris_gub_b, p.remit_info) == tuple(NEW_VALUES.values())
    assert p.rates() == {URBAN: 19000, RURAL: 15000} and p.hidden_list_columns == ("F",)
    assert json.loads(path.read_text(encoding="utf-8")) == new and list(json.loads(path.read_text(encoding="utf-8"))) == list(new)
    assert pe.open_for_edit(path, "multicultural").sha256 == r.sha256            # 다시 불러올 수 있다


def test_the_previous_content_is_backed_up_byte_for_byte(tmp_path):
    path = make_policy(tmp_path)
    original = path.read_bytes()
    s = pe.open_for_edit(path, "daechung")
    r = pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert r.backup == tmp_path / "policy.json.bak" and r.backup.read_bytes() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["policy.json", "policy.json.bak"]      # 임시 파일이 남지 않는다


def test_existing_backups_are_never_overwritten_or_deleted(tmp_path):
    path = make_policy(tmp_path)
    (tmp_path / "policy.json.bak").write_text("옛 백업 1", encoding="utf-8")
    (tmp_path / "policy.json.bak.1").write_text("옛 백업 2", encoding="utf-8")
    s = pe.open_for_edit(path, "daechung")
    first = pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert first.backup.name == "policy.json.bak.2"
    s = pe.open_for_edit(path, "daechung")
    second = pe.save_policy_replace(s, pe.edited_data(s, VALUES))
    assert second.backup.name == "policy.json.bak.3"
    assert (tmp_path / "policy.json.bak").read_text(encoding="utf-8") == "옛 백업 1" and (tmp_path / "policy.json.bak.1").read_text(encoding="utf-8") == "옛 백업 2"
    assert json.loads(first.backup.read_text(encoding="utf-8"))["wins_work_name"] == "합성근로"
    assert json.loads(second.backup.read_text(encoding="utf-8"))["wins_work_name"] == "새합성근로"


def test_saving_without_changes_writes_nothing_and_makes_no_backup(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 1, RURAL: 2})
    before = path.read_bytes()
    s = pe.open_for_edit(path, "multicultural")
    r = pe.save_policy_replace(s, pe.edited_data(s, {k: s.data[k] for k in VALUES}, {"rate_urban": "1", "rate_rural": "2"}))
    assert not r.changed and r.backup is None and path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["policy.json"]


def test_invalid_result_is_rejected_before_anything_is_written(tmp_path):
    path = make_policy(tmp_path)
    before = path.read_bytes()
    s = pe.open_for_edit(path, "daechung")
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, {**VALUES, "list_title": "{bad}"}))
    assert codes(e) == ["POLICY_TEMPLATE"] and path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["policy.json"]


# ---------- 충돌·실패 ----------
def test_external_change_after_loading_blocks_the_save_and_keeps_their_content(tmp_path):
    path = make_policy(tmp_path)
    s = pe.open_for_edit(path, "daechung")
    theirs = json.loads(path.read_text(encoding="utf-8"))
    theirs["wins_work_name"] = "다른사람이고침"
    path.write_text(json.dumps(theirs, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_CONFLICT"]
    assert json.loads(path.read_text(encoding="utf-8"))["wins_work_name"] == "다른사람이고침"
    assert [p.name for p in tmp_path.iterdir()] == ["policy.json"]               # 백업·임시 파일 없음


def test_a_change_that_keeps_size_and_mtime_is_still_detected_by_the_hash(tmp_path):
    path = make_policy(tmp_path)
    s = pe.open_for_edit(path, "daechung")
    st = path.stat()
    data = bytearray(path.read_bytes())
    i = data.index(b"ZZ0001")
    data[i + 5] = ord("9")                                                     # 같은 길이로 한 글자만 바꾼다
    path.write_bytes(bytes(data))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert path.stat().st_size == st.st_size and path.stat().st_mtime_ns == st.st_mtime_ns
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_CONFLICT"]


def test_a_deleted_file_is_reported_not_recreated(tmp_path):
    path = make_policy(tmp_path)
    s = pe.open_for_edit(path, "daechung")
    path.unlink()
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_FILE_MISSING"] and list(tmp_path.iterdir()) == []


def test_a_change_between_the_check_and_the_replace_is_caught_by_the_second_check(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    s = pe.open_for_edit(path, "daechung")
    real = pe._read_current
    calls = []

    def racing(p):
        calls.append(1)
        data = real(p)
        if len(calls) == 1:                                                     # 첫 확인 직후 다른 프로그램이 파일을 바꾼다
            Path(p).write_text(json.dumps({**json.loads(data), "wins_work_name": "경합"}, ensure_ascii=False), encoding="utf-8")
        return data

    monkeypatch.setattr(pe, "_read_current", racing)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_CONFLICT"] and json.loads(path.read_text(encoding="utf-8"))["wins_work_name"] == "경합"
    assert [p.name for p in tmp_path.iterdir()] == ["policy.json"]


def test_replace_failure_keeps_the_original_and_removes_the_temp_file(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = path.read_bytes()
    s = pe.open_for_edit(path, "daechung")

    def boom(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(pe.os, "replace", boom)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_IO"] and path.read_bytes() == before
    assert not [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert "denied" not in str(e.value) and "denied" not in repr(e.value)
    assert load_policy(path).wins_work_name == "합성근로"                       # 원본은 여전히 정상이다


def test_temp_write_failure_keeps_the_original(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = path.read_bytes()
    s = pe.open_for_edit(path, "daechung")

    real = pe.tempfile.mkstemp

    def boom(*a, **k):
        if "dir" in k:                                                 # 정책 파일 옆의 임시 파일 생성만 실패시킨다(검증용 시스템 임시 파일은 정상)
            raise OSError("disk full")
        return real(*a, **k)

    monkeypatch.setattr(pe.tempfile, "mkstemp", boom)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_IO"] and path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["policy.json"]
    assert "disk full" not in str(e.value) and "disk full" not in repr(e.value)


def test_unwritable_system_temp_for_validation_is_reported_as_a_code(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = path.read_bytes()
    s = pe.open_for_edit(path, "daechung")
    new = pe.edited_data(s, NEW_VALUES)

    def boom(*a, **k):
        raise OSError("no temp")

    monkeypatch.setattr(pe.tempfile, "mkstemp", boom)
    monkeypatch.setattr("scholarship_payment.config.policy_builder.tempfile.mkstemp", boom)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, new)
    assert codes(e) == ["POLICY_EDIT_IO"] and path.read_bytes() == before


def test_backup_failure_stops_before_the_original_is_replaced(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = path.read_bytes()
    s = pe.open_for_edit(path, "daechung")
    real = pe.tempfile.mkstemp

    def deny_backup_temp(*a, **k):
        if k.get("prefix") == ".policy-backup-":                               # 백업용 임시 파일만 만들 수 없다
            raise OSError("no space")
        return real(*a, **k)

    monkeypatch.setattr(pe.tempfile, "mkstemp", deny_backup_temp)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_BACKUP_FAILED"] and path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["policy.json"]


def test_session_and_results_never_expose_policy_values(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 18000, RURAL: 14000})
    s = pe.open_for_edit(path, "multicultural")
    r = pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES, {"rate_urban": "19001", "rate_rural": "15001"}))
    for obj in (s, r):
        text = repr(obj) + str(obj)
        assert not any(v in text for v in ("새합성근로", "ZZ0101", "19001", "15001", "합성근로"))


def test_a_conflict_is_detected_before_any_temp_file_or_backup_is_created(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    s = pe.open_for_edit(path, "daechung")
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    new = pe.edited_data(s, NEW_VALUES)
    real = pe.tempfile.mkstemp

    def no_temp_beside_the_policy(*a, **k):
        assert "dir" not in k, "충돌인데도 정책 파일 옆에 임시 파일을 만들었다"
        return real(*a, **k)

    monkeypatch.setattr(pe.tempfile, "mkstemp", no_temp_beside_the_policy)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, new)
    assert codes(e) == ["POLICY_EDIT_CONFLICT"]


# ================= 백업 무결성 (커밋 전 추가 검증) =================
def _no_backup_names(folder):
    return sorted(p.name for p in Path(folder).iterdir() if ".bak" in p.name)


def _only(folder, *names):
    return sorted(p.name for p in Path(folder).iterdir()) == sorted(names)


def test_backup_sha256_equals_the_original_taken_right_before_the_edit(tmp_path):
    path = make_policy(tmp_path, "multicultural", {URBAN: 18000, RURAL: 14000})
    before = sha(path)
    s = pe.open_for_edit(path, "multicultural")
    r = pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES, {"rate_urban": "19000", "rate_rural": "15000"}))
    assert sha(r.backup) == before == s.sha256 and sha(path) != before and sha(path) == r.sha256
    assert load_policy(r.backup).wins_work_name == "합성근로"                       # 백업은 그대로 정책으로 읽을 수 있다


def test_a_failure_while_writing_the_backup_leaves_no_backup_and_does_not_replace_the_original(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = sha(path)
    s = pe.open_for_edit(path, "daechung")
    replaced = []
    real_replace = pe.os.replace
    monkeypatch.setattr(pe.os, "replace", lambda *a, **k: (replaced.append(a), real_replace(*a, **k))[1])

    def half_then_fail(fd, data):
        with os.fdopen(fd, "wb") as f:
            f.write(data[: len(data) // 2])                                        # 절반만 쓰고 실패한다
        raise OSError("disk full")

    monkeypatch.setattr(pe, "_write_synced", half_then_fail)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_BACKUP_FAILED"] and replaced == []
    assert sha(path) == before and load_policy(path).wins_work_name == "합성근로"
    assert _no_backup_names(tmp_path) == [] and _only(tmp_path, "policy.json")      # 불완전한 백업도 임시 파일도 남지 않는다


def test_a_backup_whose_content_differs_from_the_original_is_never_accepted(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = sha(path)
    s = pe.open_for_edit(path, "daechung")

    def silently_corrupt(fd, data):
        with os.fdopen(fd, "wb") as f:
            f.write(data[:-1] + b"X")                                              # 오류 없이 한 바이트가 다르게 기록된 경우

    monkeypatch.setattr(pe, "_write_synced", silently_corrupt)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_BACKUP_FAILED"] and sha(path) == before and _only(tmp_path, "policy.json")


def test_existing_good_backups_survive_a_failed_backup_attempt_byte_for_byte(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    old1, old2 = "옛 백업 1(길이가 다른 내용)", "옛 백업 2"
    (tmp_path / "policy.json.bak").write_text(old1, encoding="utf-8")
    (tmp_path / "policy.json.bak.1").write_text(old2, encoding="utf-8")
    snap = {n: sha(tmp_path / n) for n in ("policy.json", "policy.json.bak", "policy.json.bak.1")}
    s = pe.open_for_edit(path, "daechung")

    def fail(fd, data):
        os.close(fd)
        raise OSError("io")

    monkeypatch.setattr(pe, "_write_synced", fail)
    with pytest.raises(ValidationFailed):
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert {n: sha(tmp_path / n) for n in snap} == snap and _only(tmp_path, *snap)


def test_a_failing_exclusive_create_never_deletes_an_existing_backup_of_a_different_size(tmp_path, monkeypatch):
    """회귀: 만들기에 실패했을 때 '파일이 있고 크기가 다르면 지우는' 정리가 기존 정상 백업을 지울 수 있었다."""
    path = make_policy(tmp_path)
    (tmp_path / "policy.json.bak").write_text("기존 정상 백업", encoding="utf-8")
    s = pe.open_for_edit(path, "daechung")
    real_link = pe.os.link

    def no_link(*a, **k):
        raise OSError(1, "operation not permitted")                                # 하드링크를 쓸 수 없는 저장소

    real_open = pe.os.open

    def no_create(file, *a, **k):
        if str(file).endswith((".bak", ".bak.1")):                                 # 백업 최종 이름을 새로 만들 수 없다(임시 파일은 정상)
            raise PermissionError("denied")
        return real_open(file, *a, **k)

    monkeypatch.setattr(pe.os, "link", no_link)
    monkeypatch.setattr(pe.os, "open", no_create)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    monkeypatch.setattr(pe.os, "link", real_link)
    assert codes(e) == ["POLICY_EDIT_BACKUP_FAILED"] and (tmp_path / "policy.json.bak").read_text(encoding="utf-8") == "기존 정상 백업"
    assert _only(tmp_path, "policy.json", "policy.json.bak")


def test_storage_without_hard_links_still_gets_a_complete_backup_and_never_overwrites(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = path.read_bytes()
    (tmp_path / "policy.json.bak").write_text("옛 백업", encoding="utf-8")
    s = pe.open_for_edit(path, "daechung")

    def no_link(*a, **k):
        raise OSError(1, "operation not permitted")

    monkeypatch.setattr(pe.os, "link", no_link)
    r = pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert r.backup.name == "policy.json.bak.1" and r.backup.read_bytes() == before
    assert (tmp_path / "policy.json.bak").read_text(encoding="utf-8") == "옛 백업" and _only(tmp_path, "policy.json", "policy.json.bak", "policy.json.bak.1")


def test_copy_failure_on_a_storage_without_hard_links_removes_only_its_own_partial_backup(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = sha(path)
    (tmp_path / "policy.json.bak").write_text("옛 백업", encoding="utf-8")
    s = pe.open_for_edit(path, "daechung")
    real_write = pe._write_synced
    calls = []

    def no_link(*a, **k):
        raise OSError(1, "operation not permitted")

    def fail_on_second(fd, data):                                                  # 첫 호출(임시 파일)은 정상, 둘째(직접 복사)에서 절반만 쓰고 실패
        calls.append(1)
        if len(calls) == 1:
            return real_write(fd, data)
        with os.fdopen(fd, "wb") as f:
            f.write(data[:10])
        raise OSError("io")

    monkeypatch.setattr(pe.os, "link", no_link)
    monkeypatch.setattr(pe, "_write_synced", fail_on_second)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_BACKUP_FAILED"] and sha(path) == before
    assert (tmp_path / "policy.json.bak").read_text(encoding="utf-8") == "옛 백업" and _only(tmp_path, "policy.json", "policy.json.bak")


def test_replace_failure_keeps_the_original_intact_and_leaves_a_complete_matching_backup(tmp_path, monkeypatch):
    path = make_policy(tmp_path)
    before = sha(path)
    s = pe.open_for_edit(path, "daechung")

    def boom(*a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(pe.os, "replace", boom)
    with pytest.raises(ValidationFailed) as e:
        pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert codes(e) == ["POLICY_EDIT_IO"] and sha(path) == before and load_policy(path).wins_work_name == "합성근로"
    assert _only(tmp_path, "policy.json", "policy.json.bak") and sha(tmp_path / "policy.json.bak") == before   # 완전한 백업만 남는다


def test_backup_file_permissions_follow_the_original_when_possible(tmp_path):
    if os.name == "nt":
        pytest.skip("POSIX 권한만 확인한다")
    path = make_policy(tmp_path)
    os.chmod(path, 0o640)
    s = pe.open_for_edit(path, "daechung")
    r = pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES))
    assert (r.backup.stat().st_mode & 0o777) == 0o640 and (path.stat().st_mode & 0o777) == 0o640


# ================= 수정 후 이전 Prepared 로는 생성할 수 없다 =================
def test_a_prepared_from_before_the_edit_cannot_generate_files(tmp_path, make_input):
    from scholarship_payment.app import convert as conv
    from test_golden_equivalence import BASE_DATE
    policy_path = make_policy(tmp_path)
    tpl = tmp_path / "tpl.xlsx"
    tpl.write_bytes(TEMPLATE.read_bytes())
    out = tmp_path / "out"
    out.mkdir()
    prepared = conv.prepare("daechung", make_input(n=3), tpl, policy=load_policy(policy_path), base_date=BASE_DATE,
                            policy_source=conv.PolicySource(policy_path, conv.fingerprint_file(policy_path)))
    s = pe.open_for_edit(policy_path, "daechung")
    assert pe.save_policy_replace(s, pe.edited_data(s, NEW_VALUES)).changed
    with pytest.raises(conv.ConversionFailed) as e:
        conv.finish(prepared, out)
    assert e.value.stage == "changed" and codes(e) == ["INPUT_FILE_CHANGED"] and list(out.iterdir()) == []


def test_tk_and_cli_call_style_with_positional_rates_text_is_unchanged(tmp_path):
    """gui/app.py 와 __main__.py 는 make_policy_file(템플릿, 값, 출력, 사업, rates_text) 를 위치 인자로 부른다."""
    from scholarship_payment.config.policy_builder import make_policy_file
    out = make_policy_file(TEMPLATE, VALUES, tmp_path / "p.json", "multicultural", "가상A=1000, 가상B=1500")
    assert load_policy(out).rates() == {"가상A": 1000, "가상B": 1500}
    with pytest.raises(ValidationFailed):
        make_policy_file(TEMPLATE, VALUES, tmp_path / "q.json", "multicultural", "형식이 틀림")
    assert not (tmp_path / "q.json").exists()
