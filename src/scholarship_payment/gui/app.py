"""Tkinter 화면(얇은 껍데기): 파일 선택 → run_conversion 호출 → 결과 표시 → 결과 폴더 열기.
업무 계산·변환 규칙은 두지 않는다(app.controller 가 담당). 화면에는 규칙 코드·건수·경로만 표시한다.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from scholarship_payment import __version__
from scholarship_payment.app.controller import run_conversion
from scholarship_payment.config.default_paths import default_policy_path, default_template_path, search_dirs
from scholarship_payment.config.policy_builder import HIDDEN_FOR, PROMPTS, RATES_PROMPT, make_policy_file
from scholarship_payment.errors import ValidationFailed

MAX_PASSWORD_TRIES = 3
PROGRAMS = {"대청교": "daechung", "다문화·탈북학생 멘토링": "multicultural", "AI멘토링": "ai"}


def open_folder(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(str(path))                       # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, simpledialog, ttk

    root = tk.Tk()
    root.title(f"장학금 지급명단 변환 v{__version__}")
    root.geometry("720x520")
    v_in, v_out = tk.StringVar(), tk.StringVar()
    v_prog = tk.StringVar(value=next(iter(PROGRAMS)))
    v_tpl, v_pol, v_date = tk.StringVar(), tk.StringVar(), tk.StringVar()
    last_default = {"tpl": "", "pol": ""}

    def program() -> str:
        return PROGRAMS[v_prog.get()]

    def fill_defaults(*_) -> None:
        """사용자 PC 에 해당 사업의 템플릿·정책 파일이 있으면 미리 채운다(직접 고른 값은 덮어쓰지 않는다)."""
        tpl, pol = default_template_path(program()), default_policy_path(program())
        for var, key, path in ((v_tpl, "tpl", tpl), (v_pol, "pol", pol)):
            if var.get() in ("", last_default[key]):
                var.set(str(path) if path else "")
            last_default[key] = str(path) if path else ""
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

    ttk.Label(frm, text="사업").grid(row=0, column=0, sticky="w", pady=4)
    cb = ttk.Combobox(frm, textvariable=v_prog, values=list(PROGRAMS), state="readonly")
    cb.grid(row=0, column=1, sticky="w", padx=6)
    cb.bind("<<ComboboxSelected>>", fill_defaults)
    row(1, "재단 원본(월별지급 파일)", v_in, pick_file(v_in, [("Excel", "*.xlsx")]))
    row(2, "결과 저장 폴더", v_out, pick_dir)
    row(3, "출력 템플릿", v_tpl, pick_file(v_tpl, [("Excel", "*.xlsx")]))
    row(4, "정책 파일(JSON)", v_pol, pick_file(v_pol, [("JSON", "*.json")]))
    ttk.Label(frm, text="기준일(YYYY.MM.DD, 비우면 오늘)").grid(row=5, column=0, sticky="w", pady=4)
    ttk.Entry(frm, textvariable=v_date, width=14).grid(row=5, column=1, sticky="w", padx=6)
    fill_defaults()

    log = tk.Text(frm, height=14, state="disabled", wrap="word")
    log.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=8)
    frm.rowconfigure(7, weight=1)
    btn_open = ttk.Button(frm, text="결과 폴더 열기", state="disabled", command=lambda: open_folder(state["out"].parent))

    def show(lines: list[str]) -> None:
        log.configure(state="normal")
        log.delete("1.0", "end")
        log.insert("end", "\n".join(lines))
        log.configure(state="disabled")

    def run() -> None:
        btn_open.configure(state="disabled")
        args = (program(), v_in.get().strip(), v_out.get().strip(), v_tpl.get().strip(), v_pol.get().strip() or None,
                v_date.get().strip() or None)
        o = run_conversion(*args)
        for _ in range(MAX_PASSWORD_TRIES):
            if not o.needs_password:
                break
            pw = simpledialog.askstring("비밀번호", o.summary + "\n원본 파일 비밀번호를 입력하세요.", show="*", parent=root)
            if not pw:                                   # 취소
                break
            o = run_conversion(*args, password=pw)
            pw = None
        show([o.summary, *o.details] + ([f"저장 위치: {o.output_path}"] if o.ok else []))
        state["out"] = o.output_path
        if o.ok:
            btn_open.configure(state="normal")

    def make_policy() -> None:
        tpl = v_tpl.get().strip()
        if not tpl:
            show(["먼저 출력 템플릿을 선택하세요(정책 파일은 템플릿에서 머리글을 읽어 만듭니다)."])
            return
        dlg = tk.Toplevel(root)
        dlg.title("정책 파일 만들기")
        dlg.columnconfigure(1, weight=1)
        prog = program()
        labels = dict(PROMPTS)
        if prog in HIDDEN_FOR:
            labels["rates"] = RATES_PROMPT
        vars_ = {k: tk.StringVar() for k in labels}
        for i, (k, label) in enumerate(labels.items()):
            ttk.Label(dlg, text=label).grid(row=i, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(dlg, textvariable=vars_[k], width=48).grid(row=i, column=1, sticky="ew", padx=8)
        msg = ttk.Label(dlg, text="", foreground="#b00020")
        msg.grid(row=len(labels) + 1, column=0, columnspan=2, sticky="w", padx=8)

        def save() -> None:
            home = search_dirs()[-1]                      # 기본 저장 위치: 다음 실행 때 자동으로 채워지는 곳
            try:
                home.mkdir(parents=True, exist_ok=True)
            except OSError:
                home = None
            out = filedialog.asksaveasfilename(parent=dlg, defaultextension=".json", filetypes=[("JSON", "*.json")], title="정책 파일 저장 위치",
                                               initialfile=f"policy_{prog}.json", **({"initialdir": str(home)} if home else {}))
            if not out:
                return
            try:
                entered = {k: v.get() for k, v in vars_.items()}
                rates_text = entered.pop("rates", None)
                path = make_policy_file(tpl, entered, out, prog, rates_text)
            except ValidationFailed as e:
                msg.configure(text="만들지 못했습니다: " + "; ".join(str(x) for x in e.errors[:5]))
                return
            v_pol.set(str(path))
            dlg.destroy()
            show([f"정책 파일을 만들었습니다: {path}"])

        ttk.Button(dlg, text="저장", command=save).grid(row=len(labels), column=1, sticky="e", padx=8, pady=8)

    ttk.Button(frm, text="정책 파일 만들기", command=make_policy).grid(row=5, column=2)
    ttk.Button(frm, text="변환 실행", command=run).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)
    btn_open.grid(row=6, column=2)
    root.mainloop()
