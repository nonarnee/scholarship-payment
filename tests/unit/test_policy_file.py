"""정책 파일 로더. 실제 상수가 코드에 없으므로 파일이 유일한 출처다 — 빠진 값이 합성 기본값으로 조용히 채워지면 안 된다."""
import json
from pathlib import Path

import pytest

from scholarship_payment.config.policy import SYNTHETIC_POLICY, OutputPolicy
from scholarship_payment.config.policy_file import PLACEHOLDER, load_policy, policy_to_dict
from scholarship_payment.errors import ValidationFailed

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "templates" / "synthetic_policy.json"


def write(tmp_path, data, name="policy.json"):
    p = tmp_path / name
    p.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def base():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def fail(path):
    with pytest.raises(ValidationFailed) as ei:
        load_policy(path)
    return {(e.code, e.field) for e in ei.value.errors}, ei.value


def test_example_file_equals_the_synthetic_policy():
    assert load_policy(EXAMPLE) == SYNTHETIC_POLICY


def test_roundtrip_through_dict(tmp_path):
    pol = OutputPolicy(list_title="제목 {year}/{month}", wins_work_name="W", wris_gub_a="A", wris_gub_b="B", remit_info="R{month}",
                       wris_headers=("h1", "h2"), excluded_sheets=("x", "y"), file_prefix="접두")
    assert load_policy(write(tmp_path, policy_to_dict(pol))) == pol


def test_file_missing_and_unreadable(tmp_path):
    assert fail(tmp_path / "없음.json")[0] == {("POLICY_FILE_MISSING", "file")}
    assert fail(write(tmp_path, "{not json"))[0] == {("POLICY_UNREADABLE", "file")}
    bad = tmp_path / "b.json"
    bad.write_bytes(b"\xff\xfe\x00bad")
    assert fail(bad)[0] == {("POLICY_UNREADABLE", "file")}
    assert fail(write(tmp_path, "[1,2]"))[0] == {("POLICY_NOT_OBJECT", "file")}


@pytest.mark.parametrize("key", list(json.loads(EXAMPLE.read_text(encoding="utf-8"))))
def test_every_key_is_required(tmp_path, key):
    d = base()
    del d[key]
    assert fail(write(tmp_path, d))[0] == {("POLICY_KEY_MISSING", key)}


def test_unknown_keys_are_rejected_without_echoing_them(tmp_path):
    d = base()
    d["오타키비밀"] = 1
    codes, exc = fail(write(tmp_path, d))
    assert codes == {("POLICY_KEY_UNKNOWN", "keys")} and "오타키비밀" not in str(exc) + repr(exc)


@pytest.mark.parametrize("key,value", [
    ("list_title", 1), ("list_title", ""), ("wins_work_name", None), ("wris_gub_a", "  "), ("remit_info", ["x"]),
    ("wris_headers", "abc"), ("wris_headers", []), ("wris_headers", ["a", 1]), ("wris_headers", ["a", ""]),
    ("excluded_sheets", "x"), ("excluded_sheets", [1]), ("excluded_sheets", [""]), ("file_prefix", 5),
])
def test_type_errors(tmp_path, key, value):
    d = base()
    d[key] = value
    assert fail(write(tmp_path, d))[0] == {("POLICY_TYPE", key)}


def test_excluded_sheets_may_be_empty(tmp_path):
    d = base()
    d["excluded_sheets"] = []
    assert load_policy(write(tmp_path, d)).excluded_sheets == ()


@pytest.mark.parametrize("key", ["list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info", "file_prefix"])
def test_placeholder_values_are_rejected(tmp_path, key):
    d = base()
    d[key] = PLACEHOLDER
    assert fail(write(tmp_path, d))[0] == {("POLICY_PLACEHOLDER", key)}


def test_placeholder_inside_lists_is_rejected(tmp_path):
    d = base()
    d["wris_headers"] = ["a", PLACEHOLDER]
    assert fail(write(tmp_path, d))[0] == {("POLICY_PLACEHOLDER", "wris_headers")}


@pytest.mark.parametrize("text", ["{name}", "{0}", "{}", "{year.real}", "{year!r}", "{year:>5}", "{month[0]}", "{", "}"])
@pytest.mark.parametrize("key", ["list_title", "remit_info"])
def test_only_year_and_month_placeholders_are_allowed(tmp_path, key, text):
    d = base()
    d[key] = text
    assert fail(write(tmp_path, d))[0] == {("POLICY_TEMPLATE", key)}


@pytest.mark.parametrize("prefix", ["a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a|b", ".숨김", "a..b", "a\nb", "a. "])
def test_file_prefix_must_be_a_safe_file_name_part(tmp_path, prefix):
    d = base()
    d["file_prefix"] = prefix
    assert fail(write(tmp_path, d))[0] == {("POLICY_FILE_PREFIX", "file_prefix")}


def test_all_problems_are_reported_together_and_without_values(tmp_path):
    d = base()
    d["wins_work_name"], d["list_title"], d["file_prefix"] = PLACEHOLDER, "{비밀치환자}", "비밀/접두"
    del d["wris_gub_a"]
    codes, exc = fail(write(tmp_path, d))
    assert len(codes) == 4
    assert not any(s in str(exc) + repr(exc) for s in ("비밀치환자", "비밀/접두"))


def test_values_with_surrounding_spaces_are_kept_exactly(tmp_path):
    d = base()
    d["wins_work_name"] = " 값 "
    assert load_policy(write(tmp_path, d)).wins_work_name == " 값 "
