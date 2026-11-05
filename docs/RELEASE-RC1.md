# 배포 후보 `0.3.0-rc.1` — 빌드 구조와 배포 가능 여부 판정 기준

> 작성: 2026-11-04 (Phase 5-A). **이 문서는 정식 배포를 선언하지 않는다.** 자동 테스트와 CI 통과는 학교 PC·Windows Excel 검증이 아니다.

## 1. 상태
- 신규 PySide6 화면이 기본 GUI 후보이고, 기존 Tkinter 화면은 **한 릴리스 동안 병행**한다(코드와 회귀 테스트는 삭제하지 않는다). CLI 는 그대로다.
- 정식 배포·사용자 배포는 수행하지 않았다. Windows 수동 UAT(Phase 5-B)는 수행하지 않았다.

## 2. 산출물
| 종류 | exe 이름 | 용도 | 배포 |
|---|---|---|---|
| 신규 PySide6(기본) | `ScholarshipPayment-v0.3.0-rc.1` | 사용자용 GUI. 옵션은 `--smoke`, `--version` 뿐 | 배포 후보 |
| 기존 Tkinter(legacy) | `ScholarshipPaymentLegacyTk-v0.3.0-rc.1` | 되돌리기·병행용 | 배포 후보(한 릴리스) |
| 개발용 | `ScholarshipPaymentUI-dev` | 패키징된 exe 의 합성 E2E 검증 전용(`--gallery`, `--synthetic-e2e-smoke` 포함) | **사용자에게 배포하지 않음** |

CI 아티팩트 이름은 `<exe 이름>-<커밋 7자리>` 이고, 이름 규칙은 `packaging/release_info.py` 한 곳에서 정한다. 버전은 `scholarship_payment.__version__`(`0.3.0-rc.1`) 하나에서 나오며 창 제목·정보 화면·exe 이름·Windows 버전 리소스·아티팩트 이름이 모두 이 값을 쓴다(pip 메타데이터에서는 `0.3.0rc1` 로 정규화된다). Windows 버전 리소스의 숫자 4칸은 `0.3.0.0` 이고, rc 표시는 문자열 FileVersion/ProductVersion 에 있다.

## 3. 빌드
- `python packaging/build_release.py --kind qt|legacy|dev` (PyInstaller onedir). Windows 에서는 창 앱(`--windowed`)으로 빌드한다.
- 정식 Qt exe 는 개발 모듈(`ui.gallery`, `ui.e2e_smoke`, `ui.__main__`)과 `tkinter`·`scholarship_payment.gui` 를 **제외**하고, 진입점은 `packaging/run_gui_qt.py` → `ui/app_main.py` 다. 점검 도구가 실행 파일 안의 모듈 목록으로 이를 확인한다.
- 빌드 의존성 버전은 `packaging/rc-constraints.txt` 로 고정한다(Windows CI 에서 실제 검증된 버전).
- 개발 환경에서 로컬로 만들어 볼 수 있다(`--no-windowed`로 콘솔 앱). 단 macOS 빌드는 Windows 빌드의 근거가 아니다.

## 4. 배포 폴더 구조 (qt)
```
ScholarshipPayment-v0.3.0-rc.1/
  ScholarshipPayment-v0.3.0-rc.1.exe
  _internal/                 Qt·파이썬 런타임·라이브러리(별도 파일)
  README-설치.txt            설치·실행·설정·한계·롤백 안내
  BUILD-INFO.txt             버전, 커밋, Python·PySide6·Qt 등 정확한 버전
  SHA256SUMS.txt             exe·안내문·LICENSES 파일의 SHA-256
  LICENSES/                  LGPL-3.0, GPL-3.0, THIRD-PARTY-NOTICES, README-LICENSES, RELINK-Qt
```
**정책 JSON 과 실제 학교 템플릿은 포함하지 않는다.** 점검 도구가 `.xlsx`·`policy_*.json`·`template_*` 파일이 들어 있으면 실패한다.

## 5. 자동 검증 범위와 미검증 범위
**자동으로 확인한 것(합성 데이터)**: 전체 pytest, 골든 동등성, 개발 옵션이 정식 진입점에서 거부됨(종료 코드 2)과 정식 exe 에 개발 모듈·tkinter 가 없음, 두 exe(Qt·legacy)의 엔진 모듈 바이트코드가 같음, SHA256SUMS 검증, 패키징된 **개발용** exe 의 합성 E2E(모듈 로딩·파싱·미리보기·생성·출력 재검증·무덮어쓰기·암호 파일·폴더 오류 재시도), 산출물 점검(Qt 목록·필수 파일·금지 파일).
**미검증(학교 PC에서 직접)**: `docs/UAT-CHECKLIST.md` 전체 — 실제 창·글꼴·DPI·해상도, 파일 대화상자·드래그 앤 드롭, 폴더 열기·클립보드, Defender·SmartScreen, 네트워크 드라이브·OneDrive, 실제 재단 원본·정책·템플릿, **실제 Windows Excel 열기·인쇄·서식, WINS/WRIS 업로드 호환**, 접근성, 롤백. 정식 exe 자체로 생성 경로를 실행하는 E2E 는 없다(개발용 exe 로 대체, 두 exe 의 동일성은 위 점검으로 보완).
이번 변경 내용은 Windows 러너에서 **아직 실행하지 않았다**(푸시·CI 실행은 별도 승인).

## 6. 배포 가능 여부 최종 판정 기준
CI 통과만으로 판정하지 않는다. 아래 **필수 조건을 모두 충족해야** "정식 배포 가능"으로 기록한다.
1. 릴리스 후보 커밋의 Windows CI 가 모두 통과(테스트, 정식 exe 점검, 엔진 비교, SHA256SUMS 검증, 개발용 exe E2E).
2. `docs/UAT-CHECKLIST.md` 의 P0 항목이 대표 학교 PC 2대 이상(서로 다른 Windows·Excel 조합)에서 통과하고, 미해결 P0·P1 결함이 없다.
3. 실제 Windows Excel 에서 세 사업의 출력이 열기·인쇄·값·서식 기준을 충족하고, 권한 있는 담당자가 WINS/WRIS 호환을 확인했다.
4. 미결정 업무 정책(H5/M17, M21, H1/H2 등, `docs/OPEN-QUESTIONS.md`)이 결정되었거나, 현재 동작과 한계를 문서로 명시해 사용자가 수용했다.
5. `docs/LICENSE-REVIEW.md` §6 의 조건이 충족되었다(배포 범위·소스 제공 방식 결정, 외부 전달이면 법무 확인).
6. 전산팀의 Defender·SmartScreen 허용 절차를 마쳤고, 네트워크 미사용·쓰기 범위 제한을 확인했다.
7. 롤백 수단(이전 버전 또는 legacy)을 확보했고 롤백 시험(U24)이 통과했다.
8. `docs/PROJECT-STATUS.md` 가 실제로 실행한 사실만으로 갱신되었고, 알려진 한계(강제 종료 시 임시 파일 등)가 안내문에 적혀 있다.

일부만 충족한 상태는 **제한 시범 사용(1~2대, 롤백 수단 유지)** 으로 구분해 기록하고 정식 배포로 표현하지 않는다.

## 7. 롤백
`README-설치.txt` §8 의 절차를 따른다: 새 폴더를 풀기 전에 이전 폴더를 이름만 바꿔 보관하고, 문제가 있으면 새 프로그램을 닫고 이전(또는 legacy) 폴더의 exe 를 실행한다. legacy 는 `settings.json` 을 쓰지 않으므로 설정 파일이 롤백을 막지 않는다. 이미 만든 결과 파일은 그대로 남는다. 롤백 시험은 UAT U24 다.

## 8. 사용자 설정 위치
`%APPDATA%\ScholarshipPayment\settings.json` (마지막 사업, 사업별 템플릿·정책·저장 폴더 경로만). 정책·템플릿 기본 탐색 위치는 exe 폴더와 같은 `%APPDATA%\ScholarshipPayment` 폴더의 `policy_<사업코드>.json`·`template_<사업코드>.xlsx` 다.

## 9. 정식 배포 전에 남은 필수 조건 (요약)
Windows CI 에서 이번 변경 실행 / UAT 수행(Phase 5-B) / 실제 Excel·WINS/WRIS 확인 / 미결정 업무 정책 결정 / LGPL 소스 제공·배포 범위 결정과 법무 확인 / 전산팀 허용 / 앱 자체 라이선스 결정(필요 시 별도 승인) / 정식 버전 번호 확정(rc 해제).
