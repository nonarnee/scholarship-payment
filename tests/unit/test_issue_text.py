"""오류·경고·참고 코드 → 한국어 설명과 조치 안내. 코드와 업무 규칙은 바꾸지 않고 문구만 대응시킨다."""
import re
from pathlib import Path

from scholarship_payment.ui import issue_text as it

SRC = Path(__file__).resolve().parents[2] / "src" / "scholarship_payment"


def codes_in_engine() -> set[str]:
    found = set()
    for p in SRC.rglob("*.py"):
        rel = p.relative_to(SRC).parts
        if rel[0] == "ui" or p.name == "user_settings.py":
            continue
        text = p.read_text(encoding="utf-8")
        found |= set(re.findall(r'ValidationError\(\s*"([A-Z][A-Z_]+)"', text))
        found |= set(re.findall(r'_fail\(\s*"([A-Z][A-Z_]+)"', text))
        found |= set(re.findall(r'^[A-Z_]+ *= *"([A-Z][A-Z_]{5,})"$', text, re.M)) if p.name == "source.py" else set()
        if p.name == "convert.py":                                                      # CHANGED_CODE, UNREADABLE_CODE = "…", "…" 처럼 상수로 정의한 코드
            found |= set(re.findall(r'"(INPUT_[A-Z_]+)"', text))
    return found


def test_every_engine_code_has_a_korean_description_and_an_action():
    missing = sorted(c for c in codes_in_engine() if c not in it.CATALOG)
    assert missing == []
    for code, entry in it.CATALOG.items():
        assert entry.title.strip() and entry.action.strip(), code
        assert re.search(r"[가-힣]", entry.title) and re.search(r"[가-힣]", entry.action), code


def test_catalog_has_no_codes_the_engine_does_not_know():
    extra = sorted(set(it.CATALOG) - codes_in_engine())
    assert extra == []


def test_unknown_code_is_shown_with_its_code_and_a_generic_action():
    d = it.describe("SOME_FUTURE_CODE")
    assert "SOME_FUTURE_CODE" in d.title and d.action


def test_texts_never_contain_placeholders_or_personal_data_markers():
    for code, e in it.CATALOG.items():
        for text in (e.title, e.action):
            assert "{" not in text and "}" not in text and "학번:" not in text and "성명:" not in text, code


def test_location_text_lists_rows_then_fields_and_truncates():
    assert it.location_text((5, 7), ()) == "행 5, 7"
    assert it.location_text((), ("C1", "D1")) == "위치 C1, D1"
    long = tuple(range(1, 40))
    assert it.location_text(long, ()).endswith("외 31건") and it.location_text(long, ()).count(",") == 7
    assert it.location_text((), ()) == ""


def test_severity_labels_are_distinct():
    assert len({it.SEVERITY_LABEL[k] for k in ("error", "warning", "note")}) == 3
