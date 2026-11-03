"""CI 전용: 합성 입력을 만들어 명령줄 변환이 끝까지 되는지 확인한다(합성 데이터만 사용)."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "synthetic"))
import make_synthetic as mk  # noqa: E402

from scholarship_payment.app.controller import run_conversion  # noqa: E402

with tempfile.TemporaryDirectory() as d:
    src, out = Path(d) / "synthetic_input.xlsx", Path(d) / "out"
    out.mkdir()
    mk.save_input(src, 45, "numeric")
    o = run_conversion("daechung", src, out, ROOT / "templates" / "synthetic_payment_template.xlsx")
    print(o.summary)
    sys.exit(0 if o.ok and o.count == 45 and o.output_path.exists() else 1)
