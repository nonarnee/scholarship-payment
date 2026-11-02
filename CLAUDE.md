# 프로젝트 작업 규칙

## 목표
한국장학재단 월별지급승인 파일을 표준 대학 지급명단(지급대상자명단, WINS, WRIS)으로 변환하는 **오프라인 Windows 데스크톱 도구**.

## 문서 우선순위
1. `docs/REQUIREMENTS.md`: 사용자 요구사항
2. `docs/FILE-STRUCTURE.md`: 실제 마스킹 샘플에서 확인한 구조(재검증 필요)
3. `docs/DECISIONS-OPEN.md`: 확정/미확정 정책
4. `docs/ARCHITECTURE.md`: 구현 원칙
5. `docs/VALIDATION-AND-TESTS.md`: 검증 기준
6. `docs/PUBLIC-SAFETY.md`: 공개 저장소 안전 규칙(모든 작업에 우선 적용)

## 절대 준수
- 원본 Excel을 수정하지 않는다.
- 처음에는 설계만 한다. 사용자의 후속 지시 전까지 구현에 착수하지 않는다.
- 입력 Adapter와 출력 Writer를 분리한다.
- 지원 사업: 대청교, 다문화·탈북학생 멘토링, AI멘토링. 미제공 양식은 추정하지 않는다.
- 지급명단에는 실사용 시트 3개(지급대상자명단, WINS, WRIS) 모두 필요하다.
- 정확한 금액·계좌·은행코드가 서식보다 우선이며 양쪽 모두 검증한다.
- 문자열 식별자(학번, 계좌번호)의 앞자리 0 보존. 엑셀 수식 주입 방지.
- 금액은 정수 원 단위. `float` 기반 금액 연산 금지.
- 오류 발생 시 부분 성공 파일을 최종 결과로 남기지 않는다.
- 학생 식별정보 및 계좌 정보를 로그/콘솔/테스트 스냅샷에 평문으로 기록하지 않는다.
- **이 저장소는 GitHub Public이다.** 실제 업무자료와 그 파생 값(성명·학번·계좌·사업자번호·기관명·금액 합계·내부 시스템 구분코드/상수/고유 헤더·실제 파일명·값의 종류 수나 분포)을 코드·문서·테스트·커밋 메시지 어디에도 쓰지 않는다. `docs/PUBLIC-SAFETY.md`를 따른다.
- 마스킹 샘플도 공개 안전성이 확인되기 전에는 커밋하지 않는다. 테스트용 엑셀은 `tools/synthetic/make_synthetic.py`로 만든 완전 합성 데이터(`synthetic_*.xlsx`)만 허용한다.
- 커밋 전 `tools/safety/check_public_safety.py` 통과(훅: `sh tools/safety/install-hooks.sh`), 푸시 전 `--tracked`/`--worktree` 재실행. 실자료 분석 결과는 `private/`(git 무시)에만 기록한다.
- Windows 운영 환경에서 실실행 검증되지 않은 결과를 '완료'라고 표현하지 않는다.

## 개발 원칙(후속 단계)
- Python 3.12, Tkinter+ttk, openpyxl, pytest, PyInstaller 후보. 의존성·보존율은 설계 단계에서 실측한다.
- 개발 Mac / Windows 빌드 GitHub Actions / 실검증 Windows Excel.
- 템플릿에서 스타일을 복제하되 저장 시 Excel 특수 기능 손상 여부를 확인한다.
- 불확실한 정책은 `OPEN-QUESTIONS.md`로 이동한다.
