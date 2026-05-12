import os
import shutil
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
from pathlib import Path

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass  # HEIC support unavailable but app still works for other formats

from PIL import Image

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".heic", ".heif", ".cr2", ".nef", ".arw",
    ".dng", ".raw", ".bmp",
}

EXIF_DATETIME_ORIGINAL = 36867
EXIF_DATETIME          = 306


def get_exif_date(filepath):
    try:
        img  = Image.open(filepath)
        exif = img.getexif()
        raw  = exif.get(EXIF_DATETIME_ORIGINAL) or exif.get(EXIF_DATETIME)
        if raw:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def unique_dest(folder, filename):
    dest = folder / filename
    if not dest.exists():
        return dest
    stem, suffix = Path(filename).stem, Path(filename).suffix
    counter = 1
    while dest.exists():
        dest = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return dest


def organize(src, dst, on_progress, on_status):
    src, dst = Path(src), Path(dst)

    files = [
        p for p in src.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    total     = len(files)
    organized = 0
    unsorted  = 0
    errors    = 0

    on_status(f"Found {total} images…")

    for i, filepath in enumerate(files):
        dt = get_exif_date(filepath)

        if dt:
            dest_dir = dst / str(dt.year) / f"{dt.month:02d}" / f"{dt.day:02d}"
        else:
            dest_dir = dst / "_unsorted"
            unsorted += 1

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = unique_dest(dest_dir, filepath.name)

        try:
            shutil.copy2(filepath, dest_path)
            organized += 1
        except Exception:
            errors += 1

        on_progress((i + 1) / total * 100)
        on_status(f"Copying {i + 1} of {total}: {filepath.name}")

    return organized, unsorted, errors


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Photo Organizer")
        self.resizable(False, False)
        self.configure(padx=24, pady=20, bg="#f5f5f5")
        self._build_ui()

    def _build_ui(self):
        label_opts = dict(bg="#f5f5f5", anchor="w", font=("Helvetica", 12))
        entry_opts = dict(width=46, font=("Helvetica", 11))

        # Source
        tk.Label(self, text="Source folder", **label_opts).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.src_var = tk.StringVar()
        src_row = tk.Frame(self, bg="#f5f5f5")
        src_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        tk.Entry(src_row, textvariable=self.src_var, **entry_opts).pack(side="left")
        tk.Button(src_row, text="Browse", command=self._pick_src,
                  font=("Helvetica", 11), padx=8).pack(side="left", padx=(8, 0))

        # Destination
        tk.Label(self, text="Destination folder", **label_opts).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.dst_var = tk.StringVar()
        dst_row = tk.Frame(self, bg="#f5f5f5")
        dst_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        tk.Entry(dst_row, textvariable=self.dst_var, **entry_opts).pack(side="left")
        tk.Button(dst_row, text="Browse", command=self._pick_dst,
                  font=("Helvetica", 11), padx=8).pack(side="left", padx=(8, 0))

        # Progress
        self.progress = ttk.Progressbar(self, length=460, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status_var, bg="#f5f5f5",
                 fg="#666", font=("Helvetica", 10), anchor="w").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(0, 16))

        # Button
        self.btn = tk.Button(
            self, text="Organize Photos", command=self._run,
            font=("Helvetica", 13, "bold"), bg="#4A90D9", fg="white",
            padx=16, pady=8, relief="flat", cursor="hand2",
        )
        self.btn.grid(row=6, column=0, columnspan=2)
        self.columnconfigure(0, weight=1)

    def _pick_src(self):
        p = filedialog.askdirectory(title="Select source folder")
        if p:
            self.src_var.set(p)

    def _pick_dst(self):
        p = filedialog.askdirectory(title="Select destination folder")
        if p:
            self.dst_var.set(p)

    def _run(self):
        src, dst = self.src_var.get().strip(), self.dst_var.get().strip()
        if not src or not dst:
            messagebox.showwarning("Missing folders",
                                   "Please select both a source and destination folder.")
            return
        if src == dst:
            messagebox.showwarning("Same folder",
                                   "Source and destination must be different folders.")
            return

        self.btn.config(state="disabled")
        self.progress["value"] = 0

        def worker():
            organized, unsorted, errors = organize(
                src, dst,
                on_progress=lambda pct: self.after(0, lambda p=pct: self.progress.configure(value=p)),
                on_status=lambda msg: self.after(0, lambda m=msg: self.status_var.set(m)),
            )
            self.after(0, lambda: self._done(organized, unsorted, errors))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, organized, unsorted, errors):
        self.btn.config(state="normal")
        self.status_var.set("Done.")
        lines = [f"{organized} image{'s' if organized != 1 else ''} organized by date."]
        if unsorted:
            lines.append(f"{unsorted} copied to _unsorted (no EXIF date).")
        if errors:
            lines.append(f"{errors} file{'s' if errors != 1 else ''} could not be copied.")
        messagebox.showinfo("Done", "\n".join(lines))


if __name__ == "__main__":
    app = App()
    app.mainloop()
