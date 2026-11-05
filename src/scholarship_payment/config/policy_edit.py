"""기존 정책 JSON 수정: 불러오기 → 편집 내용 만들기 → 안전 저장.

- 수정은 사용자가 입력하는 5개 값(그리고 다문화·탈북학생 멘토링의 시급(도시)·시급(농어촌))만 바꾼다. 나머지 키·값과 키 순서는 그대로 둔다.
- 생성과 같은 검증(`policy_builder.validate_policy_dict` → `load_policy`)을 저장 전에 통과해야 한다.
- 저장은 ① 불러온 뒤 파일이 바뀌지 않았는지 SHA-256 으로 확인 ② 같은 폴더에 임시 파일 작성 ③ 교체 직전 다시 확인 ④ 이전 내용을 백업(`.bak`, 이미 있으면 `.bak.1` …,
  기존 백업은 덮어쓰거나 지우지 않는다) ⑤ `os.replace` 로 원자적 교체 순서다. 어느 단계에서 실패해도 기존 정책 파일은 바뀌지 않는다.
- 도시·농어촌 외의 시급 키가 있으면 수정 저장을 차단한다(기존 키를 지우지 않는다). 오류에는 코드와 키 이름만 담고 값은 담지 않는다(DI-13).
- 백업은 임시 파일에 먼저 쓰고 원본 바이트와 같은지 확인한 뒤에만 최종 이름(`.bak*`)으로 공개한다. 그래서 `.bak*` 이름에는 완전한 백업만 있다.
- **한계**: 마지막 SHA-256 확인과 `os.replace` 사이에 다른 프로그램이 같은 파일을 바꾸는 극히 짧은 경합은 완전히 막지 못한다(파일 잠금을 쓰지 않는다).
  강제 종료 시 `.policy-edit-*.tmp`·`.policy-backup-*.tmp` 임시 파일이 남을 수 있고 자동으로 정리하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from scholarship_payment.config.policy_builder import HIDDEN_FOR, RATE_KEYS, USER_KEYS, rates_from_fields, validate_policy_dict
from scholarship_payment.config.policy_file import KEYS, OPTIONAL_KEYS
from scholarship_payment.errors import ValidationError, ValidationFailed

CONFLICT, EXTRA_RATE_KEYS, BACKUP_FAILED, IO_ERROR = "POLICY_EDIT_CONFLICT", "POLICY_EDIT_EXTRA_RATE_KEYS", "POLICY_EDIT_BACKUP_FAILED", "POLICY_EDIT_IO"
_MAX_BACKUPS = 10000


def _fail(code: str, field_name: str = "file") -> ValidationFailed:
    return ValidationFailed([ValidationError(code, field_name)])


@dataclass(frozen=True)
class PolicyEditSession:
    """불러온 시점의 정책 파일. `sha256` 은 그때 읽은 바이트의 해시이며 저장 직전 충돌 확인의 기준이다. 값(`data`)은 repr 에 나오지 않는다."""
    path: Path
    sha256: str
    program: str
    data: dict = field(repr=False)


@dataclass(frozen=True)
class EditSaveResult:
    path: Path
    backup: Path | None
    sha256: str
    changed: bool


def _read_current(path) -> bytes:
    try:
        return Path(path).read_bytes()
    except FileNotFoundError:
        raise _fail("POLICY_FILE_MISSING") from None
    except OSError:
        raise _fail("POLICY_UNREADABLE") from None


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def open_for_edit(path: str | Path, program: str) -> PolicyEditSession:
    """수정할 정책 파일을 읽는다. 파일을 바꾸지 않는다. 읽을 수 없거나 구조가 맞지 않거나 추가 시급 키가 있으면 ValidationFailed.
    자리표시자가 남은 초안도 열 수 있다(값은 저장할 때 검증한다)."""
    p = Path(path)
    if not p.is_file():
        raise _fail("POLICY_FILE_MISSING")
    raw = _read_current(p)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise _fail("POLICY_UNREADABLE") from None
    if not isinstance(data, dict):
        raise _fail("POLICY_NOT_OBJECT")
    if set(data) - set(KEYS) - set(OPTIONAL_KEYS):
        raise _fail("POLICY_KEY_UNKNOWN", "keys")
    missing = [k for k in KEYS if k not in data]
    if missing:
        raise ValidationFailed([ValidationError("POLICY_KEY_MISSING", k) for k in missing])
    if program in HIDDEN_FOR and "hourly_rates" in data:
        rates = data["hourly_rates"]
        if not isinstance(rates, dict):
            raise _fail("POLICY_TYPE", "hourly_rates")
        if set(rates) - set(RATE_KEYS):
            raise _fail(EXTRA_RATE_KEYS, "hourly_rates")          # 기존 키를 지우지 않으려고 수정을 막는다
    return PolicyEditSession(path=p, sha256=_digest(raw), program=program, data=data)


def edited_data(session: PolicyEditSession, values: dict, rate_values: dict | None = None) -> dict:
    """화면에서 입력한 값으로 새 정책 dict 를 만든다(원본 객체는 바꾸지 않는다). 5개 값은 비어 있으면 안 되고,
    다문화·탈북학생 멘토링은 시급(도시)·시급(농어촌) 두 칸이 모두 필요하다. 그 밖의 키·값·순서는 그대로다."""
    blank = [k for k in USER_KEYS if not isinstance(values.get(k), str) or not values[k].strip()]
    if blank:
        raise ValidationFailed([ValidationError("POLICY_KEY_MISSING", k) for k in blank])
    new = dict(session.data)
    for k in USER_KEYS:
        new[k] = values[k]
    if session.program in HIDDEN_FOR:
        given = rates_from_fields((rate_values or {}).get("rate_urban"), (rate_values or {}).get("rate_rural"))
        old = session.data.get("hourly_rates") if isinstance(session.data.get("hourly_rates"), dict) else {}
        merged = {k: given[k] for k in old if k in given}            # 기존 키 순서를 지킨다
        merged.update({k: v for k, v in given.items() if k not in merged})
        new["hourly_rates"] = merged
    return new


def _write_synced(fd: int, data: bytes) -> None:
    """열려 있는 파일 기술자 fd 에 data 를 쓰고 디스크에 내린 뒤 닫는다."""
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _same_bytes(path, expected: bytes) -> bool:
    try:
        return Path(path).read_bytes() == expected
    except OSError:
        return False


def _publish_exclusive_copy(dest: Path, content: bytes) -> bool:
    """하드링크를 쓸 수 없는 저장소용: dest 를 새로 만들어(이미 있으면 False) 쓰고 내용을 확인한다.
    쓰기·확인에 실패하면 **이번에 만든** dest 만 지우고 BACKUP_FAILED. 처음부터 만들지 못한 경우에는 아무것도 지우지 않는다."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(dest, flags, 0o600)
    except FileExistsError:
        return False
    except OSError:
        raise _fail(BACKUP_FAILED) from None
    try:                                                      # 여기부터 dest 는 이번에 만든 파일이다
        _write_synced(fd, content)
        if not _same_bytes(dest, content):
            raise OSError("backup mismatch")
    except OSError:
        try:
            dest.unlink()
        except OSError:
            pass
        raise _fail(BACKUP_FAILED) from None
    return True


def _create_backup(path: Path, content: bytes) -> Path:
    """이전 내용을 `<파일명>.bak`, 이미 있으면 `.bak.1`, `.bak.2` … 로 저장한다.
    먼저 같은 폴더의 임시 파일에 쓰고 원본 바이트와 같은지 확인한 **뒤에만** 최종 이름으로 공개한다(하드링크는 기존 이름을 덮어쓰지 않는다).
    그래서 `.bak*` 이름에는 완전하고 검증된 백업만 있다. 기존 백업은 덮어쓰거나 지우지 않는다."""
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".policy-backup-", suffix=".tmp")
    except OSError:
        raise _fail(BACKUP_FAILED) from None
    tmp = Path(tmp_name)
    try:
        try:
            _write_synced(fd, content)
        except OSError:
            raise _fail(BACKUP_FAILED) from None
        if not _same_bytes(tmp, content):                     # 오류 없이 다르게 기록된 경우도 정상 백업으로 보지 않는다
            raise _fail(BACKUP_FAILED)
        try:
            shutil.copymode(path, tmp)                        # 원본의 권한을 따른다(실패해도 계속)
        except OSError:
            pass
        for n in range(_MAX_BACKUPS):
            dest = path.with_name(path.name + (".bak" if n == 0 else f".bak.{n}"))
            try:
                os.link(tmp, dest)
                return dest
            except FileExistsError:
                continue
            except OSError:                                    # 하드링크를 쓸 수 없는 저장소: 새 파일로 직접 복사한다
                if _publish_exclusive_copy(dest, content):
                    return dest
        raise _fail(BACKUP_FAILED)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def save_policy_replace(session: PolicyEditSession, new_data: dict) -> EditSaveResult:
    """검증을 통과한 정책으로 같은 경로의 파일을 교체한다. 실패하면 ValidationFailed 이고 기존 파일은 바뀌지 않는다.
    내용이 같으면 아무것도 쓰지 않고(백업 포함) changed=False 를 돌려준다."""
    try:
        text = validate_policy_dict(new_data)
    except OSError:                                                    # 검증용 임시 파일을 만들 수 없는 경우(값 문제가 아니다)
        raise _fail(IO_ERROR) from None
    path = session.path
    current = _read_current(path)
    if _digest(current) != session.sha256:
        raise _fail(CONFLICT)
    if new_data == session.data:
        return EditSaveResult(path, None, session.sha256, False)
    try:
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".policy-edit-", suffix=".tmp")
    except OSError:
        raise _fail(IO_ERROR) from None
    tmp = Path(tmp_name)
    # 바이트로 직접 쓴다: 텍스트 모드는 Windows 에서 \n 을 \r\n 으로 바꿔 해시가 실제 파일과 어긋난다. 줄바꿈은 원본 파일을 따른다.
    payload = (text.replace("\n", "\r\n") if b"\r\n" in current else text).encode("utf-8")
    try:
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            try:
                shutil.copymode(path, tmp)                             # 원래 파일의 권한을 따른다(실패해도 저장은 계속)
            except OSError:
                pass
        except OSError:
            raise _fail(IO_ERROR) from None
        if _digest(_read_current(path)) != session.sha256:             # 교체 직전에 한 번 더 확인한다
            raise _fail(CONFLICT)
        backup = _create_backup(path, current)
        try:
            os.replace(tmp, path)
        except OSError:
            raise _fail(IO_ERROR) from None
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return EditSaveResult(path, backup, _digest(payload), True)
