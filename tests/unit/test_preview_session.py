"""미리보기 세션(Qt 무관 상태 기계): 중복 실행 방지, 오래된 결과 폐기, 비밀번호 3회 제한·취소·재입력, 변경 감지로 무효화."""
import pytest

from scholarship_payment.ui import preview as pv
from scholarship_payment.ui.runner import InlineRunner, ManualRunner
from scholarship_payment.ui.state import Step1Selection
from prep_helpers import PW, TEMPLATE, encrypt, flip_byte_keep_size_and_mtime, make_policy

BASE = "2099.10.07"


@pytest.fixture
def pol(tmp_path):
    return make_policy(tmp_path)


def sel(src, pol, program="daechung"):
    return Step1Selection(program, BASE, str(src), str(tmp_out()), str(TEMPLATE), str(pol))


def tmp_out():
    return "/unused/out"          # Phase 3 에서는 저장 폴더를 쓰지 않는다


def session(runner=None):
    return pv.PreviewSession(runner or InlineRunner())


# ---------- 기본 흐름 ----------
def test_start_prepares_and_reaches_ready_with_summary(make_input, pol):
    s = session()
    assert s.state == pv.IDLE
    s.start(sel(make_input(n=4), pol))
    assert s.state == pv.READY and s.summary.count == 4 and s.prepared is not None and s.errors == ()


def test_preparing_state_is_visible_while_work_runs_and_blocks_duplicate_start(make_input, pol):
    r = ManualRunner()
    s = session(r)
    s.start(sel(make_input(n=3), pol))
    assert s.state == pv.PREPARING and s.busy and len(r.pending) == 1
    s.start(sel(make_input(n=3), pol))                                    # 처리 중 중복 실행은 무시
    assert len(r.pending) == 1
    r.run_all()
    assert s.state == pv.READY and not s.busy


def test_failed_state_has_grouped_errors_and_no_prepared(make_input, pol):
    s = session()
    s.start(sel(make_input(n=5, mutate=lambda ws: ws.__setitem__("F7", ws["F5"].value)), pol))
    assert s.state == pv.FAILED and s.prepared is None and any(g.code == "DUPLICATE_STUDENT_ID" for g in s.errors)


# ---------- 오래된 결과 폐기 ----------
def test_discard_while_preparing_drops_the_late_result(make_input, pol):
    r = ManualRunner()
    s = session(r)
    s.start(sel(make_input(n=3), pol))
    s.discard()                                                            # 이전 단계로 이동/취소
    r.run_all()
    assert s.state == pv.IDLE and s.prepared is None and s.summary is None and not s.busy


def test_restart_after_discard_ignores_the_first_runs_result(make_input, pol, tmp_path):
    r = ManualRunner()
    s = session(r)
    a, b = make_input(n=3), make_input(n=4)
    s.start(sel(a, pol))
    s.discard()
    s.start(sel(b, pol))
    r.run(1)                                                               # 새 실행이 먼저 끝나고
    r.run(0)                                                               # 이전 실행의 늦은 결과는 무시
    assert s.state == pv.READY and s.summary.count == 4


def test_discard_clears_everything_including_attempts(make_input, pol, tmp_path):
    enc = encrypt(make_input(n=3), tmp_path / "e.xlsx")
    s = session()
    s.start(sel(enc, pol))
    s.submit_password("x1")
    assert s.attempts == 1
    s.discard()
    assert s.state == pv.IDLE and s.attempts == 0 and s.prepared is None and s.errors == ()


# ---------- 비밀번호: 필요할 때만, 최대 3회, 취소·재입력 ----------
def test_password_is_requested_only_for_encrypted_files(make_input, pol, tmp_path):
    s = session()
    s.start(sel(make_input(n=3), pol))
    assert s.state == pv.READY
    s2 = session()
    s2.start(sel(encrypt(make_input(n=3), tmp_path / "e.xlsx"), pol))
    assert s2.state == pv.NEED_PASSWORD and s2.attempts == 0 and not s2.last_password_wrong


def test_correct_password_after_one_wrong_attempt(make_input, pol, tmp_path):
    s = session()
    s.start(sel(encrypt(make_input(n=3), tmp_path / "e.xlsx"), pol))
    s.submit_password("틀림")
    assert s.state == pv.NEED_PASSWORD and s.attempts == 1 and s.last_password_wrong
    s.submit_password(PW)
    assert s.state == pv.READY and s.summary.count == 3 and not s.last_password_wrong


def test_three_wrong_attempts_lock_the_session_until_discard(make_input, pol, tmp_path):
    s = session()
    s.start(sel(encrypt(make_input(n=3), tmp_path / "e.xlsx"), pol))
    for i in range(3):
        assert s.state == pv.NEED_PASSWORD
        s.submit_password(f"틀림{i}")
    assert s.state == pv.LOCKED and s.attempts == 3 and s.prepared is None
    s.submit_password(PW)                                                  # 잠긴 뒤에는 받지 않는다
    s.start(sel(make_input(n=3), pol))
    assert s.state == pv.LOCKED
    s.discard()
    assert s.state == pv.IDLE


def test_cancel_password_returns_to_a_cancelled_state_and_keeps_the_attempt_count(make_input, pol, tmp_path):
    enc = encrypt(make_input(n=3), tmp_path / "e.xlsx")
    s = session()
    s.start(sel(enc, pol))
    s.submit_password("틀림")
    s.cancel_password()
    assert s.state == pv.CANCELLED and s.prepared is None and s.attempts == 1
    s.start(sel(enc, pol))                                                  # 사용자가 다시 시도하면 비밀번호를 다시 묻는다
    assert s.state == pv.NEED_PASSWORD and s.attempts == 1
    s.submit_password(PW)
    assert s.state == pv.READY


def test_password_is_not_kept_by_the_session_or_the_pending_job_after_it_runs(make_input, pol, tmp_path):
    r = ManualRunner()
    s = session(r)
    s.start(sel(encrypt(make_input(n=3), tmp_path / "e.xlsx"), pol))
    r.run_all()
    r.pending.clear()
    s.submit_password(PW)
    r.run_all()
    assert s.state == pv.READY
    blob = repr(vars(s)) + repr(s.summary) + repr(s.prepared)
    assert PW not in blob


def test_password_waiting_in_a_queued_job_is_wiped_on_discard(make_input, pol, tmp_path):
    r = ManualRunner()
    s = session(r)
    s.start(sel(encrypt(make_input(n=3), tmp_path / "e.xlsx"), pol))
    r.run_all()
    r.pending.clear()
    s.submit_password(PW)
    box = s._box
    s.discard()
    assert box.value is None                                                # 대기 중이던 작업 안의 비밀번호도 지운다
    r.run_all()
    assert s.state == pv.IDLE


def test_wrong_password_result_after_discard_is_ignored(make_input, pol, tmp_path):
    r = ManualRunner()
    s = session(r)
    s.start(sel(encrypt(make_input(n=3), tmp_path / "e.xlsx"), pol))
    r.run_all()
    r.pending.clear()
    s.submit_password("틀림")
    s.discard()
    r.run_all()
    assert s.state == pv.IDLE and s.attempts == 0


# ---------- 변경 감지: 미리보기 무효화(자동 재생성 없음) ----------
@pytest.mark.parametrize("which", ["source", "template", "policy"])
def test_verify_fresh_invalidates_the_preview_when_a_file_changed(which, make_input, pol, tmp_path):
    src = make_input(n=3)
    tpl = tmp_path / "tpl.xlsx"
    tpl.write_bytes(TEMPLATE.read_bytes())
    s = session()
    s.start(Step1Selection("daechung", BASE, str(src), "/x", str(tpl), str(pol)))
    assert s.state == pv.READY
    s.verify_fresh()
    assert s.state == pv.READY
    flip_byte_keep_size_and_mtime({"source": src, "template": tpl, "policy": pol}[which])
    s.verify_fresh()
    assert s.state == pv.INVALIDATED and s.prepared is None and s.summary is None and s.changed == (which,)


def test_invalidated_session_does_not_regenerate_by_itself_and_needs_explicit_restart(make_input, pol):
    src = make_input(n=3)
    r = ManualRunner()
    s = session(r)
    s.start(sel(src, pol))
    r.run_all()
    flip_byte_keep_size_and_mtime(src)
    s.verify_fresh()
    r.run_all()
    assert s.state == pv.INVALIDATED and r.pending == []                   # 변경을 감지해도 스스로 다시 읽지 않는다
    s.start(sel(src, pol))                                                  # 사용자가 다시 확인을 누르면 처음부터
    assert s.state == pv.PREPARING


def test_late_verify_result_after_discard_is_ignored(make_input, pol):
    src = make_input(n=3)
    r = ManualRunner()
    s = session(r)
    s.start(sel(src, pol))
    r.run_all()
    r.pending.clear()
    flip_byte_keep_size_and_mtime(src)
    s.verify_fresh()
    s.discard()
    r.run_all()
    assert s.state == pv.IDLE


def test_verify_fresh_is_a_noop_unless_ready(make_input, pol):
    r = ManualRunner()
    s = session(r)
    s.verify_fresh()
    assert s.state == pv.IDLE and r.pending == []


def test_session_never_writes_files(make_input, pol, tmp_path, monkeypatch):
    from scholarship_payment.app import convert as conv
    monkeypatch.setattr(conv, "save_new", lambda *a, **k: (_ for _ in ()).throw(AssertionError("save")))
    src = make_input(n=3)
    before = sorted(str(p) for p in tmp_path.rglob("*"))
    s = session()
    s.start(sel(src, pol))
    s.verify_fresh()
    assert s.state == pv.READY and sorted(str(p) for p in tmp_path.rglob("*")) == before


def test_old_runs_result_arriving_first_does_not_complete_the_new_run(make_input, pol):
    r = ManualRunner()
    s = session(r)
    a, b = make_input(n=3), make_input(n=4)
    s.start(sel(a, pol))
    s.discard()
    s.start(sel(b, pol))
    r.run(0)                                                               # 이전 실행의 결과가 먼저 도착해도
    assert s.state == pv.PREPARING and s.summary is None                   # 새 실행이 끝나기 전에는 완료로 보지 않는다
    r.run(1)
    assert s.state == pv.READY and s.summary.count == 4
