# 합성 데이터 도구

| 파일 | 용도 |
|---|---|
| `make_synthetic.py` | 완전 합성 엑셀 생성(입력 형식·출력 템플릿). **실제 파일을 읽지 않는다.** 입력 파일은 재단 다운로드 원본처럼 B·V·X 열과 합계행 일부를 빈 문자열 셀로 저장한다 |
| `check_fidelity.py` | **로컬 전용.** 실제 다운로드 원본과 합성 입력의 구조 서명(시트명·병합·숨김 열·헤더·셀 타입·합계행)을 비교해 **차이만** 출력한다. 값은 출력하지 않는다 |

```
.venv/bin/python -I tools/synthetic/make_synthetic.py
.venv/bin/python -I tools/synthetic/check_fidelity.py samples/<실제 월별지급승인.xlsx>   # 실자료가 있는 PC에서만
```
- 새 월의 원본을 받으면 `check_fidelity.py`로 형태가 바뀌었는지 먼저 확인한다(Adapter는 레이아웃이 다르면 차단한다).
- 출력의 상세는 공개 문서·커밋에 옮기지 않는다(`docs/PUBLIC-SAFETY.md`).
