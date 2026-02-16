from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

DEFAULT_OUTPUTS_DIR = Path.cwd() / "books" / "out"

def print_file_fallback(path: Path) -> None:
    """Open/print using OS file association (fallback)."""
    if platform.system() == "Windows":
        try:
            os.startfile(str(path), "print")
        except OSError as e:
            if getattr(e, "winerror", None) == 1155:
                messagebox.showwarning(
                    "Print setup",
                    "No default print handler for this file type.\nOpening file instead..."
                )
                os.startfile(str(path))
            else:
                raise
    else:
        subprocess.run(["lpr", str(path)], check=True)

def get_printer_names_windows() -> list[str]:
    cmd = ["powershell", "-NoProfile", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return [x.strip() for x in r.stdout.splitlines() if x.strip()]
    except Exception:
        return []

def print_to_specific_printer_windows(path: Path, printer: str) -> None:
    # relies on PDF handler supporting PrintTo verb
    cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        f'Start-Process -FilePath "{path}" -Verb PrintTo -ArgumentList "{printer}"'
    ]
    subprocess.run(cmd, check=True)

class PrintGUI(tk.Tk):
    def __init__(self, secret_mode: bool = False) -> None:
        super().__init__()
        self.secret_mode = secret_mode
        self.title("Print Book" + (" // SIGNAL UNLOCKED" if secret_mode else ""))
        self.geometry("720x360")

        if secret_mode:
            self.tk_setPalette(
                background="#111111",
                foreground="#00ff41",
                activeBackground="#00ff41",
                activeForeground="#111111",
            )

        self.selected_path = tk.StringVar()

        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=8)
        tk.Label(top, text="Selected file:").pack(side=tk.LEFT)
        tk.Entry(top, textvariable=self.selected_path, width=70).pack(side=tk.LEFT, padx=6)
        tk.Button(top, text="Browse...", command=self.browse_file).pack(side=tk.LEFT)

        mid = tk.Frame(self)
        mid.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        tk.Label(mid, text="Recent PDFs (books/out):").pack(anchor=tk.W)

        self.listbox = tk.Listbox(mid, height=12)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        bottom = tk.Frame(self)
        bottom.pack(fill=tk.X, padx=12, pady=8)
        tk.Button(bottom, text="Refresh", command=self.refresh).pack(side=tk.LEFT)
        tk.Button(bottom, text="Add Printer", command=self.on_add_printer).pack(side=tk.LEFT, padx=10)
        tk.Button(bottom, text="Terminal", command=self.on_open_terminal).pack(side=tk.LEFT)

        print_bg = "#003300" if secret_mode else "#0078d7"
        tk.Button(bottom, text="Print", command=self.on_print, fg="white", bg=print_bg).pack(side=tk.RIGHT)

        self.refresh()

    def on_open_terminal(self) -> None:
        try:
            if platform.system() == "Windows":
                os.system("start powershell")
            else:
                subprocess.Popen(["x-terminal-emulator"])
        except Exception as e:
            messagebox.showerror("Error", f"Could not open terminal: {e}")

    def on_add_printer(self) -> None:
        try:
            if platform.system() == "Windows":
                os.startfile("ms-settings:printers")
            else:
                messagebox.showinfo("Add Printer", "Use your system settings to add a printer.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open printer settings: {e}")

    def browse_file(self) -> None:
        p = filedialog.askopenfilename(
            title="Select PDF to print",
            initialdir=str(DEFAULT_OUTPUTS_DIR),
            filetypes=[("PDF Files", "*.pdf"), ("All Files", "*.*")]
        )
        if p:
            self.selected_path.set(p)

    def refresh(self) -> None:
        self.listbox.delete(0, tk.END)
        if not DEFAULT_OUTPUTS_DIR.exists():
            return

        files = sorted(DEFAULT_OUTPUTS_DIR.rglob("*.pdf"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files:
            rel = f.relative_to(DEFAULT_OUTPUTS_DIR)
            self.listbox.insert(tk.END, str(rel))

    def on_select(self, _evt) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        val = self.listbox.get(sel[0])
        full = DEFAULT_OUTPUTS_DIR / val
        self.selected_path.set(str(full))

    def on_print(self) -> None:
        p_str = self.selected_path.get().strip()
        if not p_str:
            messagebox.showwarning("No file", "Please select a file to print.")
            return

        p = Path(p_str)
        if not p.exists():
            messagebox.showerror("Print error", f"File not found:\n{p}")
            return

        # Smart printer suggestion (Windows)
        if platform.system() == "Windows":
            printers = get_printer_names_windows()
            best = next((x for x in printers if "EPSON" in x.upper() and "WF" in x.upper()), None) \
                   or next((x for x in printers if "EPSON" in x.upper()), None)

            if best:
                if messagebox.askyesno("Smart Print", f"Found printer:\n{best}\n\nPrint directly to it?"):
                    try:
                        print_to_specific_printer_windows(p, best)
                        messagebox.showinfo("Print", f"Sent to: {best}")
                        return
                    except Exception:
                        # fall through to fallback
                        pass

        try:
            print_file_fallback(p)
            messagebox.showinfo("Print", f"Sent to printer/viewer:\n{p.name}")
        except Exception as e:
            messagebox.showerror("Print error", f"Failed to print:\n{e}")

def main(secret_mode: bool = False) -> None:
    app = PrintGUI(secret_mode=secret_mode)
    app.mainloop()
