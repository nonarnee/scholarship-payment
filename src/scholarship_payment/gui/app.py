"""Tkinter 화면(얇은 껍데기): 파일 선택 → run_conversion 호출 → 결과 표시 → 결과 폴더 열기.
업무 계산·변환 규칙은 두지 않는다(app.controller 가 담당). 화면에는 규칙 코드·건수·경로만 표시한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scholarship_payment.app.controller import run_conversion

DEFAULT_TEMPLATE = Path(__file__).resolve().parents[3] / "templates" / "synthetic_payment_template.xlsx"
PROGRAM = "daechung"         # 현재 지원: 대청교만


def open_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))                       # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, ttk

    root = tk.Tk()
    root.title("장학금 지급명단 변환 (대청교)")
    root.geometry("720x520")
    v_in, v_out = tk.StringVar(), tk.StringVar()
    v_tpl, v_pol, v_date = tk.StringVar(value=str(DEFAULT_TEMPLATE)), tk.StringVar(), tk.StringVar()
    state: dict[str, Path | None] = {"out": None}

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    def row(r: int, label: str, var, pick) -> None:
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky="w", pady=4)
        ttk.Entry(frm, textvariable=var).grid(row=r, column=1, sticky="ew", padx=6)
        ttk.Button(frm, text="찾기", command=pick).grid(row=r, column=2)

    def pick_file(var, types):
        return lambda: var.set(filedialog.askopenfilename(filetypes=types) or var.get())

    def pick_dir():
        v_out.set(filedialog.askdirectory() or v_out.get())

    row(0, "재단 원본(월별지급승인)", v_in, pick_file(v_in, [("Excel", "*.xlsx")]))
    row(1, "결과 저장 폴더", v_out, pick_dir)
    row(2, "출력 템플릿", v_tpl, pick_file(v_tpl, [("Excel", "*.xlsx")]))
    row(3, "정책 파일(JSON)", v_pol, pick_file(v_pol, [("JSON", "*.json")]))
    ttk.Label(frm, text="기준일(YYYY.MM.DD, 비우면 오늘)").grid(row=4, column=0, sticky="w", pady=4)
    ttk.Entry(frm, textvariable=v_date, width=14).grid(row=4, column=1, sticky="w", padx=6)

    log = tk.Text(frm, height=14, state="disabled", wrap="word")
    log.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=8)
    frm.rowconfigure(6, weight=1)
    btn_open = ttk.Button(frm, text="결과 폴더 열기", state="disabled", command=lambda: open_folder(state["out"].parent))

    def show(lines: list[str]) -> None:
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.insert("end", "\n".join(lines))
        log.configure(state="disabled")

    def run() -> None:
        btn_open.configure(state="disabled")
        o = run_conversion(PROGRAM, v_in.get().strip(), v_out.get().strip(), v_tpl.get().strip(),
                           v_pol.get().strip() or None, v_date.get().strip() or None)
        show([o.summary, *o.details] + ([f"저장 위치: {o.output_path}"] if o.ok else []))
        state["out"] = o.output_path
        if o.ok:
            btn_open.configure(state="normal")

    ttk.Button(frm, text="변환 실행", command=run).grid(row=5, column=0, columnspan=2, sticky="w", pady=8)
    btn_open.grid(row=5, column=2)
    root.mainloop()
