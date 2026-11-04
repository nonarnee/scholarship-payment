# 신규 화면(PySide6) 기술 결정과 라이선스 검토

> 작성: 2026-11-04. **실제로 확인한 사실만** 적는다. 확인하지 못한 것은 "미확인"으로 표시한다. 법률 자문이 아니다.

## 1. 결정 (사용자 승인, 2026-11-04)
1. GUI 프레임워크는 PySide6. 2. Step 2에 학생별 샘플 표는 두지 않는다(지급 요약·검증 결과 중심). 3. 신규 GUI는 실제 정책 파일을 필수로 한다(기존 CLI·`convert()` 기본 동작은 바꾸지 않음, 구현은 Phase 2 이후). 4. 사업별 템플릿·정책 경로, 마지막 사업, 기본 저장 폴더를 사용자 설정으로 관리(구현은 Phase 2). 5. 글꼴은 동봉하지 않고 Windows 시스템 글꼴(맑은 고딕 → Segoe UI). 6. 입력은 `.xlsx`만. 7. 소요 시간·추정 진행률은 표시하지 않는다. 8. 기존 Tkinter 화면은 Phase 4까지 유지하고 Phase 5에서 제거. 9. 미확정 업무 정책은 바꾸지 않는다.

## 2. 구조 (Phase 1에서 만든 것)
- `src/scholarship_payment/ui/` — `theme.py`(Stitch `DESIGN.md` 토큰·스타일시트), `widgets.py`(Card·Badge·AppButton·StepperBar), `navigation.py`(Qt 무관 3단계 네비게이션), `main_window.py`(스테퍼·스크롤 본문·하단 버튼 바·상태 표시줄, 자리표시 화면 3개), `gallery.py`(개발용 컴포넌트 갤러리), `__main__.py`(개발 진입점 `python -m scholarship_payment.ui [--gallery] [--smoke]`).
- 기존 `gui/`(Tkinter), `app/`, 엔진, `packaging/run_gui.py`, 기존 `build` CI 작업은 **변경하지 않았다**. PySide6는 선택 의존성(`pip install -e ".[gui]"`)이다.
- 업무 규칙·변환 호출은 아직 없다(자리표시 화면).

## 3. 의존성과 라이선스
- 추가한 패키지: `PySide6-Essentials>=6.8,<7`(이 Mac에 설치된 버전 6.12.0, 함께 설치된 `shiboken6` 6.12.0). 설치 패키지 메타데이터의 라이선스 표기: `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`.
- 코드가 import 하는 Qt 모듈: QtCore, QtGui, QtWidgets. **QtNetwork는 import 하지 않으며** 테스트(`tests/ui/test_main_window.py`)가 이를 확인한다. CI의 PyInstaller 빌드는 `--exclude-module PySide6.QtNetwork`로 제외한다.
- 공식 Qt 문서(2026-11-04 조회): Qt 6은 상용·LGPLv3(GPLv3로 대체 가능)·Marketplace 약정으로 제공된다. 오픈소스 판에서 LGPL이 아니라 GPL로만 제공되는 모듈로 열거된 것에 QtCore·QtGui·QtWidgets는 **들어 있지 않다**(출처: https://doc.qt.io/qt-6/licensing.html). Qt for Python 전용 라이선스 페이지의 본문(LGPL 조건 상세)은 조회 도구 한계로 **끝까지 읽지 못했다(미확인)**.
- LGPLv3 배포 시 의무(Qt FAQ, https://www.qt.io/faq/qt-open-source-licensing): ① LGPL 전문 사본 제공과 LGPL 사용을 알리는 눈에 띄는 고지 ② 사용한 Qt 라이브러리의 전체 소스(수정 포함) 또는 서면 제안 — Qt 소스로의 링크만으로는 충분하지 않다고 명시 ③ 사용자가 다른 버전의 Qt로 재링크할 수 있어야 함 ④ 응용 프로그램 자체 코드는 "work that uses" 라이브러리로서 비공개로 둘 수 있음. 동적 링크를 권장한다는 문구가 있다.
- **onedir 구성만으로 의무가 모두 충족된다고 가정하지 않는다.** 필요한 조치(고지문·소스 제공 방식·교체 방법 안내)는 Phase 5 전에 확정해야 한다.
- 내부 사용과 외부 배포: Qt FAQ는 의무를 "고객·최종 사용자에게 제품을 전달할 때"를 기준으로 설명하며 **내부 사용은 직접 다루지 않는다(미확인)**. 이 도구를 같은 기관 안에서만 쓰는지, 다른 기관·학교 밖에 전달하는지에 따라 판단이 달라질 수 있다. 기관 내부 배포에 대한 해석은 **법무·Qt 측 확인이 필요**하다.

## 4. 확인한 것과 확인하지 못한 것
| 항목 | 상태 |
|---|---|
| macOS(개발 Mac)에서 offscreen 위젯 생성·이벤트·화면 그리기(`grab`) | 확인(자동 테스트 46개, 100/125/150% 캡처 육안 확인) |
| `python -m scholarship_payment.ui --smoke` 종료 코드 0 (Mac) | 확인 |
| Windows 러너 빌드·smoke·폴더 크기·smoke 시간 | CI 작업 `ui-foundation`이 기록(실행 결과는 `PROJECT-STATUS.md`/PR의 Actions 기록 참조) |
| **Windows 10/11 실제 창 표시, 맑은 고딕 렌더링, 125/150% DPI 외관, 키보드 탐색 실감** | **미검증**(수동) |
| 학교 PC Defender·SmartScreen 반응 | **미검증**(수동) |
| 콤보박스 드롭다운 화살표 모양 | Mac 렌더링에서는 스타일 충돌 가능성이 있어 사용자 지정 스타일을 뺐다. Windows 모양 **미확인** |
| 최종 EXE 크기 | 측정만 한다(합격선 없음) |
| 디자인 `code.html` | 전달받지 못함(`screen.png`·`DESIGN.md`만 사용) |
