"""공용 테스트 도구. 입력 파일은 합성 생성기(tools/synthetic/make_synthetic.py)로만 만든다(실제 자료 금지)."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"

_spec = importlib.util.spec_from_file_location("make_synthetic", ROOT / "tools" / "synthetic" / "make_synthetic.py")
mk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mk)


@pytest.fixture
def synthetic():
    """합성 생성기 모듈(records, build_input 등)."""
    return mk


@pytest.fixture
def fixture_45():
    return FIXTURES / "synthetic_monthly_approval_45.xlsx"


@pytest.fixture
def fixture_3_text_ids():
    return FIXTURES / "synthetic_monthly_approval_3_text_ids.xlsx"


@pytest.fixture
def make_input(tmp_path):
    """합성 입력 파일을 만들고 `mutate(ws)`로 변형한다. 실제 다운로드 원본처럼 B·V·X 열과 합계행 일부는 빈 문자열 셀로 저장한다."""
    counter = {"n": 0}

    def _make(n=45, id_mode="numeric", mutate=None):
        wb = mk.build_input(n, id_mode)
        ws = wb.active
        if mutate is not None:
            mutate(ws)
        total = 3 + n
        coords = [f"{c}{r}" for r in range(3, total) for c in "BVX" if ws[f"{c}{r}"].value is None]
        coords += [f"{c}{total}" for c in "ATUVWX" if ws[f"{c}{total}"].value is None]
        counter["n"] += 1
        path = tmp_path / f"input_{counter['n']}.xlsx"
        wb.save(path)
        mk._inject_empty_strings(path, coords)
        return path

    return _make


@pytest.fixture
def make_mc_input(tmp_path):
    """다문화 형식 합성 입력. students 를 직접 주거나 n 으로 자동 생성하고 `mutate(ws)`로 변형한다."""
    counter = {"n": 0}

    def _make(n=3, students=None, mutate=None):
        wb = mk.build_input_multicultural(students if students is not None else mk.mc_students(n))
        if mutate is not None:
            mutate(wb.active)
        counter["n"] += 1
        path = tmp_path / f"mc_input_{counter['n']}.xlsx"
        wb.save(path)
        return path

    return _make
