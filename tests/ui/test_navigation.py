"""네비게이션 로직(Qt 무관): 단계 1~3, 선행 조건 없이는 다음으로 갈 수 없다."""
import pytest

from scholarship_payment.ui.navigation import STEP_TITLES, Navigator, Step


def test_steps_and_titles_follow_the_design():
    assert [int(s) for s in Step] == [1, 2, 3]
    assert [STEP_TITLES[s] for s in Step] == ["파일 선택", "지급내역 확인", "결과 생성"]


def test_starts_at_step_1_and_cannot_advance_until_ready():
    nav = Navigator()
    assert nav.current is Step.FILE and not nav.can_next() and not nav.can_back()
    assert nav.next() is False and nav.current is Step.FILE
    nav.set_ready(Step.FILE, True)
    assert nav.can_next() and nav.next() is True and nav.current is Step.REVIEW


def test_back_is_always_allowed_after_step_1_and_keeps_readiness():
    nav = Navigator()
    nav.set_ready(Step.FILE, True)
    nav.next()
    assert nav.can_back() and nav.back() is True and nav.current is Step.FILE
    assert nav.can_next()


def test_cannot_go_past_the_last_step_or_before_the_first():
    nav = Navigator()
    for s in Step:
        nav.set_ready(s, True)
    nav.next(), nav.next()
    assert nav.current is Step.RESULT and not nav.can_next() and nav.next() is False
    nav.back(), nav.back()
    assert nav.current is Step.FILE and nav.back() is False


def test_completed_steps_are_the_ones_before_current():
    nav = Navigator()
    nav.set_ready(Step.FILE, True)
    nav.next()
    assert nav.completed == {Step.FILE}


def test_go_only_allows_backward_or_next_ready_step():
    nav = Navigator()
    assert nav.go(Step.RESULT) is False and nav.go(Step.REVIEW) is False
    nav.set_ready(Step.FILE, True)
    assert nav.go(Step.REVIEW) is True and nav.go(Step.FILE) is True


def test_unready_current_step_blocks_next_again():
    nav = Navigator()
    nav.set_ready(Step.FILE, True)
    nav.set_ready(Step.FILE, False)
    assert not nav.can_next()


def test_changes_are_reported_to_listeners():
    nav, seen = Navigator(), []
    nav.on_change(lambda: seen.append((nav.current, nav.can_next(), nav.can_back())))
    nav.set_ready(Step.FILE, True)
    nav.next()
    assert seen[-1] == (Step.REVIEW, False, True) and len(seen) == 2


def test_invalid_step_value_is_rejected():
    with pytest.raises(ValueError):
        Navigator().set_ready(7, True)


# ---------- 잠금(생성 중·성공 후): 이동을 모두 막고, reset 으로만 처음으로 ----------
def test_locked_navigator_blocks_next_back_and_go_and_reset_unlocks():
    nav = Navigator()
    nav.set_ready(Step.FILE, True)
    nav.set_ready(Step.REVIEW, True)
    nav.next()
    nav.next()
    assert nav.current == Step.RESULT
    nav.set_locked(True)
    assert not nav.can_back() and not nav.can_next() and nav.back() is False and nav.go(Step.FILE) is False and nav.go(Step.REVIEW) is False
    assert nav.current == Step.RESULT
    nav.set_locked(False)
    assert nav.can_back()
    nav.set_locked(True)
    nav.reset()
    assert nav.current == Step.FILE and not nav.locked and nav.completed == set()


def test_lock_notifies_listeners_once_per_change():
    nav = Navigator()
    calls = []
    nav.on_change(lambda: calls.append(1))
    nav.set_locked(True)
    nav.set_locked(True)
    nav.set_locked(False)
    assert len(calls) == 2


def test_go_backwards_never_loops_forever_when_back_is_refused(monkeypatch):
    nav = Navigator()
    nav.set_ready(Step.FILE, True)
    nav.set_ready(Step.REVIEW, True)
    nav.next()
    nav.next()
    monkeypatch.setattr(nav, "back", lambda: False)
    assert nav.go(Step.FILE) is False and nav.current == Step.RESULT
