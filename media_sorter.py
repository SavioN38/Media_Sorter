import os
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import ctypes
import json
import sys
import queue

# ================= RESOURCE PATH =================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # PyInstaller temp dir
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ================= DRAG & DROP =================
try:
    import tkinterdnd2 as dnd
    HAS_DND = True
except ImportError:
    HAS_DND = False
    dnd = None

# ================= CONFIG =================
CONFIG_FILE = "media_sorter_config.json"
APP_ICON = "MediaSorter.ico"

# ================= THEME =================
THEME_BG = "#0f1115"
CARD_BG  = "#161a22"
INPUT_BG = "#0b0e14"
BORDER   = "#2b3240"
TEXT     = "#ffffff"
SUBTEXT  = "#b6c0cc"
PRIMARY  = "#4f7cff"


# ================= PILL BUTTON =================
class PillButton(tk.Canvas):
    def __init__(self, parent, text, command, active=False):
        super().__init__(parent, width=110, height=32,
                         bg=THEME_BG, highlightthickness=0)
        self.command = command
        self.rect = self._rounded_rect(
            2, 2, 108, 30, 14,
            fill=PRIMARY if active else BORDER
        )
        self.create_text(55, 16, text=text,
                         fill="white",
                         font=("Segoe UI", 9, "bold"))
        self.bind("<Button-1>", lambda e: self.command())

    def _rounded_rect(self, x1, y1, x2, y2, r, **kw):
        return self.create_polygon(
            x1+r,y1, x2-r,y1, x2,y1, x2,y1+r,
            x2,y2-r, x2,y2, x2-r,y2,
            x1+r,y2, x1,y2, x1,y2-r,
            x1,y1+r, x1,y1,
            smooth=True, **kw
        )

    def set_active(self, active):
        self.itemconfig(self.rect, fill=PRIMARY if active else BORDER)


# ================= MAIN APP =================
class MediaSorter:
    def __init__(self, root):
        self.root = root

        # ---- FIX TASKBAR ID ----
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "MediaSorter.Pro"
            )
        except:
            pass

        # ---- SET ICON (WINDOWS CORRECT) ----
        try:
            self.root.iconbitmap(resource_path(APP_ICON))
        except:
            pass

        self.root.title("Media Sorter Pro")
        self.root.geometry("860x600")
        self.root.configure(bg=THEME_BG)

        self.files = []
        self.mode = "move"
        self.apply_all_action = None
        self.total_files = 0

        self.dest_var = tk.StringVar()

        # ---- THREAD COMMUNICATION ----
        self.ui_queue = queue.Queue()
        self.result_queue = queue.Queue()

        self.load_config()
        self.build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self.process_ui_queue)

    # ================= UI =================
    def build_ui(self):
        main = tk.Frame(self.root, bg=THEME_BG, padx=24, pady=20)
        main.pack(fill=tk.BOTH, expand=True)

        tk.Label(main, text="Media Sorter Pro",
                 fg=TEXT, bg=THEME_BG,
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")

        tk.Label(main, text="Drag and organize your files",
                 fg=SUBTEXT, bg=THEME_BG,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 16))

        toggle = tk.Frame(main, bg=THEME_BG)
        toggle.pack(pady=(0, 16))

        self.move_btn = PillButton(toggle, "MOVE", lambda: self.set_mode("move"), True)
        self.copy_btn = PillButton(toggle, "COPY", lambda: self.set_mode("copy"))
        self.move_btn.pack(side=tk.LEFT, padx=6)
        self.copy_btn.pack(side=tk.LEFT, padx=6)

        body = tk.Frame(main, bg=THEME_BG)
        body.pack(fill=tk.BOTH, expand=True)

        # LEFT
        left = tk.Frame(body, bg=CARD_BG, padx=16, pady=16)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 14))

        tk.Label(left, text="FILES", fg=TEXT, bg=CARD_BG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        self.listbox = tk.Listbox(
            left, bg=INPUT_BG, fg=TEXT,
            selectbackground=PRIMARY,
            relief="flat", font=("Segoe UI", 9)
        )
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=12)

        if HAS_DND:
            self.listbox.drop_target_register("DND_Files")
            self.listbox.dnd_bind("<<Drop>>", self.on_drop)

        # RIGHT
        right = tk.Frame(body, bg=CARD_BG, padx=16, pady=16)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        tk.Label(right, text="DESTINATION", fg=TEXT, bg=CARD_BG,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")

        tk.Entry(
            right, textvariable=self.dest_var,
            bg=INPUT_BG, fg=TEXT,
            insertbackground="white",
            relief="flat",
            highlightthickness=1,
            highlightbackground=BORDER,
            width=34
        ).pack(pady=10, ipady=4)

        tk.Button(
            right, text="BROWSE",
            command=self.browse_dest,
            bg=BORDER, fg="white",
            activebackground=PRIMARY,
            relief="flat", bd=0,
            padx=16, pady=6,
            font=("Segoe UI", 9, "bold")
        ).pack()

        # PROGRESS
        progress_wrap = tk.Frame(main, bg=CARD_BG, pady=8)
        progress_wrap.pack(fill="x", pady=(12, 8))

        self.progress_canvas = tk.Canvas(
            progress_wrap, width=400, height=8,
            bg=BORDER, highlightthickness=0
        )
        self.progress_canvas.pack(anchor="center")

        self.progress_bar = self.progress_canvas.create_rectangle(
            0, 0, 0, 8, fill=PRIMARY, width=0
        )

        self.action_btn = tk.Button(
            main, text="MOVE FILES",
            command=self.start_operation,
            bg=PRIMARY, fg="white",
            activebackground="#3c63d9",
            relief="flat", bd=0,
            padx=26, pady=10,
            font=("Segoe UI", 10, "bold")
        )
        self.action_btn.pack()

    # ================= CONFIG =================
    def load_config(self):
        try:
            with open(CONFIG_FILE, "r") as f:
                self.dest_var.set(json.load(f).get("last_dest", ""))
        except:
            pass

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"last_dest": self.dest_var.get()}, f)
        except:
            pass

    def on_close(self):
        self.save_config()
        self.root.destroy()

    # ================= UI QUEUE PROCESSOR =================
    def process_ui_queue(self):
        try:
            task, payload = self.ui_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self.process_ui_queue)
            return

        if task == "conflict":
            result = self.conflict_dialog(payload)
            self.result_queue.put(result)

        self.root.after(100, self.process_ui_queue)

    # ================= CONFLICT POPUP =================
    def conflict_dialog(self, filename):
        dlg = tk.Toplevel(self.root)
        dlg.configure(bg=THEME_BG)
        dlg.resizable(False, False)
        dlg.grab_set()

        choice = tk.StringVar(value="keep")
        apply_all = tk.BooleanVar()

        tk.Label(dlg, text="File already exists",
                 fg=TEXT, bg=THEME_BG,
                 font=("Segoe UI", 13, "bold")).pack(pady=10)

        tk.Label(dlg, text=filename,
                 fg=SUBTEXT, bg=THEME_BG,
                 wraplength=380,
                 font=("Segoe UI", 9)).pack()

        box = tk.Frame(dlg, bg=THEME_BG)
        box.pack(pady=10)

        for t, v in [
            ("Replace existing file", "replace"),
            ("Skip this file", "skip"),
            ("Keep both (rename)", "keep")
        ]:
            tk.Radiobutton(
                box, text=t, variable=choice, value=v,
                bg=THEME_BG, fg=TEXT,
                selectcolor=THEME_BG,
                font=("Segoe UI", 9)
            ).pack(anchor="w", pady=2)

        tk.Checkbutton(
            dlg, text="Apply to all",
            variable=apply_all,
            bg=THEME_BG, fg=TEXT,
            selectcolor=THEME_BG,
            font=("Segoe UI", 9)
        ).pack(pady=6)

        tk.Button(
            dlg, text="OK",
            command=dlg.destroy,
            bg=PRIMARY, fg="white",
            relief="flat", bd=0,
            padx=22, pady=6,
            font=("Segoe UI", 9, "bold")
        ).pack(pady=10)

        self.center_dialog(dlg, 420, 260)
        dlg.wait_window()
        return choice.get(), apply_all.get()

    def center_dialog(self, dlg, w, h):
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")

    # ================= LOGIC =================
    def set_mode(self, mode):
        self.mode = mode
        self.move_btn.set_active(mode == "move")
        self.copy_btn.set_active(mode == "copy")
        self.action_btn.config(
            text="MOVE FILES" if mode == "move" else "COPY FILES"
        )

    def on_drop(self, event):
        for p in self.root.tk.splitlist(event.data):
            if os.path.isfile(p):
                self.files.append(p)
                self.listbox.insert(tk.END, os.path.basename(p))

    def browse_dest(self):
        d = filedialog.askdirectory()
        if d:
            self.dest_var.set(d)
            self.save_config()

    def start_operation(self):
        if not self.files or not self.dest_var.get():
            messagebox.showwarning("Missing info", "Select files and destination")
            return
        self.apply_all_action = None
        self.total_files = len(self.files)
        self.progress_canvas.coords(self.progress_bar, 0, 0, 0, 8)
        threading.Thread(target=self.perform, daemon=True).start()

    def perform(self):
        dest = self.dest_var.get()
        os.makedirs(dest, exist_ok=True)

        for i, src in enumerate(self.files, 1):
            dst = os.path.join(dest, os.path.basename(src))

            if os.path.exists(dst):
                if self.apply_all_action:
                    action = self.apply_all_action
                    apply_all = True
                else:
                    self.ui_queue.put(("conflict", os.path.basename(dst)))
                    action, apply_all = self.result_queue.get()

                if apply_all:
                    self.apply_all_action = action

                if action == "skip":
                    self.update_progress(i)
                    continue
                elif action == "replace":
                    os.remove(dst)
                else:
                    base, ext = os.path.splitext(dst)
                    n = 1
                    while os.path.exists(dst):
                        dst = f"{base}_{n}{ext}"
                        n += 1

            shutil.move(src, dst) if self.mode == "move" else shutil.copy2(src, dst)
            self.update_progress(i)

        self.files.clear()
        self.listbox.delete(0, tk.END)
        self.progress_canvas.coords(self.progress_bar, 0, 0, 0, 8)
        messagebox.showinfo("Done", "Operation completed")

    def update_progress(self, i):
        w = int((i / self.total_files) * 400)
        self.progress_canvas.coords(self.progress_bar, 0, 0, w, 8)


if __name__ == "__main__":
    root = dnd.Tk() if HAS_DND else tk.Tk()
    MediaSorter(root)
    root.mainloop()

#pyinstaller 
#  --onefile 
#  --windowed 
#  --icon=MediaSorter.ico 
# --add-data "MediaSorter.ico;." 
#  media_sorter.py
