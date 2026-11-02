# 공개 안전성 도구

설계와 규칙은 `docs/PUBLIC-SAFETY.md`. 이 폴더는 구현이다. 표준 라이브러리만 쓴다(`build_denylist.py`만 openpyxl 필요).

| 파일 | 용도 |
|---|---|
| `check_public_safety.py` | 경로·엑셀 속성·패턴·로컬 금지어 검사. `--staged` / `--tracked` / `--worktree` / 파일 지정 |
| `build_denylist.py` | 비공개 xlsx에서 로컬 금지어 목록 생성(`.safety/denylist.local.txt`, git 무시) |
| `public_terms.txt` | 금지어에서 제외할 공개 용어(구조 라벨, 공개 사업명). **실값 금지** |
| `hooks/pre-commit`, `install-hooks.sh` | 커밋 전 자동 검사 설치 |

```
# 최초 1회
sh tools/safety/install-hooks.sh
.venv/bin/python -I tools/safety/build_denylist.py <비공개 xlsx ...>   # 실자료가 있는 PC에서만

# 수시/푸시 전
python3 -I tools/safety/check_public_safety.py --worktree
python3 -I tools/safety/check_public_safety.py --tracked
```
- 종료 코드 0 = 통과, 1 = 위반. 위반 출력에는 **일치한 값이 표시되지 않는다**.
- 검사기 자체 시험: `.venv/bin/python -m pytest tests/test_public_safety.py`
- 훅은 `git commit --no-verify`로 우회되므로 푸시 전 수동 검사가 필요하다.
