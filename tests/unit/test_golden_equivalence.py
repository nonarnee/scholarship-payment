"""리팩터링 전후 출력 동등성(골든): 완전 합성 입력 → 기준 출력(현재 convert()로 만든 정규화 덤프)과 비교한다.
골든 재생성: UPDATE_GOLDEN=1 pytest tests/unit/test_golden_equivalence.py (**리팩터링 전 동작을 기준으로 할 때만** 사용).
고정: 기준일·정책·입력. 비교하지 않는 것: XLSX 바이너리 SHA(압축·메타데이터가 달라질 수 있음).
"""
import dataclasses
import json
import os
from pathlib import Path

import pytest

from scholarship_payment.app import convert as conv
from scholarship_payment.app.convert import convert
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from xlsx_dump import diff, dump, write_golden

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "synthetic_payment_template.xlsx"
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
BASE_DATE = "2099.10.07"
CARRY = ((2, 8 * 60, "9999년08월"), (3, 90, "9999년08월"))
MC_POLICY = dataclasses.replace(SYNTHETIC_POLICY, hourly_rates=(("가상A", 1000), ("가상B", 1500)), hidden_list_columns=("F",))


def build_case(name, make_input, make_mc_input, synthetic, monkeypatch):
    """(program, 입력 경로, 정책)"""
    if name == "daechung_plain":
        return "daechung", make_input(n=5), SYNTHETIC_POLICY
    if name == "daechung_carryover":
        return "daechung", make_input(n=4, extra=CARRY), SYNTHETIC_POLICY
    if name == "ai_carryover":
        monkeypatch.setattr(conv, "AI_HOURLY_RATE", 1000)      # 합성 입력의 시급
        return "ai", make_input(n=4, extra=CARRY), SYNTHETIC_POLICY
    if name == "multicultural_mixed_rates":
        st = synthetic.mc_students(4)
        st[2]["rows"] = [("가상기관최근", "가상B", 5 * 60), ("가상기관이전", "가상A", 6 * 60)]
        return "multicultural", make_mc_input(students=st), MC_POLICY
    raise KeyError(name)


CASES = ["daechung_plain", "daechung_carryover", "ai_carryover", "multicultural_mixed_rates"]


def snapshot(name, result) -> dict:
    d = dump(result.output_path)
    d.update(case=name, filename=result.output_path.name, count=result.count,
             warnings=[f"{w.code}:{w.field}:{w.row}" for w in result.warnings], notes=[f"{n.code}:{n.field}:{n.row}" for n in result.notes])
    return d


def run_convert(name, tmp_path, make_input, make_mc_input, synthetic, monkeypatch) -> dict:
    program, src, policy = build_case(name, make_input, make_mc_input, synthetic, monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    return snapshot(name, convert(program, src, out, TEMPLATE, policy=policy, base_date=BASE_DATE))


def load_golden(name) -> dict:
    return json.loads((GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", CASES)
def test_current_convert_matches_golden(name, tmp_path, make_input, make_mc_input, synthetic, monkeypatch):
    got = run_convert(name, tmp_path, make_input, make_mc_input, synthetic, monkeypatch)
    path = GOLDEN_DIR / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        write_golden(got, path)
    expected = load_golden(name)
    assert diff(got, json.loads(json.dumps(expected))) == [] and got["filename"] == expected["filename"]
    assert len(got["sheets"]) == len(expected["sheets"]) and got["sheet_order"] == expected["sheet_order"]
