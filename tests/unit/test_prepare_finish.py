"""convert() 를 prepare()/finish() 로 나눈 계약: 비생성·불변·변경 감지(SHA-256)·실패 시 부분 파일 없음·골든 동등성·비노출.
입력·템플릿·정책은 모두 합성이다. 기존 convert() 의 동작(오류 단계·코드 순서)은 그대로여야 한다."""
import dataclasses
import hashlib
import inspect
import os
import pickle
import tempfile
from pathlib import Path

import pytest
from msoffcrypto.format.ooxml import OOXMLFile
from openpyxl import Workbook, load_workbook

from scholarship_payment.app import convert as conv
from scholarship_payment.app.convert import ConversionFailed, FileFingerprint, PolicySource, Prepared, check_unchanged, convert, finish, prepare
from scholarship_payment.config.policy import SYNTHETIC_POLICY
from scholarship_payment.config.policy_builder import make_policy_file
from scholarship_payment.config.policy_file import load_policy
from scholarship_payment.core.bank_codes import FIRST_DATA_ROW
from xlsx_dump import diff, dump

from test_golden_equivalence import BASE_DATE, CASES, MC_POLICY, TEMPLATE, build_case, load_golden, snapshot

PW = "가짜-pw-0000!"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tree(*dirs):
    return sorted(str(p) for d in dirs for p in Path(d).rglob("*"))


@pytest.fixture
def out(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return d


@pytest.fixture
def tpl(tmp_path):
    p = tmp_path / "tpl.xlsx"
    p.write_bytes(TEMPLATE.read_bytes())
    return p


@pytest.fixture
def policy_path(tmp_path):
    vals = {"list_title": "합성 {year}년 {month}월 명단", "wins_work_name": "합성근로", "wris_gub_a": "ZZ0001", "wris_gub_b": "ZZ0002", "remit_info": "합성적요({month}월)"}
    return make_policy_file(TEMPLATE, vals, tmp_path / "policy_daechung.json", "daechung")


def prep(src, tpl, **kw):
    return prepare("daechung", src, tpl, base_date=BASE_DATE, **kw)


# ---------- 골든: 분리 후에도 출력이 기준과 같다 ----------
@pytest.mark.parametrize("name", CASES)
def test_finish_of_prepare_matches_golden(name, tmp_path, make_input, make_mc_input, synthetic, monkeypatch):
    program, src, policy = build_case(name, make_input, make_mc_input, synthetic, monkeypatch)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = finish(prepare(program, src, TEMPLATE, policy=policy, base_date=BASE_DATE), out_dir)
    got = snapshot(name, result)
    expected = load_golden(name)
    assert diff(got, expected) == [] and got["filename"] == expected["filename"] and got["sheet_order"] == expected["sheet_order"]


def test_convert_is_exactly_finish_of_prepare(tmp_path, make_input):
    src = make_input(n=4)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    r1 = convert("daechung", src, a, TEMPLATE, base_date=BASE_DATE)
    r2 = finish(prepare("daechung", src, TEMPLATE, base_date=BASE_DATE), b)
    assert r1.count == r2.count and [x.code for x in r1.warnings] == [x.code for x in r2.warnings] and r1.output_path.name == r2.output_path.name
    assert diff(dump(r1.output_path), dump(r2.output_path)) == []


def test_public_signatures_keep_the_old_contract():
    params = list(inspect.signature(convert).parameters)
    assert params == ["program", "input_path", "out_dir", "template_path", "policy", "base_date", "today", "password"]
    assert "out_dir" not in inspect.signature(prepare).parameters                  # 미리보기에는 저장 위치 개념이 없다
    assert list(inspect.signature(finish).parameters) == ["prepared", "out_dir"]


# ---------- prepare(): 파일을 만들지 않고 입력을 바꾸지 않는다 ----------
def test_prepare_creates_no_files_anywhere_and_never_saves(tmp_path, make_input, tpl, out, monkeypatch):
    src = make_input(n=4)
    sys_tmp = tmp_path / "sys_tmp"
    sys_tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(sys_tmp))                      # 시스템 임시 폴더를 이 테스트 전용으로 바꿔 그 안의 생성도 감시한다
    before = tree(tmp_path)
    monkeypatch.setattr(conv, "save_new", lambda *a, **k: (_ for _ in ()).throw(AssertionError("save_new called")))
    monkeypatch.setattr(conv, "build_workbook", lambda *a, **k: (_ for _ in ()).throw(AssertionError("build_workbook called")))
    monkeypatch.setattr(tempfile, "mkstemp", lambda *a, **k: (_ for _ in ()).throw(AssertionError("mkstemp called")))
    monkeypatch.setattr(Workbook, "save", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Workbook.save called")))
    p = prep(src, tpl)
    assert isinstance(p, Prepared) and tree(tmp_path) == before and list(out.iterdir()) == [] and list(sys_tmp.iterdir()) == []


def test_prepare_leaves_source_template_and_policy_bytes_untouched(tmp_path, make_input, tpl, policy_path):
    src = make_input(n=4)
    h = (sha(src), sha(tpl), sha(policy_path))
    mt = (os.stat(src).st_mtime_ns, os.stat(tpl).st_mtime_ns)
    policy = load_policy(policy_path)
    prepare("daechung", src, tpl, policy=policy, base_date=BASE_DATE, policy_source=PolicySource(policy_path, conv.fingerprint_file(policy_path)))
    assert (sha(src), sha(tpl), sha(policy_path)) == h and (os.stat(src).st_mtime_ns, os.stat(tpl).st_mtime_ns) == mt


def test_finish_leaves_inputs_untouched_and_does_not_modify_prepared_data(tmp_path, make_input, tpl, out):
    src = make_input(n=4)
    p = prep(src, tpl)
    before = (pickle.dumps((p._validated, p._source_totals, p.policy, p.warnings, p.notes)), sha(src), sha(tpl))
    finish(p, out)
    finish(p, out)                                                           # 같은 Prepared 로 두 번 → 두 번째는 _2 파일
    assert (pickle.dumps((p._validated, p._source_totals, p.policy, p.warnings, p.notes)), sha(src), sha(tpl)) == before
    assert sorted(x.name for x in out.iterdir()) == ["지급명단_DAECHUNG_9999_09.xlsx", "지급명단_DAECHUNG_9999_09_2.xlsx"]


# ---------- 불변성: frozen 만 믿지 않고 내부까지 확인 ----------
def _assert_deep_immutable(obj, path="obj"):
    leaf = (str, int, float, bool, type(None))
    if isinstance(obj, leaf):
        return
    if isinstance(obj, (tuple, frozenset)):
        for i, x in enumerate(obj):
            _assert_deep_immutable(x, f"{path}[{i}]")
        return
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        assert obj.__dataclass_params__.frozen, f"{path}: 가변 dataclass"
        for f in dataclasses.fields(obj):
            _assert_deep_immutable(getattr(obj, f.name), f"{path}.{f.name}")
        return
    raise AssertionError(f"{path}: 가변 또는 알 수 없는 타입 {type(obj).__name__}")


def test_prepared_holds_only_deeply_immutable_data(make_input, tpl):
    p = prep(make_input(n=4, extra=((2, 480, "9999년08월"),)), tpl)
    for f in dataclasses.fields(p):
        _assert_deep_immutable(getattr(p, f.name), f.name)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.base_date = "2000.01.01"
    with pytest.raises((AttributeError, TypeError)):
        p._validated.rows[0].row.pay_amount = 1
    with pytest.raises((AttributeError, TypeError)):
        p._validated.rows[0] = None


def test_prepared_has_no_password_or_workbook_fields(make_input, tpl):
    names = {f.name for f in dataclasses.fields(prep(make_input(n=2), tpl))}
    assert not [n for n in names if "password" in n or "workbook" in n or n in ("wb", "template_bytes")]


def test_repr_and_pickle_text_expose_no_paths_or_payment_values(tmp_path, make_input, tpl):
    src = make_input(n=4)
    p = prep(src, tpl)
    text = repr(p) + repr(p.source_fp) + repr(p.template_fp)
    row = p._validated.rows[0].row
    for secret in (str(src), str(tpl), str(tmp_path), row.student_id, row.name, row.account_no, str(row.pay_amount)):
        assert secret not in text
    assert "Prepared(" in repr(p) and str(p.count) in repr(p)


def test_password_never_ends_up_in_prepared(make_input, tpl, tmp_path):
    plain = make_input(n=3)
    enc = tmp_path / "enc.xlsx"
    with open(plain, "rb") as f, open(enc, "wb") as o:
        OOXMLFile(f).encrypt(PW, o)
    p = prep(enc, tpl, password=PW)
    blob = repr(p) + repr(vars(p)) + pickle.dumps(p).decode("latin-1")
    assert PW not in blob and p.count == 3


# ---------- 요약값: 미리보기와 출력의 인원·금액 일치 ----------
@pytest.mark.parametrize("name", CASES)
def test_prepared_count_and_total_equal_the_generated_output(name, tmp_path, make_input, make_mc_input, synthetic, monkeypatch):
    program, src, policy = build_case(name, make_input, make_mc_input, synthetic, monkeypatch)
    p = prepare(program, src, TEMPLATE, policy=policy, base_date=BASE_DATE)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    res = finish(p, out_dir)
    wris = load_workbook(res.output_path)["WRIS"]
    amounts = [wris.cell(r, 5).value for r in range(2, wris.max_row + 1) if wris.cell(r, 5).value is not None]      # total_money 열
    assert res.count == p.count == len(amounts) and sum(amounts) == p.total_amount and all(isinstance(a, int) for a in amounts)
    assert p.year == 9999 and 1 <= p.month <= 12


def test_prepared_year_month_come_from_the_batch(make_input, tpl):
    p = prep(make_input(n=2), tpl)
    assert (p.year, p.month, p.program) == (9999, 9, "daechung") and p.filename == "지급명단_DAECHUNG_9999_09.xlsx"


# ---------- 기준일은 prepare 에서 확정 ----------
def test_base_date_is_fixed_at_prepare_time(make_input, tpl, out):
    from datetime import date
    src = make_input(n=2)
    p = prepare("daechung", src, tpl, today=date(2099, 1, 2))
    assert p.base_date == "2099.01.02"
    res = finish(p, out)                                                      # finish 는 오늘 날짜를 다시 읽지 않는다
    assert diff(dump(res.output_path), dump(finish(p, out).output_path)) == []
    q = prepare("daechung", src, tpl, base_date="2050.05.05", today=date(2099, 1, 2))
    assert q.base_date == "2050.05.05"


# ---------- 변경 감지(SHA-256): 크기·시각이 같아도 내용이 바뀌면 막는다 ----------
def _flip_one_byte_keep_size_and_mtime(path):
    st = os.stat(path)
    data = bytearray(Path(path).read_bytes())
    data[-1] ^= 0x01
    Path(path).write_bytes(bytes(data))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))


@pytest.mark.parametrize("which", ["source", "template", "policy"])
def test_finish_refuses_when_a_file_changed_even_with_same_size_and_mtime(which, make_input, tpl, policy_path, out):
    src = make_input(n=3)
    p = prepare("daechung", src, tpl, policy=load_policy(policy_path), base_date=BASE_DATE,
                policy_source=PolicySource(policy_path, conv.fingerprint_file(policy_path)))
    assert check_unchanged(p) == ()
    target = {"source": src, "template": tpl, "policy": policy_path}[which]
    size, mtime = os.stat(target).st_size, os.stat(target).st_mtime_ns
    _flip_one_byte_keep_size_and_mtime(target)
    assert (os.stat(target).st_size, os.stat(target).st_mtime_ns) == (size, mtime)       # 보조 정보는 그대로인데
    assert check_unchanged(p) == (which,)                                                  # SHA-256 이 잡는다
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert e.value.stage == "changed" and [(x.code, x.field) for x in e.value.errors] == [("INPUT_FILE_CHANGED", which)]
    assert list(out.iterdir()) == []                                                      # 생성하지 않음(임시 파일도 없음)


@pytest.mark.parametrize("which", ["source", "template", "policy"])
def test_deleted_file_counts_as_changed(which, make_input, tpl, policy_path, out):
    src = make_input(n=3)
    p = prepare("daechung", src, tpl, policy=load_policy(policy_path), base_date=BASE_DATE,
                policy_source=PolicySource(policy_path, conv.fingerprint_file(policy_path)))
    Path({"source": src, "template": tpl, "policy": policy_path}[which]).unlink()
    assert check_unchanged(p) == (which,)
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert e.value.stage == "changed" and list(out.iterdir()) == []


def test_several_changes_are_all_reported_and_finish_does_not_regenerate_by_itself(make_input, tpl, out):
    src = make_input(n=3)
    p = prep(src, tpl)
    _flip_one_byte_keep_size_and_mtime(src)
    _flip_one_byte_keep_size_and_mtime(tpl)
    assert check_unchanged(p) == ("source", "template")
    with pytest.raises(ConversionFailed):
        finish(p, out)
    assert list(out.iterdir()) == []


def test_source_changed_while_prepare_is_reading_is_rejected(monkeypatch, make_input, tpl):
    from scholarship_payment.adapters.daechung import DaechungAdapter
    src = make_input(n=3)
    real = DaechungAdapter.read

    def read_then_modify(self, path, password=None):
        res = real(self, path, password)
        _flip_one_byte_keep_size_and_mtime(path)                          # 읽는 사이에 바뀜
        return res

    monkeypatch.setattr(DaechungAdapter, "read", read_then_modify)
    with pytest.raises(ConversionFailed) as e:
        prep(src, tpl)
    assert e.value.stage == "changed" and [x.field for x in e.value.errors] == ["source"]


def test_finish_builds_from_the_exact_bytes_it_hashed_not_from_the_path(monkeypatch, make_input, tpl, out):
    seen = {}
    real = conv.build_workbook

    def spy(validated, template, policy, base_date=None):
        seen["type"] = type(template).__name__
        return real(validated, template, policy, base_date)

    monkeypatch.setattr(conv, "build_workbook", spy)
    p = prep(make_input(n=2), tpl)
    finish(p, out)
    assert seen["type"] == "BytesIO"                                          # 해시한 바이트 = 실제로 쓴 바이트(검사와 사용 사이에 바뀔 틈이 없다)


def test_template_swapped_between_hash_check_and_use_cannot_leak_into_output(monkeypatch, make_input, tpl, out):
    p = prep(make_input(n=2), tpl)
    good = dump(finish(p, out).output_path)
    real_fp = conv.fingerprint_bytes

    def swap_after_hash(data):
        fp = real_fp(data)
        tpl.write_bytes(b"swapped after the hash was taken")             # 해시 직후 파일이 바뀌어도
        return fp

    monkeypatch.setattr(conv, "fingerprint_bytes", swap_after_hash)
    res = finish(p, out)
    assert res.count == p.count
    assert diff(dump(res.output_path), good) == []                            # 바뀐 파일이 아니라 해시한 바이트로 만든 정상 파일


# ---------- 실패 시 부분 파일 없음 ----------
def test_finish_failure_in_template_layout_leaves_nothing(make_input, tmp_path, out):
    bad = tmp_path / "bad_layout.xlsx"
    wb = load_workbook(TEMPLATE)
    del wb["WINS"]
    wb.save(bad)
    p = prep(make_input(n=3), bad)                                            # prepare 는 템플릿 레이아웃을 보장하지 않는다(은행코드만 읽음)
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert e.value.stage == "template" and list(out.iterdir()) == []


def test_finish_failure_in_output_verification_leaves_nothing(monkeypatch, make_input, tpl, out):
    p = prep(make_input(n=3), tpl)
    monkeypatch.setattr(conv, "verify_output", lambda *a, **k: (_ for _ in ()).throw(conv.ValidationFailed([conv.ValidationError("OUTPUT_MISMATCH", "x")])))
    with pytest.raises(ConversionFailed) as e:
        finish(p, out)
    assert e.value.stage == "output" and list(out.iterdir()) == []


def test_finish_into_missing_folder_leaves_nothing_and_does_not_touch_prepared(make_input, tpl, tmp_path):
    p = prep(make_input(n=3), tpl)
    with pytest.raises(ConversionFailed) as e:
        finish(p, tmp_path / "no_such_dir")
    assert e.value.stage == "output" and [x.code for x in e.value.errors] == ["OUTPUT_DIR_MISSING"] and not (tmp_path / "no_such_dir").exists()


# ---------- 오류 단계·코드는 기존 convert() 와 같다 ----------
def _same_failure(make, tmp_path):
    src, template = make
    out_dir = tmp_path / "o"
    out_dir.mkdir(exist_ok=True)
    with pytest.raises(ConversionFailed) as a:
        convert("daechung", src, out_dir, template, base_date=BASE_DATE)
    with pytest.raises(ConversionFailed) as b:
        prepare("daechung", src, template, base_date=BASE_DATE)
    assert (a.value.stage, [(e.code, e.field, e.row) for e in a.value.errors], a.value.missing_banks) == (b.value.stage, [(e.code, e.field, e.row) for e in b.value.errors], b.value.missing_banks)
    return b.value


def test_missing_bank_code_is_reported_by_prepare_with_bank_names(make_input, tmp_path):
    wb = load_workbook(TEMPLATE)
    ws = wb["은행코드"]
    gone = ws.cell(FIRST_DATA_ROW, 2).value
    ws.cell(FIRST_DATA_ROW, 3).value = None
    t = tmp_path / "t.xlsx"
    wb.save(t)
    src = make_input(n=3, mutate=lambda s: [s.__setitem__(f"T{r}", gone) for r in (3, 4, 5)])
    e = _same_failure((src, t), tmp_path)
    assert e.stage == "validate" and e.errors and all(x.code.startswith("BANK_CODE_") for x in e.errors) and e.missing_banks == (gone,)


def test_bank_not_in_table_is_reported_missing_by_prepare(make_input, tpl, tmp_path):
    src = make_input(n=3, mutate=lambda s: [s.__setitem__(f"T{r}", "표에없는가상은행") for r in (3, 4)])
    e = _same_failure((src, tpl), tmp_path)
    assert e.stage == "validate" and {x.code for x in e.errors} == {"BANK_CODE_MISSING"} and e.missing_banks == ("표에없는가상은행",)


def test_ambiguous_bank_code_is_blocked_by_prepare(make_input, tmp_path):
    wb = load_workbook(TEMPLATE)
    ws = wb["은행코드"]
    name = ws.cell(FIRST_DATA_ROW, 2).value
    r = ws.max_row + 1
    ws.cell(r, 2, name)
    ws.cell(r, 3, 99999)
    ws.cell(r, 4, 99998)
    t = tmp_path / "t.xlsx"
    wb.save(t)
    src = make_input(n=3, mutate=lambda s: [s.__setitem__(f"T{rr}", name) for rr in (3, 4, 5)])
    e = _same_failure((src, t), tmp_path)
    assert e.stage == "validate" and any(x.code == "BANK_CODE_AMBIGUOUS" for x in e.errors)


def test_duplicate_student_id_is_blocked_by_prepare(make_input, tpl, tmp_path):
    src = make_input(n=5, mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value))
    e = _same_failure((src, tpl), tmp_path)
    assert e.stage == "validate" and any(x.code == "DUPLICATE_STUDENT_ID" for x in e.errors)


def test_missing_bank_sheet_and_unreadable_template_and_missing_source_keep_their_stages(make_input, tmp_path):
    wb = load_workbook(TEMPLATE)
    del wb["은행코드"]
    t = tmp_path / "nobank.xlsx"
    wb.save(t)
    assert _same_failure((make_input(n=2), t), tmp_path).stage == "template"
    junk = tmp_path / "junk.xlsx"
    junk.write_bytes(b"junk")
    assert _same_failure((make_input(n=2), junk), tmp_path).stage == "template"
    assert _same_failure((tmp_path / "없음.xlsx", TEMPLATE), tmp_path).stage in ("input", "template")
    assert _same_failure((tmp_path / "없음.xlsx", TEMPLATE), tmp_path).errors[0].code == "FILE_NOT_FOUND"


def test_unsupported_program_is_an_input_stage_error():
    with pytest.raises(ConversionFailed) as e:
        prepare("nope", "x.xlsx", TEMPLATE)
    assert e.value.stage == "input" and e.value.errors[0].code == "PROGRAM_UNSUPPORTED"


# ---------- 암호 파일: prepare 에서 비밀번호 오류를 구분 ----------
def test_encrypted_source_password_required_wrong_and_correct(make_input, tpl, tmp_path):
    plain = make_input(n=3)
    enc = tmp_path / "enc.xlsx"
    with open(plain, "rb") as f, open(enc, "wb") as o:
        OOXMLFile(f).encrypt(PW, o)
    for pw, code in ((None, "INPUT_PASSWORD_REQUIRED"), ("틀린-pw", "INPUT_PASSWORD_WRONG")):
        with pytest.raises(ConversionFailed) as e:
            prep(enc, tpl, password=pw)
        assert e.value.stage == "input" and [x.code for x in e.value.errors] == [code] and "틀린-pw" not in repr(e.value) + str(e.value)
    h = sha(enc)
    assert prep(enc, tpl, password=PW).count == 3 and sha(enc) == h                       # 원본 불변


def test_policy_object_is_snapshotted_not_referenced(make_input, tpl):
    pol = dataclasses.replace(SYNTHETIC_POLICY, list_title="합성 {month}월")
    p = prepare("daechung", make_input(n=2), tpl, policy=pol, base_date=BASE_DATE)
    assert p.policy == pol and p.policy is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.policy.list_title = "바뀜"
    assert MC_POLICY.hourly_rates                                              # (임포트 사용 표시)


def test_fingerprint_has_sha256_and_helper_values(tmp_path):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    fp = conv.fingerprint_file(f)
    assert isinstance(fp, FileFingerprint) and fp.size == 3 and fp.sha256 == hashlib.sha256(b"abc").hexdigest() and fp.mtime_ns == os.stat(f).st_mtime_ns
    assert str(f) not in repr(fp)


# ---------- 기존 진입점(CLI·공용 실행 계층·Tk 가 쓰는 경로)도 같은 골든 출력을 낸다 ----------
def test_cli_and_controller_paths_still_produce_the_golden_output(make_input, tmp_path, capsys):
    from scholarship_payment import __main__ as cli
    from scholarship_payment.app.controller import run_conversion
    src = make_input(n=5)
    golden = load_golden("daechung_plain")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    o = run_conversion("daechung", src, a, TEMPLATE, base_date=BASE_DATE)
    assert o.ok and o.count == 5
    assert cli.main(["convert", "--program", "daechung", "--input", str(src), "--out-dir", str(b), "--template", str(TEMPLATE), "--base-date", BASE_DATE]) == 0
    for folder in (a, b):
        (f,) = list(folder.iterdir())
        got = dump(f)
        assert diff({**got, **{k: golden[k] for k in ("filename", "count", "warnings", "notes")}}, golden) == [] and f.name == golden["filename"]


def test_tk_gui_module_still_imports_and_uses_the_shared_controller():
    import scholarship_payment.gui.app as app
    assert callable(app.main) and app.run_conversion is __import__("scholarship_payment.app.controller", fromlist=["run_conversion"]).run_conversion
