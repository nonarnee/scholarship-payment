# 템플릿 검증 실험 스크립트

설계 단계의 openpyxl 검증용 **일회성 실험 코드**다. 변환 엔진이 아니며 제품 코드에서 import하지 않는다.
결과와 해석은 `docs/TEMPLATE-ANALYSIS.md` §8~9, `docs/IMPLEMENTATION-PLAN.md` §3 참조.

| 파일 | 용도 |
|---|---|
| `analyze.py` | 샘플 xlsx를 **읽기 전용**으로 분석(스타일, 병합, 행 높이·열 너비, 수식 패턴, 셀 타입, 인쇄·조건부 서식). 개인정보 값은 출력하지 않고 구조·형식만 요약 |
| `exp.py` | **합성 데이터**로 방식 A(행 삽입·삭제) / 방식 B(스타일 복제 + 블록 재구성)를 N=1/32/45/70/120에서 실행하고 템플릿과 비교. 마지막에 템플릿 SHA-256 불변을 assert |

## 실행
```
# 공개 합성 템플릿으로 (누구나 재현 가능)
.venv/bin/python -I tools/synthetic/make_synthetic.py   # 합성 템플릿·입력 생성
.venv/bin/python -I tools/experiments/exp.py templates/synthetic_payment_template.xlsx "<출력 폴더>"
.venv/bin/python -I tools/experiments/analyze.py templates/synthetic_payment_template.xlsx
```
- 실제 업무자료(`samples/`, git 제외)를 분석할 때는 **로컬에서만** 실행하고 결과를 공개 문서·커밋에 옮기지 않는다(`docs/PUBLIC-SAFETY.md`).
- **출력 폴더는 프로젝트 밖 임시 경로**를 쓴다(`*.xlsx`는 `.gitignore` 대상이지만 생성물을 저장소에 두지 않는다).
- 실험 데이터는 전부 가상 값(`가상NNN`, `000-000-…`)이다. 실제 지급자료를 넣지 않는다.
- `exp.py`는 템플릿 시트명(`지급대상자명단(9월)`)과 행 번호(5, 50 등)를 상수로 가정한다. 다른 월·사업 템플릿에는 그대로 쓸 수 없다.
- 실험 한계: Excel/LibreOffice가 없는 환경에서 작성되어, 생성물의 Excel 열기 경고·인쇄 미리보기는 검증하지 않았다.
