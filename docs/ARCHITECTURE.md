# 아키텍처 제안

## 데이터 흐름
입력 Workbook → 사업별 WorkbookAdapter → 공통 `PaymentBatch`/`PaymentRow` → Validator → 표준 TemplateWriter → 파일 무결성 재검증 → 안전한 저장(임시 파일 → 최종 경로).

### 입력 Adapter
- `DaechungAdapter`: 실제 샘플로 구현 가능한 첫 대상
- `MulticulturalAdapter`: 실제 샘플 제공 전까지 계약/인터페이스만 설계
- `AiMentoringAdapter`: 실제 샘플 제공 전까지 계약/인터페이스만 설계
- 헤더/레이아웃 식별 시 사업을 자동으로 추정하는 대신 사용자 선택과 구조 검증을 함께 사용한다.
- 다른 버전의 헤더 발견 시 조용히 열 번호를 적용하지 말고 거부/진단한다.

### 공통 모델(초안)
`PaymentBatch`: 사업코드, 지급연월, 대상자 리스트, 원본 파일 메타정보, 원본 지급총액, 사용자 지정 출력 옵션.
`PaymentRow`: 원본 순번, 학번(str), 성명, 학과, 활동기관, 근로지, 사업자등록번호(str), 인원(값+의미), 시급(정수 원), 활동시간(분 정수; 출력 시 `N시간[M분]` 변환), 실제 재단 지급액(정수 원), 은행명, 계좌번호(str), 선택적 비고, 사업별 확장 필드.

모델은 표시 데이터와 식별자 형식을 구분한다. 각 시트에 필요한 사업별 고정값·근로구분·적요는 별도 `BusinessOutputPolicy`로 매핑한다. 스키마에 없는 값은 빈칸/오류 중 어떤 방식으로 취급할지 명시한다.

### 공통 Writer
- 공식 출력 템플릿으로 기존 지급명단(마스킹 버전)의 스타일/수식/페이지 설정을 보존.
- 데이터 행이 늘거나 줄 때 행 스타일, 병합, 합계, 수식 참조, 인쇄 범위를 조정.
- 템플릿 행 삽입·삭제(A) vs 스타일 복제 후 행 블록 재구성(B): 실험 결과 **B 권장**(`IMPLEMENTATION-PLAN.md` §3). Windows Excel 검증 전까지 최종 확정 아님.
- 선택적 기능에 의존하거나 복구 경고가 나타나면 방식 변경.
- WINS/WRIS는 **값 기록을 우선 검토**한다(수식은 최대 96명 상한). 전산 업로드 호환성 검증 전까지 최종 확정하지 않는다(OPEN H1).
- 파일명/시트명/상단 제목/지급월/적요의 월별 갱신 정책을 명시.
- 기존 `wins 업로드 결과(2.9)` 자료를 사용자 산출물에 포함하지 않는다.

### GUI
- Tkinter + ttk로 입력/출력 파일 선택, 사업 선택, 미리보기(사업명/월/인원/금액), 진행 상태, 검증오류, 생성 완료와 파일 위치 안내.
- 개인정보(이름·학번·계좌) 전체를 기본 화면에 노출하지 않으며 오류 메시지는 가능하면 행 번호와 필드만 표시.

### 빌드
- macOS에서 개발/테스트, GitHub Actions Windows runner에서 PyInstaller EXE 빌드.
- PyInstaller는 macOS → Windows 직접 크로스 컴파일을 지원하지 않으므로 Windows runner 필요.
- Windows 10/11 + 실제 Excel/학교 전산에서 별도 UAT.
- 저장소/빌드 아티팩트에 실자료를 넣지 않는다.

### 프로젝트 트리 초안
```
scholarship-payment-tool/
  CLAUDE.md
  docs/
  src/scholarship_payment/
    adapters/{base,daechung,multicultural,ai_mentoring}.py
    models/{batch,row}.py
    core/{validate,normalize}.py
    output/{template_writer,business_policy}.py
    gui/{main_window}.py
    main.py
  templates/payment_template.xlsx
  tests/{fixtures,unit,integration}/
  .github/workflows/build-windows.yml
  pyproject.toml
  .gitignore
```
