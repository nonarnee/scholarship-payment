"""안전 저장: 임시 파일에 쓰고 검증을 통과한 뒤에만 최종 이름으로 공개한다. **기존 파일은 절대 덮어쓰지 않는다.**
실패하면 임시 파일을 지워 부분 결과가 남지 않게 한다. 오류에는 값을 담지 않는다.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Callable

from scholarship_payment.errors import ValidationError, ValidationFailed

MAX_SUFFIX = 999


def _candidates(base: str):
    stem, dot, ext = base.rpartition(".")
    yield base
    for k in range(2, MAX_SUFFIX + 1):
        yield f"{stem}_{k}{dot}{ext}"


def _publish(tmp: Path, final: Path) -> bool:
    """최종 이름이 비어 있을 때만 만든다. 이미 있으면 False."""
    try:
        os.link(tmp, final)                 # 원자적이며 대상이 있으면 FileExistsError
        return True
    except FileExistsError:
        return False
    except OSError:                         # 하드링크를 지원하지 않는 파일시스템: 배타 생성 후 복사
        try:
            with open(final, "xb") as dst, open(tmp, "rb") as src:
                dst.write(src.read())
            return True
        except FileExistsError:
            return False
        except BaseException:
            final.unlink(missing_ok=True)
            raise


def save_new(wb, out_dir: str | Path, filename: str, verify: Callable[[Path], None]) -> Path:
    """`wb`를 저장하고 `verify(임시경로)`가 통과하면 `out_dir/filename`(있으면 `_2`, `_3`…)으로 공개한다."""
    folder = Path(out_dir)
    if not folder.is_dir():
        raise ValidationFailed([ValidationError("OUTPUT_DIR_MISSING", "out_dir")])
    tmp: Path | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=".~", suffix=".xlsx", dir=folder)
        os.close(fd)
        tmp = Path(name)
        wb.save(tmp)
        verify(tmp)
        for candidate in _candidates(filename):
            final = folder / candidate
            if _publish(tmp, final):
                return final
        raise ValidationFailed([ValidationError("OUTPUT_NAME_EXHAUSTED", "filename")])
    except PermissionError:
        raise ValidationFailed([ValidationError("OUTPUT_PERMISSION", "out_dir")]) from None
    except OSError:
        raise ValidationFailed([ValidationError("OUTPUT_IO", "out_dir")]) from None
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
