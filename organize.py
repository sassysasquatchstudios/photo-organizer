import os
import re
import shutil
import threading
import tkinter as tk
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

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
XMP_DATE_PATTERN = re.compile(
    r'(?:DateCreated|CreateDate)[^\d]+([\d]{4}-[\d]{2}-[\d]{2})'
    r'(?:T([\d]{2}:[\d]{2}:[\d]{2}))?'
)


def get_xmp_date(img):
    try:
        xmp = img.info.get("xmp", b"")
        if xmp:
            xmp_str = xmp.decode("utf-8", errors="ignore")
            match = XMP_DATE_PATTERN.search(xmp_str)
            if match:
                date_str = match.group(1)
                time_str = match.group(2)
                fmt = "%Y-%m-%d %H:%M:%S" if time_str else "%Y-%m-%d"
                combined = f"{date_str} {time_str}" if time_str else date_str
                return datetime.strptime(combined, fmt)
    except Exception:
        pass
    return None


def get_exif_date(filepath):
    try:
        img  = Image.open(filepath)
        exif = img.getexif()

        # 1. EXIF DateTimeOriginal — camera-written, most accurate
        raw = exif.get(EXIF_DATETIME_ORIGINAL)
        if raw:
            return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")

        # 2. XMP DateCreated / CreateDate — Lightroom/editor written, what Windows shows
        xmp_date = get_xmp_date(img)
        if xmp_date:
            return xmp_date

        # 3. EXIF DateTime — often the export date, least reliable
        raw = exif.get(EXIF_DATETIME)
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


SHOOT_GAP_MINUTES = 20


def organize(src, dst, on_progress, on_status):
    src, dst = Path(src), Path(dst)

    all_files = [
        p for p in src.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    total = len(all_files)
    on_status(f"Found {total} images, reading dates…")

    # Pass 1 — read dates (50% of progress)
    dated    = defaultdict(list)  # (year, month, day) → [(dt, path), ...]
    unsorted = []

    for i, filepath in enumerate(all_files):
        dt = get_exif_date(filepath)
        if dt:
            dated[(dt.year, dt.month, dt.day)].append((dt, filepath))
        else:
            unsorted.append(filepath)
        on_progress((i + 1) / total * 50)

    # Build copy task list — sort within each day and group into shoots
    copy_tasks = []  # [(filepath, dest_dir)]

    for (year, month, day), files in dated.items():
        files.sort(key=lambda x: x[0])
        base = dst / str(year) / f"{month:02d}" / f"{day:02d}"
        shoot_num = 1
        prev_dt   = None

        for dt, filepath in files:
            if prev_dt is not None:
                gap_mins = (dt - prev_dt).total_seconds() / 60
                if gap_mins > SHOOT_GAP_MINUTES:
                    shoot_num += 1
            copy_tasks.append((filepath, base / f"shoot-{shoot_num:02d}"))
            prev_dt = dt

    for filepath in unsorted:
        copy_tasks.append((filepath, dst / "_unsorted"))

    # Pass 2 — copy files (remaining 50% of progress)
    organized     = 0
    unsorted_count = 0
    errors        = 0
    n             = len(copy_tasks)

    for i, (filepath, dest_dir) in enumerate(copy_tasks):
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = unique_dest(dest_dir, filepath.name)

        try:
            shutil.copy2(filepath, dest_path)
            if dest_dir.name == "_unsorted":
                unsorted_count += 1
            else:
                organized += 1
        except Exception:
            errors += 1

        on_progress(50 + (i + 1) / n * 50)
        on_status(f"Copying {i + 1} of {n}: {filepath.name}")

    return organized, unsorted_count, errors


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
