"""정책 파일 종단: 다른 이름·머리글을 가진 템플릿은 대응 정책이 있을 때만 변환된다. 합성 데이터만 사용."""
import importlib.util
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from scholarship_payment import __main__ as cli
from scholarship_payment.config.policy_file import PLACEHOLDER

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates" / "synthetic_payment_template.xlsx"
EXAMPLE = ROOT / "templates" / "synthetic_policy.json"
_spec = importlib.util.spec_from_file_location("derive_policy", ROOT / "tools" / "policy" / "derive_policy.py")
derive_policy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(derive_policy)

NEW_HEADERS = ["가상헤더%02d" % i for i in range(1, 11)]


@pytest.fixture
def variant(tmp_path):
    """이력 시트 이름과 WRIS 머리글이 합성 기본값과 다른 템플릿 + 그에 맞는 정책."""
    wb = load_workbook(TEMPLATE)
    wb["업로드 결과(이력)"].title = "가상이력시트"
    for c, h in enumerate(NEW_HEADERS, 1):
        wb["WRIS"].cell(1, c).value = h
    tpl = tmp_path / "variant_template.xlsx"
    wb.save(tpl)
    pol = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    pol.update(wris_headers=NEW_HEADERS, excluded_sheets=["가상이력시트"], wins_work_name="가상근로구분", file_prefix="가상접두")
    pp = tmp_path / "policy.json"
    pp.write_text(json.dumps(pol, ensure_ascii=False), encoding="utf-8")
    return tpl, pp


def run(inp, out, tpl, policy=None, extra=()):
    args = ["convert", "--program", "daechung", "--input", str(inp), "--out-dir", str(out), "--template", str(tpl), *extra]
    if policy:
        args += ["--policy", str(policy)]
    return cli.main(args)


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


def test_without_policy_the_variant_template_is_blocked_with_a_hint(make_input, variant, out, capsys):
    assert run(make_input(n=3), out, variant[0]) == 1
    err = capsys.readouterr().err
    assert "TEMPLATE_LAYOUT" in err and "--policy" in err and list(out.iterdir()) == []


def test_with_policy_the_variant_template_converts_and_uses_policy_constants(make_input, variant, out, capsys):
    assert run(make_input(n=3), out, variant[0], variant[1]) == 0
    (path,) = list(out.iterdir())
    assert path.name.startswith("가상접두_")
    wb = load_workbook(path)
    assert wb["WINS"]["A2"].value == "가상근로구분" and wb.sheetnames == ["지급대상자명단(9월)", "WINS", "WRIS", "은행코드"]
    assert [c.value for c in wb["WRIS"][1]] == NEW_HEADERS


def test_bad_policy_file_blocks_before_anything_is_read_or_written(make_input, variant, out, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    d = json.loads(variant[1].read_text(encoding="utf-8"))
    d["wins_work_name"] = PLACEHOLDER
    bad.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    assert run(make_input(n=3), out, variant[0], bad) == 1
    err = capsys.readouterr().err
    assert "POLICY_PLACEHOLDER" in err and "policy" in err and list(out.iterdir()) == []


def test_policy_values_never_appear_in_cli_output(make_input, variant, out, capsys):
    run(make_input(n=3), out, variant[0], variant[1])
    cap = capsys.readouterr()
    assert "가상근로구분" not in cap.out + cap.err


def test_example_policy_with_synthetic_template(make_input, out, capsys):
    assert run(make_input(n=2), out, TEMPLATE, EXAMPLE) == 0


# ------------------------------------------------------------------ derive_policy (로컬 전용 도구)
def test_derive_reads_what_it_can_and_leaves_placeholders(variant, tmp_path, monkeypatch, capsys):
    root = tmp_path / "repo"
    (root / "private").mkdir(parents=True)
    monkeypatch.setattr(derive_policy, "ROOT", root)
    out = root / "private" / "p.json"
    assert derive_policy.main([str(variant[0]), str(out)]) == 0
    d = json.loads(out.read_text(encoding="utf-8"))
    assert d["wris_headers"] == NEW_HEADERS and d["excluded_sheets"] == ["가상이력시트"]
    assert [k for k, v in d.items() if v == PLACEHOLDER] == ["list_title", "wins_work_name", "wris_gub_a", "wris_gub_b", "remit_info"]
    text = capsys.readouterr().out
    assert "가상헤더" not in text and "가상이력시트" not in text
    # 자리표시자가 남은 초안은 로더가 차단한다
    assert cli.main(["convert", "--program", "daechung", "--input", "x", "--out-dir", str(tmp_path), "--policy", str(out)]) == 1


def test_derive_refuses_outside_private_and_never_overwrites(variant, tmp_path, monkeypatch):
    root = tmp_path / "repo"
    (root / "private").mkdir(parents=True)
    monkeypatch.setattr(derive_policy, "ROOT", root)
    assert derive_policy.main([str(variant[0]), str(tmp_path / "elsewhere.json")]) == 2
    target = root / "private" / "p.json"
    target.write_text("keep")
    assert derive_policy.main([str(variant[0]), str(target)]) == 2 and target.read_text() == "keep"


def test_bad_policy_never_falls_back_to_the_synthetic_policy(make_input, out, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    assert run(make_input(n=2), out, TEMPLATE, bad) == 1      # 합성 템플릿이라 폴백했다면 성공했을 조합
    assert list(out.iterdir()) == []
