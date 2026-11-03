"""사업별 기본 정책 파일 위치. 실제 상수가 든 파일은 저장소·exe 에 넣지 않고, 사용자 PC 의 정해진 위치에서 찾는다.
찾는 순서: ① 실행 파일(exe)이 있는 폴더 ② 사용자 설정 폴더(Windows: %APPDATA%\\ScholarshipPayment). 파일명: policy_<사업코드>.json
파일 내용은 읽지 않는다(경로만 돌려준다). 내용 검증은 변환 때 load_policy 가 한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        dirs.append(Path(sys.executable).resolve().parent)
    appdata = os.environ.get("APPDATA")
    dirs.append(Path(appdata) / "ScholarshipPayment" if appdata else Path.home() / ".config" / "scholarship_payment")
    return dirs


def default_policy_path(program: str, dirs: list[Path] | None = None) -> Path | None:
    name = f"policy_{program}.json"
    for d in (search_dirs() if dirs is None else dirs):
        p = d / name
        if p.is_file():
            return p
    return None
