"""PySide6 화면(신규, 개발 중). 기존 Tkinter 화면(`gui/`)은 새 화면이 검증될 때까지 그대로 둔다.
업무 규칙·변환 로직은 두지 않는다: 표시와 입력만 하고, 실제 처리는 `app/` 계층이 담당한다(CLAUDE.md §4).
PySide6 는 선택 의존성(`pip install -e ".[gui]"`)이며, 이 패키지는 PySide6 가 있을 때만 import 한다(navigation 제외).
"""
