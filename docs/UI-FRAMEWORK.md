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
| Windows 러너(GitHub Actions windows-latest, Python 3.12.10) 빌드·smoke | 확인: 실행 41770914331(커밋 6f655ea, 수동 실행) — `build`·`ui-foundation` 모두 성공. UI 테스트 46 passed, python smoke 종료 0, PySide6 onedir 빌드 성공, 빌드된 exe `--smoke`(offscreen) 종료 코드 0. 한계: offscreen 플랫폼이라 실제 Windows 창 플러그인(qwindows) 표시 경로는 실행되지 않음 |
| 폴더 크기·smoke 시간(CI 러너, 참고용·합격선 없음) | 폴더 91.7 MB, smoke 0.29 s (artifact 압축 파일 약 38.2 MB). 학교 PC·실제 창 표시 시간 **미측정**. PyInstaller 경고 `api-ms-win-*.dll` not found 다수(시스템 DLL 해석 경고, 빌드·smoke는 성공) |
| **Windows 10/11 실제 창 표시, 맑은 고딕 렌더링, 125/150% DPI 외관, 키보드 탐색 실감** | **미검증**(수동) |
| 학교 PC Defender·SmartScreen 반응 | **미검증**(수동) |
| 콤보박스 드롭다운 화살표 모양 | Mac 렌더링에서는 스타일 충돌 가능성이 있어 사용자 지정 스타일을 뺐다. Windows 모양 **미확인** |
| 디자인 `code.html` | 전달받지 못함(`screen.png`·`DESIGN.md`만 사용) |

## 5. 정식 배포 전 확인해야 할 라이선스 항목 (미결정, 임의로 정하지 않음)
출처는 위 Qt FAQ·라이선스 문서. 법률 자문이 아니며, 아래는 **결정이 필요한 항목**이다.
1. 배포 범위: 같은 기관 내부만인가, 다른 기관·학교 밖에도 전달하는가 (내부 사용에 대한 해석은 미확인 → 법무/Qt 확인).
2. LGPL 전문 사본과 눈에 띄는 사용 고지를 앱 안(정보 화면)과 배포 폴더(`LICENSES` 등)에 둘 위치·문구.
3. 사용한 Qt 라이브러리(QtCore/QtGui/QtWidgets 및 동봉 DLL·플러그인) 소스 제공 방식 — 소스 동봉 또는 서면 제안. 링크만으로는 불충분.
4. 사용자가 다른 Qt 버전으로 교체할 수 있음을 보장하는 방법 — onedir 폴더 구조에서 DLL 교체 가능 여부 실검증과 교체 안내문. (onedir만으로 충족된다고 가정하지 않음)
5. 동봉되는 Qt 플러그인·번들 라이브러리 각각의 라이선스 목록(실제 빌드 산출물 기준으로 재확인) — GPL 전용 모듈이 섞이지 않았는지 포함.
6. 상용 라이선스 구매 여부 — 이 문서는 LGPLv3 적용을 전제로 개발을 계속하며, 구매·배포 방식은 사용자 결정 사항이다.

## 6. Phase 2 — Step 1 파일 선택 · 고급 설정 (2026-11-04, 검토 대기)
**범위**: Step 1 화면, 고급 설정 대화상자, 정책 만들기 대화상자. 미리보기·변환 실행·결과 화면, 기존 변환 엔진·정책은 변경하지 않았다.

**구성**(Qt 무관 → Qt 순)
- `config/user_settings.py` — 사용자 설정(`settings.json`, 정책·템플릿 기본 위치와 같은 폴더). 허용 키는 `last_program`과 사업별 `template_path`·`policy_path`·`out_dir`뿐. 원본 경로·비밀번호·기준일은 저장하지 않는다. 손상 시 `.bak`(있으면 `.bak.1`…)로 보존, 보존 실패에도 기본값으로 시작, 저장은 임시 파일 + `os.replace`. 로그·예외 문구를 남기지 않는다.
- `ui/validators.py` — 가벼운 검사(`light`: 존재·종류·확장자 `.xlsx`/`.json`·빈 파일)와 구조 검사(`heavy`: 원본은 xlsx 컨테이너 모양만, 템플릿은 기존 `derive_from_template`, 정책은 기존 `load_policy`). 원본의 셀·금액은 읽지 않는다. 저장 폴더는 `os.access` 사전 확인뿐이며 실제 저장 가능 여부는 변환 때 확인한다.
- `ui/state.py` — `Step1Model`(필드별 상태, 모두 OK 일 때만 `ready()`, `snapshot()`은 Phase 3 입력), `SettingsStore`(세션 적용과 영구 저장 결과를 구분), `SettingsDraft`(고급 설정 임시 편집 상태: 복사본으로 시작, 바꾼 경로만 검증, 취소하면 폐기). 백그라운드 결과는 필드별 토큰으로 오래된 것을 버린다.
- `ui/policy_flow.py` — 기존 `policy_builder` 재사용(생성 전 검증, 기존 파일 무덮어쓰기). `ui/runner.py`·`qt_runner.py` — 작업 스레드 1개, 결과는 메인 스레드로 전달. `ui/choosers.py` — 파일 선택기(테스트는 가짜로 교체).
- `ui/step1.py`, `ui/settings_dialog.py`, `ui/policy_wizard.py`, 위젯 `DropZone`·`SegmentedTabs`·`ElidedLabel`·`PathField`·링크 버튼.

**재사용한 기존 모듈(수정 없음)**: `default_paths`(기본 템플릿·정책 탐색), `policy_file.load_policy`, `policy_builder`(`derive_from_template`·`build_policy_dict`·`save_policy_new`·`PROMPTS`·`USER_KEYS`·`HIDDEN_FOR`·`RATES_PROMPT`), `controller`의 기준일 형식(`YYYY.MM.DD`)과 같은 규칙.

**표현 원칙**: 실제로 확인한 것만 보인다 — 원본 "엑셀 형식 확인됨(내용은 아직 읽지 않음)", 템플릿 "WRIS 머리글 확인됨", 정책 "정책 형식 확인됨". "정상", "완료", "변환 준비 완료", 건수·열 수·점수는 쓰지 않는다. 다음 버튼이 막힌 이유는 푸터에 "필요: …"로 보인다(본문이 스크롤되어 가려질 때를 대비).

**Stitch 목업과 다르게 한 것(프로젝트 규칙 우선)**: 건수 감지("128건"), "24개 열 매핑", ENGINE READY·CONFIG_ID·Local Isolated·사용자 아이콘·"쓰기 권한 승인됨(NTFS)"·캐시 비우기·오프라인 확인 표시는 만들지 않았다(측정하지 않거나 해당 기능이 없음). 입력은 `.xlsx`만(목업은 .xls/.csv). 기준일은 `YYYY.MM.DD`(목업은 날짜 선택기, 형식 MM/DD/YYYY). 제목 표시줄은 Windows 기본(목업은 사용자 지정). 스테퍼는 한 곳에만 둔다. 글꼴은 시스템 글꼴(Noto Sans·Material Symbols 미사용, 아이콘 없음). HTML은 구조 참고만 했고 앱에 넣지 않았다. `code.html`은 `private/ui-reference/`(git 무시)에 보관.

**추가 검증에서 바꾼 것(2026-11-04)**
- 저장 폴더: `os.access` 결과로 다음 단계를 막지 않는다(운영체제·권한 설정에 따라 틀릴 수 있음). "쓰기 권한이 없어 보임"은 참고 문구만 띄우고, 어떤 문구도 저장 가능을 보장하지 않는다. 실제 저장 실패는 기존 엔진(`io/safe_save`)이 Phase 4에서 처리한다(변경 없음).
- 다음 단계 이동 직전 `Step1Model.recheck()`: 선택 이후 파일이 사라졌거나(존재), 같은 경로의 내용이 바뀌었으면(크기·수정 시각 서명) 이전 성공 상태를 버리고 검사를 다시 시작해 이동하지 않는다. 바뀐 것이 없으면 새 검사를 시작하지 않는다. 서명은 변경 감지 보조일 뿐 내용 동일성의 증명이 아니며, 최종 일관성 확인은 Phase 3의 지문 확인 범위다.
- 검사 함수가 예외를 내도 문구를 밖으로 내지 않고 고정 코드(`CHECK_FAILED`)로 바꾼다. 개발 진입점은 처리되지 않은 예외를 종류만 출력한다(`SCHOLARSHIP_UI_DEBUG=1`일 때만 전체 출력). 정식 진입점 적용은 Phase 5에서 다시 확인한다.
- 저장 실패 안내는 모델의 실제 상태(`persist_failed`)를 따른다: 사업 전환 중 실패해도 보이고, 이후 저장에 성공하면 사라진다. 저장 성공 시 디스크 설정 = 세션 설정임을 테스트로 확인.

**확인한 것**: 자동 테스트(설정 저장소·검증기·상태·정책 흐름·화면 — 설정 저장·복원·취소·손상 복구, 사업별 경로 독립, 무덮어쓰기, DropZone 파일 종류·다중 입력, 버튼 활성화·Navigator 연동, 오래된 백그라운드 결과 무시, 실제 스레드 실행기의 UI 응답성, 키보드 Tab 순서와 Space 활성화), 의도적 결함 주입 14종 탐지, 100/125/150% 및 1366×768@150%(가용 910×512) offscreen 캡처 육안 확인.
**미검증**: Windows 실제 창·맑은 고딕·DPI·실제 파일 선택 대화상자·드래그 앤 드롭 실동작·학교 PC(Defender, 네트워크 드라이브 경로, OneDrive 경로, 긴 경로), 콤보박스 화살표 모양, Phase 2 코드의 Windows CI 실행(푸시 전), 고대비·화면 낭독기.

