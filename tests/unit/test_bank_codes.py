"""은행코드 표. 정확 일치만 허용하고, 시스템(WINS/WRIS)별로 없거나 모호하면 차단한다(결정). 추정·유사 매칭 금지."""
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from scholarship_payment.core.bank_codes import BankCodes, BankCodeTable
from scholarship_payment.errors import ValidationError

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "synthetic_payment_template.xlsx"


def resolve(table, name, system):
    with pytest.raises(ValidationError) as ei:
        table.resolve(name, system)
    return ei.value


def test_exact_match_returns_both_codes():
    t = BankCodeTable([("가상은행A", "111", "990001")])
    assert t.resolve("가상은행A", "wins") == "111"
    assert t.resolve("가상은행A", "wris") == "990001"
    assert t.codes("가상은행A") == BankCodes(wins="111", wris="990001")


def test_codes_keep_their_cell_type():
    t = BankCodeTable([("가상은행A", 11, "0099")])
    assert t.resolve("가상은행A", "wins") == 11 and type(t.resolve("가상은행A", "wins")) is int
    assert t.resolve("가상은행A", "wris") == "0099"        # 선행 0 보존


def test_unknown_bank_is_missing_for_both_systems():
    t = BankCodeTable([("가상은행A", "1", "2")])
    assert (resolve(t, "가상은행B", "wins").code, resolve(t, "가상은행B", "wins").field) == ("BANK_CODE_MISSING", "wins_bank_code")
    assert (resolve(t, "가상은행B", "wris").code, resolve(t, "가상은행B", "wris").field) == ("BANK_CODE_MISSING", "wris_bank_code")


@pytest.mark.parametrize("near", ["가상은행a", "가상은행 A", "가상은행", "가상은행AA", ""])
def test_no_fuzzy_matching(near):
    assert resolve(BankCodeTable([("가상은행A", "1", "2")]), near, "wins").code == "BANK_CODE_MISSING"


def test_empty_code_blocks_only_that_system():
    t = BankCodeTable([("가상은행A", None, "990001"), ("가상은행B", "", "  ")])
    assert resolve(t, "가상은행A", "wins").code == "BANK_CODE_MISSING"
    assert t.resolve("가상은행A", "wris") == "990001"
    assert resolve(t, "가상은행B", "wins").code == "BANK_CODE_MISSING"
    assert resolve(t, "가상은행B", "wris").code == "BANK_CODE_MISSING"


def test_duplicate_name_with_different_codes_is_ambiguous():
    t = BankCodeTable([("가상은행A", "1", "7"), ("가상은행A", "2", "7")])
    assert resolve(t, "가상은행A", "wins").code == "BANK_CODE_AMBIGUOUS"
    assert t.resolve("가상은행A", "wris") == "7"          # WRIS 코드는 같으므로 모호하지 않음(시스템별 판정)


def test_duplicate_name_with_one_empty_code_is_ambiguous():
    t = BankCodeTable([("가상은행A", "1", "7"), ("가상은행A", None, "7")])
    assert resolve(t, "가상은행A", "wins").code == "BANK_CODE_AMBIGUOUS"


def test_identical_duplicate_rows_are_not_ambiguous():
    t = BankCodeTable([("가상은행A", "1", "7"), ("가상은행A", "1", "7")])
    assert t.resolve("가상은행A", "wins") == "1"


def test_unknown_system_name_is_rejected():
    with pytest.raises(ValueError):
        BankCodeTable([]).resolve("가상은행A", "other")


def test_errors_never_contain_the_bank_name():
    e = resolve(BankCodeTable([]), "가상비밀은행", "wins")
    assert "가상비밀은행" not in str(e) + repr(e)


def test_from_synthetic_template_workbook():
    t = BankCodeTable.from_workbook(load_workbook(TEMPLATE))
    assert t.resolve("가상은행02", "wris") == "990002"
    assert resolve(t, "가상은행09", "wins").code == "BANK_CODE_MISSING"      # 합성표의 WINS 공란
    assert t.resolve("가상은행01", "wins") == 901                           # 중복 행이 동일 코드면 모호하지 않음


def test_from_workbook_missing_sheet():
    wb = Workbook()
    with pytest.raises(ValidationError) as ei:
        BankCodeTable.from_workbook(wb)
    assert ei.value.code == "BANK_SHEET_MISSING"


def test_from_workbook_ignores_rows_without_a_name_and_header():
    wb = Workbook()
    ws = wb.active
    ws.title = "은행코드"
    ws.append(["a", "은행명", "WINS", "WRIS"])
    ws.append(["x", None, "1", "2"])
    ws.append(["x", "가상은행A", "3", "4"])
    t = BankCodeTable.from_workbook(wb)
    assert t.resolve("가상은행A", "wins") == "3"
    assert resolve(t, "은행명", "wins").code == "BANK_CODE_MISSING"      # 머리글 행은 데이터가 아니다
