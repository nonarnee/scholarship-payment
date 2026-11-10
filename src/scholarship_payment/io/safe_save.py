"""안전 저장: 임시 파일에 쓰고 검증을 통과한 뒤에만 최종 이름으로 공개한다. **기존 파일은 절대 덮어쓰지 않는다.**
실패하면 임시 파일을 지워 부분 결과가 남지 않게 한다. 오류에는 값을 담지 않는다.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Mapping

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


RUN_PREFIX = ".~run-"          # 분리 저장 중 임시 폴더 이름(남아 있는 것은 이전 실행이 중단된 흔적일 수 있다)


def _folder_candidates(stem: str):
    yield stem
    for k in range(2, MAX_SUFFIX + 1):
        yield f"{stem}_{k}"


def save_set(workbooks: Mapping[str, object], out_dir: str | Path, folder_stem: str, suffixes: Mapping[str, str],
             verify_set: Callable[[dict[str, Path]], None]) -> tuple[Path, dict[str, Path]]:
    """여러 Workbook 을 **한 폴더**로 공개한다. 임시 폴더에 모두 쓰고 `verify_set({종류: 임시경로})` 가 통과하면
    폴더째 최종 이름(`folder_stem`, 있으면 `_2`, `_3`…)으로 바꾼다. 기존 파일·폴더는 건드리지 않고(빈 폴더도 재사용하지 않는다),
    실패하면 임시 폴더 전체를 지워 부분 결과가 남지 않는다. 파일 이름은 `<폴더명>_<접미어>.xlsx`."""
    folder = Path(out_dir)
    if not folder.is_dir():
        raise ValidationFailed([ValidationError("OUTPUT_DIR_MISSING", "out_dir")])
    tmp_dir: Path | None = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix=RUN_PREFIX, dir=folder))
        current = folder_stem
        paths = {k: tmp_dir / f"{current}_{suffixes[k]}.xlsx" for k in workbooks}
        for kind, wb in workbooks.items():
            wb.save(paths[kind])
        verify_set(dict(paths))
        for candidate in _folder_candidates(folder_stem):
            final = folder / candidate
            if final.exists() or final.is_symlink():
                continue
            if candidate != current:                         # 이름이 바뀌면 안의 파일 이름도 같은 규칙으로 맞춘다(내용은 그대로)
                renamed = {k: tmp_dir / f"{candidate}_{suffixes[k]}.xlsx" for k in paths}
                for k in paths:
                    os.replace(paths[k], renamed[k])
                paths, current = renamed, candidate
            try:
                os.rename(tmp_dir, final)                    # Windows 는 대상이 있으면 실패한다. POSIX 는 위에서 존재를 확인했다
            except FileExistsError:
                continue
            except OSError:
                if final.exists():
                    continue
                raise
            tmp_dir = None
            return final, {k: final / p.name for k, p in paths.items()}
        raise ValidationFailed([ValidationError("OUTPUT_NAME_EXHAUSTED", "filename")])
    except PermissionError:
        raise ValidationFailed([ValidationError("OUTPUT_PERMISSION", "out_dir")]) from None
    except OSError:
        raise ValidationFailed([ValidationError("OUTPUT_IO", "out_dir")]) from None
    finally:
        if tmp_dir is not None:
            shutil.rmtree(tmp_dir, ignore_errors=True)
