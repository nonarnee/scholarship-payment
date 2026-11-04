"""사용자 설정(Qt 무관). 저장하는 것은 **사업 선택값과 사업별 경로 3개(템플릿·정책·기본 저장 폴더)뿐**이다.
원본 파일 경로·비밀번호·기준일·학생 정보는 이 모듈이 다루지 않는다(허용 키 목록 밖의 값은 읽을 때도 쓸 때도 버린다).

- 손상된 파일은 `settings.json.bak`(이미 있으면 `.bak.1`, `.bak.2` …)로 **보존**하고 기본값으로 시작한다. 기존 백업은 덮어쓰지 않는다.
  보존에 실패해도 기본값으로 시작하며 원본은 지우지 않는다.
- 저장은 같은 폴더의 임시 파일에 쓴 뒤 `os.replace`로 바꾼다(이 파일은 사용자 설정 전용이라 덮어쓰기가 의도이며, 업무 출력 파일과 다르다).
- 로그를 남기지 않고, 결과 객체에도 경로·예외 메시지·파일 내용을 담지 않는다(상태 코드와 백업 파일 이름만).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field, replace
from pathlib import Path

from scholarship_payment.config.default_paths import search_dirs

PROGRAMS = ("daechung", "multicultural", "ai")
VERSION = 1
FILE_NAME = "settings.json"
MAX_BYTES = 1024 * 1024
MAX_PATH_LEN = 1024
PATH_KEYS = ("template_path", "policy_path", "out_dir")

LOAD_OK, LOAD_MISSING, LOAD_RECOVERED = "ok", "missing", "recovered"
LOAD_RESET_UNPRESERVED, LOAD_UNREADABLE = "reset_unpreserved", "unreadable"
SAVE_FAILED = "SETTINGS_SAVE_FAILED"


@dataclass(frozen=True)
class ProgramPaths:
    template_path: str | None = None
    policy_path: str | None = None
    out_dir: str | None = None


@dataclass(frozen=True)
class UserSettings:
    last_program: str | None = None
    programs: dict = field(default_factory=dict)          # {program: ProgramPaths}, 저장된 사업만

    def paths(self, program: str) -> ProgramPaths:
        return self.programs.get(program, ProgramPaths())

    def with_paths(self, program: str, **changes) -> "UserSettings":
        if program not in PROGRAMS or set(changes) - set(PATH_KEYS):
            raise ValueError("invalid program or key")
        merged = {**self.programs, program: replace(self.paths(program), **changes)}
        return replace(self, programs=merged)

    def with_last_program(self, program: str | None) -> "UserSettings":
        if program is not None and program not in PROGRAMS:
            raise ValueError("invalid program")
        return replace(self, last_program=program)

    def clear_program(self, program: str) -> "UserSettings":
        return replace(self, programs={k: v for k, v in self.programs.items() if k != program})


@dataclass(frozen=True)
class LoadResult:
    settings: UserSettings
    status: str
    backup_name: str | None = None


@dataclass(frozen=True)
class SaveResult:
    ok: bool
    code: str | None = None


def settings_path() -> Path:
    """사용자 설정 폴더(Windows: %APPDATA%\\ScholarshipPayment)의 settings.json. 정책·템플릿 기본 위치와 같은 폴더다."""
    return search_dirs()[-1] / FILE_NAME


class _Corrupt(Exception):
    pass


def _clean_path(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_PATH_LEN or "\x00" in value:
        raise _Corrupt
    return value or None


def _parse(raw: bytes) -> UserSettings:
    if len(raw) > MAX_BYTES:
        raise _Corrupt
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _Corrupt from None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise _Corrupt
    last = data.get("last_program")
    if last is not None and not isinstance(last, str):
        raise _Corrupt
    progs = data.get("programs", {})
    if not isinstance(progs, dict):
        raise _Corrupt
    out: dict = {}
    for code, entry in progs.items():
        if not isinstance(code, str) or code not in PROGRAMS:
            continue                                     # 알 수 없는 사업 코드는 버린다
        if not isinstance(entry, dict):
            raise _Corrupt
        out[code] = ProgramPaths(**{k: _clean_path(entry.get(k)) for k in PATH_KEYS})
    return UserSettings(last_program=last if last in PROGRAMS else None, programs=out)


def _free_backup_name(path: Path) -> Path:
    base = path.with_name(path.name + ".bak")
    if not base.exists():
        return base
    n = 1
    while True:
        cand = path.with_name(f"{path.name}.bak.{n}")
        if not cand.exists():
            return cand
        n += 1


def _preserve(path: Path) -> str:
    """손상 파일을 기존 백업을 건드리지 않고 새 이름으로 옮긴다(복사 후 삭제). 성공 시 백업 파일 이름."""
    while True:
        dest = _free_backup_name(path)
        try:
            with open(path, "rb") as src, open(dest, "xb") as dst:   # "x": 이미 있으면 실패 → 다음 이름
                shutil.copyfileobj(src, dst)
        except FileExistsError:
            continue
        break
    try:
        path.unlink()
    except OSError:
        pass                                                         # 복사본이 있으므로 보존은 성공으로 본다
    return dest.name


def load(path: Path | None = None) -> LoadResult:
    path = settings_path() if path is None else Path(path)
    if not path.is_file():
        return LoadResult(UserSettings(), LOAD_MISSING)
    try:
        raw = path.read_bytes() if path.stat().st_size <= MAX_BYTES else b"x" * (MAX_BYTES + 1)
    except OSError:
        return LoadResult(UserSettings(), LOAD_UNREADABLE)
    try:
        return LoadResult(_parse(raw), LOAD_OK)
    except _Corrupt:
        pass
    try:
        return LoadResult(UserSettings(), LOAD_RECOVERED, _preserve(path))
    except Exception:                                                # 보존 실패(권한·디스크 등): 이유는 남기지 않는다
        return LoadResult(UserSettings(), LOAD_RESET_UNPRESERVED)


def _serialize(settings: UserSettings) -> str:
    programs = {}
    for code in PROGRAMS:
        if code in settings.programs:
            p = settings.programs[code]
            programs[code] = {k: getattr(p, k) for k in PATH_KEYS if getattr(p, k)}
    return json.dumps({"version": VERSION, "last_program": settings.last_program, "programs": programs}, ensure_ascii=False, indent=2) + "\n"


def save(settings: UserSettings, path: Path | None = None) -> SaveResult:
    """원자적으로 저장한다. 실패해도 예외를 내지 않고 코드만 돌려준다(이전 파일은 그대로)."""
    path = settings_path() if path is None else Path(path)
    tmp = None
    try:
        text = _serialize(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        tmp = None
        return SaveResult(True)
    except Exception:
        return SaveResult(False, SAVE_FAILED)
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
