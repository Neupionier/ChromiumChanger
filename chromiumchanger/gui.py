"""ChromiumChanger desktop application (tkinter, no extra dependencies)."""
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from . import actions, ai, cleanup, extsources, updater, fetcher, launcher, localai, mods, policies, profiles, settings, transfer, validate
from . import __version__

BG, CARD, FG, MUT = "#14151c", "#1d1f2b", "#e6e8f2", "#9aa0b8"
ACC, LINE, FIELD = "#7c8cff", "#2c2f42", "#12131a"
OK, BAD, WARN = "#4cc38a", "#ff6b6b", "#f5b85c"

SEARCH_PRESETS = {
    "DuckDuckGo": ("DuckDuckGo", "ddg", "https://duckduckgo.com/?q={searchTerms}",
                   "https://duckduckgo.com/ac/?q={searchTerms}&type=list", "https://duckduckgo.com"),
    "Brave Search": ("Brave Search", "brave", "https://search.brave.com/search?q={searchTerms}",
                     "https://search.brave.com/api/suggest?q={searchTerms}", "https://search.brave.com"),
    "Startpage": ("Startpage", "sp", "https://www.startpage.com/do/search?q={searchTerms}", "", "https://www.startpage.com"),
    "Ecosia": ("Ecosia", "eco", "https://www.ecosia.org/search?q={searchTerms}",
               "https://ac.ecosia.org/autocomplete?q={searchTerms}&type=list", "https://www.ecosia.org"),
    "Bing": ("Bing", "bing", "https://www.bing.com/search?q={searchTerms}",
             "https://api.bing.com/osjson.aspx?query={searchTerms}", "https://www.bing.com"),
    "Qwant": ("Qwant", "qwant", "https://www.qwant.com/?q={searchTerms}", "", "https://www.qwant.com"),
    "Naver": ("Naver", "naver", "https://search.naver.com/search.naver?query={searchTerms}", "", "https://www.naver.com"),
}
OTHER = "Other (custom)"
HOME_PRESETS = {"Blank page (about:blank)": "about:blank",
                **{k: v[4] for k, v in SEARCH_PRESETS.items()}}

FIELDS = [
    ("Branding", [
        ("brand.name", "text", "Browser name"),
        ("brand.icon", "file", "Icon file (.ico, or .png when Pillow is installed)")]),
    ("Google", [
        ("google_removal", "bool", "Remove Google services (sync, Safe Browsing, translate, sign-in, telemetry...)")]),
    ("Search / Start", [
        ("-", "searchpreset", "Search engine"),
        ("search.name", "text", "Search engine name"),
        ("search.keyword", "text", "Keyword"),
        ("search.url", "text", "Search URL (must contain {searchTerms})"),
        ("search.suggest_url", "text", "Suggestion URL (empty = off)"),
        ("homepage", "homepage", "Home page (Home button and start-up page)")]),
    ("New tab page", [
        ("newtab.enabled", "bool", "Use the built-in new tab page (search box, clock, shortcuts)"),
        ("newtab.title", "text", "Greeting / title (optional)"),
        ("newtab.search", "bool", "Show the search box (uses your default search engine)"),
        ("newtab.clock", "bool", "Show the clock and date"),
        ("newtab.clock_24h", "bool", "24-hour clock"),
        ("newtab.shortcuts", "lines", "Shortcuts, one per line: Name | https://address (max 12)")]),
    ("Shortcuts for the browser", [
        ("shortcuts.desktop", "bool", "Desktop shortcut"),
        ("shortcuts.start_menu", "bool", "Start menu shortcut")]),
    ("Ad blocking", [
        ("adblock.enabled", "bool", "Enable ad blocking"),
        ("adblock.engine", "engine", "Ad blocker (downloaded on first launch)"),
        ("adblock.custom_path", "extpath", "Custom extension (unpacked folder or .zip; only for 'Custom')"),]),
    ("Privacy", [
        ("privacy.fingerprint", "bool", "Fingerprint protection (canvas / layout noise, ungoogled-chromium only)"),
        ("privacy.webrtc_protect", "bool", "Prevent WebRTC IP leaks (policy, needs administrator)"),
        ("privacy.block_third_party_cookies", "bool", "Block third-party cookies (policy, needs administrator)"),
        ("privacy.do_not_track", "bool", "Send Do Not Track (policy, needs administrator)")]),
    ("Appearance", [
        ("appearance.dark_mode", "bool", "Force dark mode"),
        ("appearance.theme_color", "color", "Theme color"),
        ("appearance.custom_css", "area", "Custom CSS applied to all sites")]),
    ("Site rules", [
        ("site_rules.block", "lines", "Block list (e.g. *.example.com) (policy, needs administrator)"),
        ("site_rules.allow", "lines", "Allow list (policy, needs administrator)")]),
    ("Advanced", [
        ("flags", "lines", "Extra launch flags (one per line; dangerous flags are rejected)")]),
]

DEV_OPTIONS = [
    ("auto_open_devtools", "Open DevTools automatically for every tab"),
    ("insecure_localhost", "Allow invalid HTTPS certificates on localhost"),
    ("enable_logging", "Write a browser log (chrome_debug.log in the profile folder)"),
    ("devtools_experiments", "Enable DevTools experiments"),
    ("disable_cache", "Minimize the HTTP cache (see changes immediately)"),
]
DEV_PAGES = [
    ("Inspect", "chrome://inspect"), ("Extensions", "chrome://extensions"),
    ("Policies", "chrome://policy"), ("Version / command line", "chrome://version"),
    ("Flags", "chrome://flags"), ("Net export", "chrome://net-export"),
    ("GPU", "chrome://gpu"), ("Components", "chrome://components"),
]

AI_LABELS = {
    "none": "None (AI off)",
    "ollama": "Local model (Ollama)",
    "openai": "API: OpenAI-compatible (OpenAI, Grok, LM Studio...)",
    "anthropic": "API: Anthropic",
}


def resource_path(rel):
    base = Path(getattr(sys, "_MEIPASS", settings.PROJECT))
    return base / rel


def get_in(d, dotted):
    for p in dotted.split("."):
        d = d[p]
    return d


def set_in(d, dotted, v):
    parts = dotted.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = v


def open_path(p):
    p = str(p)
    if sys.platform == "win32":
        os.startfile(p)  # noqa: S606 - user-initiated, local folder/file
    else:
        import subprocess
        subprocess.Popen(["xdg-open", p])


def relaunch_admin():
    import ctypes
    params = "" if settings.FROZEN else "-m chromiumchanger"
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, str(settings.PROJECT), 1)
    return r > 32


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", self._wheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")


class ModDialog(tk.Toplevel):
    """Create / edit a mod (CSS and/or JavaScript injected into pages)."""

    def __init__(self, parent, mod=None):
        super().__init__(parent)
        self.configure(bg=BG)
        self.title("Edit mod" if mod else "New mod")
        self.geometry("720x640")
        self.transient(parent)
        self.result = None
        self.mod = mod or {}
        f = ttk.Frame(self, padding=14)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        self.name = tk.StringVar(value=self.mod.get("name", ""))
        self.desc = tk.StringVar(value=self.mod.get("description", ""))
        self.matches = tk.StringVar(value=", ".join(self.mod.get("matches", ["<all_urls>"])))
        self.run_at = tk.StringVar(value=self.mod.get("run_at", "document_idle"))
        for r, (lbl, var) in enumerate((("Name", self.name), ("Description", self.desc),
                                        ("Runs on (comma separated match patterns)", self.matches))):
            ttk.Label(f, text=lbl).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 10))
            ttk.Entry(f, textvariable=var).grid(row=r, column=1, sticky="ew", pady=3)
        ttk.Label(f, text="Run at").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(f, textvariable=self.run_at, state="readonly",
                     values=["document_start", "document_end", "document_idle"]).grid(row=3, column=1, sticky="w")
        ttk.Label(f, text="CSS").grid(row=4, column=0, sticky="nw", pady=(8, 0))
        self.css = self._text(f, 5, self.mod.get("css", ""))
        ttk.Label(f, text="JavaScript").grid(row=6, column=0, sticky="nw", pady=(8, 0))
        self.js = self._text(f, 7, self.mod.get("js", ""))
        f.rowconfigure(5, weight=1)
        f.rowconfigure(7, weight=1)
        ttk.Label(f, foreground=MUT, wraplength=660,
                  text="Example match patterns: <all_urls>   https://*.example.com/*   "
                       "Mods run as content scripts inside pages.").grid(row=8, column=0, columnspan=2, sticky="w", pady=6)
        bf = ttk.Frame(f)
        bf.grid(row=9, column=0, columnspan=2, sticky="e")
        ttk.Button(bf, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(bf, text="Save", style="Accent.TButton", command=self.save).pack(side="right")
        self.grab_set()

    def _text(self, parent, row, value):
        t = tk.Text(parent, height=8, bg=FIELD, fg=FG, insertbackground=FG, relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC,
                    font=("Consolas", 10), undo=True)
        t.grid(row=row, column=0, columnspan=2, sticky="nsew")
        t.insert("1.0", value)
        return t

    def save(self):
        raw = {
            "name": self.name.get(), "description": self.desc.get(),
            "matches": [m.strip() for m in self.matches.get().split(",") if m.strip()],
            "css": self.css.get("1.0", "end-1c"), "js": self.js.get("1.0", "end-1c"),
            "run_at": self.run_at.get(),
        }
        try:
            clean, warnings = validate.sanitize_mod(raw)
        except ValueError as e:
            messagebox.showerror("Invalid mod", str(e), parent=self)
            return
        if warnings and not messagebox.askyesno(
                "Warnings", "This code has warnings:\n\n- " + "\n- ".join(warnings) + "\n\nSave anyway?", parent=self):
            return
        self.result = clean
        self.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"ChromiumChanger {__version__}")
        root.geometry("1040x780")
        root.minsize(900, 640)
        root.configure(bg=BG)
        try:
            root.iconbitmap(str(resource_path("assets/app.ico")))
        except Exception:
            pass
        root.report_callback_exception = self.on_exception
        self.q = queue.Queue()
        self.busy = False
        self.plan = None
        self.fields = {}
        self.entries = {}
        self.dev_vars = {}
        self.setup_style()
        self.build_top()
        self.build_log()
        self.nb = ttk.Notebook(root)
        self.nb.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 6))
        for title, builder in (("Home", self.tab_home), ("Settings", self.tab_settings), ("AI", self.tab_ai),
                               ("Mods", self.tab_mods), ("Profiles", self.tab_profiles),
                               ("Developer", self.tab_dev), ("History", self.tab_history)):
            frame = ttk.Frame(self.nb, padding=12)
            self.nb.add(frame, text=f"  {title}  ")
            if title == "AI":   # long tab: scrollable so the buttons below the prompt are never cut off
                sf = ScrollFrame(frame)
                sf.pack(fill="both", expand=True)
                builder(sf.inner)
            else:
                builder(frame)
        self.reload_all()
        root.after(120, self.poll)

    # ---------- infrastructure ----------
    def setup_style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, fieldbackground=FIELD, bordercolor=LINE,
                     lightcolor=BG, darkcolor=BG, troughcolor=BG, font=("Segoe UI", 10))
        st.configure("TFrame", background=BG)
        st.configure("Card.TFrame", background=CARD)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Card.TLabel", background=CARD, foreground=FG)
        st.configure("Muted.TLabel", foreground=MUT)
        st.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        st.configure("H.TLabel", font=("Segoe UI", 11, "bold"))
        st.configure("TButton", background="#2a2d42", foreground=FG, padding=(12, 6), borderwidth=0)
        st.map("TButton", background=[("active", "#383c58"), ("disabled", "#20222f")],
               foreground=[("disabled", MUT)])
        st.configure("Accent.TButton", background=ACC, foreground="#0b0c14", font=("Segoe UI", 10, "bold"))
        st.map("Accent.TButton", background=[("active", "#95a1ff"), ("disabled", "#4a5188")])
        st.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG, padding=5)
        st.configure("TCombobox", fieldbackground=FIELD, foreground=FG, arrowcolor=FG, padding=4)
        st.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)])
        st.configure("TCheckbutton", background=BG, foreground=FG, indicatorbackground=FIELD,
                     indicatorforeground=ACC)
        st.map("TCheckbutton", background=[("active", BG)], indicatorbackground=[("selected", ACC)])
        st.configure("TNotebook", background=BG, borderwidth=0)
        st.configure("TNotebook.Tab", background=CARD, foreground=MUT, padding=(10, 6), borderwidth=0)
        st.map("TNotebook.Tab", background=[("selected", "#2a2d42")], foreground=[("selected", FG)])
        st.configure("Treeview", background=FIELD, fieldbackground=FIELD, foreground=FG, rowheight=26,
                     borderwidth=0)
        st.configure("Treeview.Heading", background=CARD, foreground=MUT, relief="flat")
        st.map("Treeview", background=[("selected", "#3b4072")])
        st.configure("Vertical.TScrollbar", background="#2a2d42", arrowcolor=FG)
        self.root.option_add("*TCombobox*Listbox.background", FIELD)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#3b4072")

    def on_exception(self, exc, val, tb):
        if getattr(self, "closing", False):  # window is being closed after clean-up
            return
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            settings.WORK.mkdir(parents=True, exist_ok=True)
            (settings.WORK / "crash.log").write_text(text, encoding="utf-8")
        except Exception:
            pass
        messagebox.showerror("Unexpected error", f"{val}\n\n(details saved to workspace/crash.log)")

    def build_top(self):
        top = ttk.Frame(self.root, padding=(16, 12, 16, 8))
        top.pack(fill="x")
        ttk.Label(top, text="ChromiumChanger", style="Title.TLabel").pack(side="left")
        right = ttk.Frame(top)
        right.pack(side="right")
        self.admin_lbl = ttk.Label(right, style="Muted.TLabel")
        self.admin_lbl.pack(side="left", padx=8)
        self.admin_btn = ttk.Button(right, text="Restart as administrator", command=self.do_admin)
        self.admin_btn.pack(side="left", padx=(0, 14))
        ttk.Label(right, text="Profile:").pack(side="left")
        self.prof_var = tk.StringVar()
        self.prof_box = ttk.Combobox(right, textvariable=self.prof_var, state="readonly", width=18)
        self.prof_box.pack(side="left", padx=6)
        self.prof_box.bind("<<ComboboxSelected>>", lambda e: self.switch_profile(self.prof_var.get()))
        ttk.Button(right, text="Launch", style="Accent.TButton", command=self.do_launch).pack(side="left", padx=(10, 0))

    def build_log(self):
        box = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        box.pack(side="bottom", fill="x")
        row = ttk.Frame(box)
        row.pack(fill="x")
        ttk.Label(row, text="Activity", style="Muted.TLabel").pack(side="left")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(row, textvariable=self.status, foreground=ACC).pack(side="right")
        self.log = tk.Text(box, height=8, bg="#0d0e14", fg="#cfd3e6", relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC, state="disabled",
                           font=("Consolas", 9), wrap="word")
        self.log.pack(fill="x", pady=(4, 0))
        self.log.tag_configure("err", foreground=BAD)
        self.log.tag_configure("ok", foreground=OK)

    def log_write(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log_write(payload, "err" if payload.startswith(("ERROR", "WARNING")) else None)
                else:
                    self.busy = False
                    self.status.set("Ready")
                    done, res, err = payload
                    if err is None:
                        self.log_write("Done.", "ok")
                    if done:
                        done(res, err)
                    self.refresh_home()
        except queue.Empty:
            pass
        self.root.after(120, self.poll)

    def run_job(self, title, fn, done=None):
        if self.busy:
            messagebox.showinfo("Busy", "Another task is still running.")
            return
        self.busy = True
        self.status.set(title + "...")
        self.log_write(f"== {title} ==")

        def work():
            res = err = None
            try:
                res = fn(lambda m: self.q.put(("log", str(m))))
            except Exception as e:  # shown in the activity log
                err = e
                self.q.put(("log", f"ERROR: {e}"))
            self.q.put(("done", (done, res, err)))
        threading.Thread(target=work, daemon=True).start()

    # ---------- top bar actions ----------
    def do_admin(self):
        if messagebox.askyesno("Administrator", "Restart ChromiumChanger with administrator rights?\n\n"
                               "Needed for policy-based settings (default search engine, homepage, site rules...)."):
            if relaunch_admin():
                self.root.destroy()
            else:
                messagebox.showwarning("Administrator", "The restart was cancelled or failed.")

    def do_launch(self, url=None):
        self.run_job("Launch", lambda log: launcher.launch(log=log, url=url))

    def do_apply(self):
        self.run_job("Apply settings", lambda log: launcher.build_all(log=log))

    def switch_profile(self, name):
        if name and name != settings.active():
            profiles.switch(name)
            self.log_write(f"Switched to profile '{name}'.")
            self.reload_all()

    # ---------- Home ----------
    def tab_home(self, f):
        ttk.Label(f, text="Get started", style="H.TLabel").pack(anchor="w")
        self.home_status = ttk.Label(f, text="")
        self.home_status.pack(anchor="w", pady=(6, 10))
        row = ttk.Frame(f)
        row.pack(anchor="w")
        self.install_btn = ttk.Button(row, text="1. Install ungoogled-chromium", command=self.do_install)
        self.install_btn.pack(side="left", padx=(0, 8))
        ttk.Button(row, text="2. Apply settings", command=self.do_apply).pack(side="left", padx=(0, 8))
        ttk.Button(row, text="3. Launch", style="Accent.TButton", command=self.do_launch).pack(side="left")
        ttk.Button(row, text="Remove customized browser...", command=self.do_remove_browser).pack(side="left", padx=(24, 0))
        ttk.Button(row, text="Check for updates", command=self.do_update).pack(side="left", padx=(8, 0))
        self.home_summary = ttk.Label(f, text="", style="Muted.TLabel", justify="left", wraplength=900)
        self.home_summary.pack(anchor="w", pady=16)
        ttk.Label(f, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "Tips\n"
            "- Always start the browser from here, from the 'Launch <name>.bat' file or from the desktop shortcut. "
            "Opening the browser .exe directly skips the extensions and flags.\n"
            "- Policy-based settings (default search engine, homepage, site rules, WebRTC/cookie/DNT) need "
            "administrator rights. Use 'Restart as administrator' at the top.\n"
            "- Policies are machine-wide: if two profiles use different policy values, the profile you "
            "launched last wins.")).pack(anchor="w")

    def do_update(self):
        self.run_job("Check for updates", lambda log: updater.check(log), self.on_update_checked)

    def on_update_checked(self, info, err):
        if err is not None:
            messagebox.showinfo("Updates", str(err))
            return
        if not info["newer"]:
            messagebox.showinfo("Updates", f"You are up to date (version {__version__}).")
            return
        if not updater.can_self_update():
            messagebox.showinfo("Updates", f"Version {info['tag']} is available.\n\nDownload it from "
                                f"https://github.com/{info['repo']}/releases/latest")
            return
        if messagebox.askyesno("Update available", f"Version {info['tag']} is available (you have {__version__}).\n\n"
                               f"{info['notes']}\n\nDownload and install now? The app restarts."):
            self.run_job("Download update", lambda log: updater.download(info, log), self.on_update_downloaded)

    def on_update_downloaded(self, folder, err):
        if err is not None or not folder:
            return
        self.closing = True
        messagebox.showinfo("Updates", "The update is ready. Click OK: the app closes and restarts with the new version.")
        localai.stop()
        updater.schedule_install(folder, lambda m: None)  # only after OK, so the old exe really exits
        try:
            self.root.destroy()
        finally:
            os._exit(0)  # make sure no leftover thread keeps the exe alive (the updater waits for it)

    def do_remove_browser(self):
        if self.busy:
            messagebox.showinfo("Busy", "Another task is still running.")
            return
        if not messagebox.askyesno("Remove customized browser",
                                   "This permanently removes:\n\n- " + "\n- ".join(cleanup.describe()) +
                                   "\n\nChromiumChanger itself and your settings, mods and AI settings are kept.\n"
                                   "Close the browser first.\n\nContinue?", icon="warning"):
            return
        self.run_job("Remove browser", lambda log: cleanup.run(log))

    def do_install(self):
        self.run_job("Install browser", lambda log: fetcher.install(log))

    def refresh_home(self):
        if not hasattr(self, "home_status") or getattr(self, "closing", False):
            return
        exe = fetcher.find_exe()
        v = fetcher.installed_version()
        if exe:
            self.home_status.configure(text=f"Browser installed: {v['tag'] if v else 'unknown version'}", foreground=OK)
            self.install_btn.configure(text="1. Reinstall / update browser")
        else:
            self.home_status.configure(text="Browser not installed yet.", foreground=WARN)
            self.install_btn.configure(text="1. Install ungoogled-chromium")
        s = settings.load()
        self.home_summary.configure(text=(
            f"Profile '{settings.active()}'  |  brand: {s['brand']['name']}  |  search: {s['search']['name']}  |  "
            f"ad blocking: {'on' if s['adblock']['enabled'] else 'off'}  |  "
            f"Google removal: {'on' if s['google_removal'] else 'off'}  |  mods: {len(mods.list_mods())}"))
        adm = policies.is_admin() if sys.platform == "win32" else False
        self.admin_lbl.configure(text="Administrator: yes" if adm else "Administrator: no",
                                 foreground=OK if adm else MUT)
        if adm or sys.platform != "win32":
            self.admin_btn.pack_forget()

    # ---------- Settings ----------
    def tab_settings(self, f):
        sf = ScrollFrame(f)
        sf.pack(fill="both", expand=True)
        inner = sf.inner
        inner.columnconfigure(1, weight=1)
        row = 0
        for title, fields in FIELDS:
            ttk.Label(inner, text=title, style="H.TLabel").grid(row=row, column=0, columnspan=2, sticky="w", pady=(14, 4))
            row += 1
            for path, kind, label in fields:
                if kind in ("searchpreset", "homepage"):
                    ttk.Label(inner, text=label, style="Muted.TLabel", wraplength=300).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=3)
                    names = (list(SEARCH_PRESETS) if kind == "searchpreset" else list(HOME_PRESETS)) + [OTHER]
                    cb = ttk.Combobox(inner, state="readonly", width=40, values=names)
                    cb.grid(row=row, column=1, sticky="w", pady=3)
                    cb.bind("<<ComboboxSelected>>", self.on_preset)
                    if kind == "searchpreset":
                        self.search_cb = cb
                    else:
                        self.home_cb = cb
                    row += 1
                    if kind == "searchpreset":
                        continue
                    label = "Home page URL"
                if kind == "bool":
                    var = tk.BooleanVar()
                    ttk.Checkbutton(inner, text=label, variable=var).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
                    self.fields[path] = (kind, var)
                else:
                    ttk.Label(inner, text=label, style="Muted.TLabel", wraplength=300).grid(row=row, column=0, sticky="nw", padx=(0, 12), pady=3)
                    if kind == "engine":
                        cell = ttk.Frame(inner)
                        cell.grid(row=row, column=1, sticky="ew", pady=3)
                        cb = ttk.Combobox(cell, state="readonly", width=46, values=[extsources.LABELS[k] for k in extsources.ENGINES])
                        cb.grid(row=0, column=0, sticky="w")
                        ttk.Button(cell, text="Download / update now", command=self.download_blocker).grid(row=0, column=1, padx=(6, 0))
                        self.fields[path] = (kind, cb)
                    elif kind in ("lines", "area"):
                        t = tk.Text(inner, height=4 if kind == "lines" else 6, bg=FIELD, fg=FG, insertbackground=FG,
                                    relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC, font=("Consolas", 10), undo=True)
                        t.grid(row=row, column=1, sticky="ew", pady=3)
                        self.fields[path] = (kind, t)
                    else:
                        var = tk.StringVar()
                        cell = ttk.Frame(inner)
                        cell.grid(row=row, column=1, sticky="ew", pady=3)
                        cell.columnconfigure(0, weight=1)
                        ent = ttk.Entry(cell, textvariable=var)
                        ent.grid(row=0, column=0, sticky="ew")
                        self.entries[path] = ent
                        if kind == "color":
                            ttk.Button(cell, text="Pick...", command=lambda v=var: self.pick_color(v)).grid(row=0, column=1, padx=(6, 0))
                        if kind == "file":
                            ttk.Button(cell, text="Browse...", command=lambda v=var: self.pick_file(v)).grid(row=0, column=1, padx=(6, 0))
                        if kind == "extpath":
                            ttk.Button(cell, text="Folder...", command=lambda v=var: self.pick_ext(v, True)).grid(row=0, column=1, padx=(6, 0))
                            ttk.Button(cell, text=".zip...", command=lambda v=var: self.pick_ext(v, False)).grid(row=0, column=2, padx=(6, 0))
                        self.fields[path] = (kind, var)
                row += 1
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Save", command=lambda: self.save_form(False)).pack(side="left")
        ttk.Button(bar, text="Save and apply", style="Accent.TButton",
                   command=lambda: self.save_form(True)).pack(side="left", padx=8)
        ttk.Button(bar, text="Reset form", command=self.load_form).pack(side="left")

    def pick_color(self, var):
        c = colorchooser.askcolor(color=var.get() or "#1e1e2e", title="Theme color")[1]
        if c:
            var.set(c)

    def pick_file(self, var):
        p = filedialog.askopenfilename(filetypes=[("Images", "*.ico *.png *.jpg *.jpeg"), ("All files", "*.*")])
        if p:
            var.set(p)

    def pick_ext(self, var, folder):
        p = filedialog.askdirectory() if folder else filedialog.askopenfilename(filetypes=[("Extension zip", "*.zip")])
        if p and messagebox.askyesno("Custom extension",
                                     "Extensions can read and change every page you visit. Only use extensions you trust.\n\nUse this one?"):
            var.set(p)

    def download_blocker(self):
        label = self.fields["adblock.engine"][1].get()
        key = next((k for k in extsources.ENGINES if extsources.LABELS[k] == label), None)
        if key not in extsources.SOURCES:
            messagebox.showinfo("Download", "Pick uBlock Origin Lite, AdGuard or uBlock Origin first (Custom needs no download).")
            return
        self.run_job(f"Download {label}", lambda log: extsources.install(key, log))

    def on_preset(self, _e=None):
        sp = self.search_cb.get()
        if sp in SEARCH_PRESETS:
            name, kw, url, sug, _home = SEARCH_PRESETS[sp]
            for k, v in (("search.name", name), ("search.keyword", kw), ("search.url", url), ("search.suggest_url", sug)):
                self.fields[k][1].set(v)
        hp = self.home_cb.get()
        if hp in HOME_PRESETS:
            self.fields["homepage"][1].set(HOME_PRESETS[hp])
        self.update_preset_state()

    def update_preset_state(self):
        custom = self.search_cb.get() == OTHER
        for k in ("search.name", "search.keyword", "search.url", "search.suggest_url"):
            self.entries[k].configure(state="normal" if custom else "disabled")
        self.entries["homepage"].configure(state="normal" if self.home_cb.get() == OTHER else "disabled")

    def sync_presets(self):
        s = {k: self.fields[k][1].get() for k in ("search.url", "homepage")}
        self.search_cb.set(next((n for n, p in SEARCH_PRESETS.items() if p[2] == s["search.url"]), OTHER))
        self.home_cb.set(next((n for n, u in HOME_PRESETS.items() if u == s["homepage"]), OTHER))
        self.update_preset_state()

    def load_form(self):
        s = settings.load()
        for path, (kind, w) in self.fields.items():
            v = get_in(s, path)
            if kind == "bool":
                w.set(bool(v))
            elif kind == "engine":
                w.set(extsources.LABELS.get(v, extsources.LABELS["ublock_lite"]))
            elif kind in ("lines", "area"):
                w.delete("1.0", "end")
                w.insert("1.0", "\n".join(v) if kind == "lines" else v)
            else:
                w.set(v or "")
        self.sync_presets()

    def collect_form(self):
        out = {}
        for path, (kind, w) in self.fields.items():
            if kind == "bool":
                v = w.get()
            elif kind == "engine":
                v = next((k for k in extsources.ENGINES if extsources.LABELS[k] == w.get()), "ublock_lite")
            elif kind == "lines":
                v = [x.strip() for x in w.get("1.0", "end-1c").splitlines() if x.strip()]
            elif kind == "area":
                v = w.get("1.0", "end-1c")
            else:
                v = w.get().strip()
            set_in(out, path, v)
        return out

    def save_form(self, apply_after):
        try:
            actions.save_settings(self.collect_form())
        except ValueError as e:
            messagebox.showerror("Cannot save", str(e))
            return
        self.log_write("Settings saved.", "ok")
        self.refresh_home()
        if apply_after:
            self.do_apply()
        else:
            self.log_write("Press 'Apply settings' on the Home tab (or Launch) to use them.")

    # ---------- AI ----------
    def tab_ai(self, f):
        lc = ttk.Frame(f, style="Card.TFrame", padding=12)
        lc.pack(fill="x", pady=(0, 10))
        ttk.Label(lc, text="Local AI (runs on this PC, free)", style="H.TLabel", background=CARD).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(lc, style="Card.TLabel", foreground=MUT, wraplength=900, text=(
            "One click: downloads Ollama (about 1.5 GB) into the app's data folder, starts it and downloads the model "
            "you choose. No installer and no administrator rights are needed. Download sizes are large, so use a fast connection.")
                  ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
        self.local_model = ttk.Combobox(lc, state="readonly", width=60,
                                        values=[f"{m} - {d}" for m, d in localai.MODELS])
        self.local_model.current(1)
        self.local_model.grid(row=2, column=0, sticky="w")
        ttk.Button(lc, text="Install local AI and use it", style="Accent.TButton",
                   command=self.install_local_ai).grid(row=2, column=1, padx=8)
        self.local_status = tk.StringVar(value="")
        ttk.Label(lc, textvariable=self.local_status, style="Card.TLabel", foreground=MUT).grid(row=3, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.refresh_local_status()
        card = ttk.Frame(f, style="Card.TFrame", padding=12)
        card.pack(fill="x")
        card.columnconfigure(1, weight=1)
        ttk.Label(card, text="AI connection (optional, off by default)", style="H.TLabel", background=CARD).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(card, style="Card.TLabel", foreground=MUT, wraplength=900, text=(
            "Choose a local model (Ollama running on this PC) or an API. Nothing is sent anywhere while the provider is "
            "'None'. The API key is stored in app.json in the workspace; alternatively set the CC_API_KEY "
            "environment variable and leave the key empty.")).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
        self.ai_vars = {k: tk.StringVar() for k in ("provider", "model", "base_url", "api_key")}
        ttk.Label(card, text="Provider", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=3)
        self.ai_prov = ttk.Combobox(card, state="readonly", values=list(AI_LABELS.values()), width=48)
        self.ai_prov.grid(row=2, column=1, sticky="w")
        self.ai_prov.bind("<<ComboboxSelected>>", self.on_ai_provider)
        for r, (k, lbl, show) in enumerate((("model", "Model name", ""), ("base_url", "Base URL", ""),
                                            ("api_key", "API key", "*")), start=3):
            ttk.Label(card, text=lbl, style="Card.TLabel").grid(row=r, column=0, sticky="w", pady=3)
            self.ai_entries = getattr(self, "ai_entries", {})
            e = ttk.Entry(card, textvariable=self.ai_vars[k], show=show)
            e.grid(row=r, column=1, sticky="ew", pady=3)
            self.ai_entries[k] = e
        bf = ttk.Frame(card, style="Card.TFrame")
        bf.grid(row=6, column=1, sticky="w", pady=(8, 0))
        ttk.Button(bf, text="Save AI settings", command=self.save_ai).pack(side="left")
        ttk.Button(bf, text="Test connection", command=self.test_ai).pack(side="left", padx=8)

        ttk.Label(f, text="Describe the customization you want", style="H.TLabel").pack(anchor="w", pady=(14, 4))
        self.ai_prompt = tk.Text(f, height=4, bg=FIELD, fg=FG, insertbackground=FG, relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC, font=("Segoe UI", 10))
        self.ai_prompt.pack(fill="x")
        row = ttk.Frame(f)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Create plan", style="Accent.TButton", command=self.make_plan).pack(side="left")
        ttk.Label(row, style="Muted.TLabel", text="  e.g. 'Hide the Shorts button on YouTube', 'make Wikipedia dark', 'use Brave search'").pack(side="left")
        self.plan_text = tk.Text(f, height=10, bg="#0d0e14", fg="#cfd3e6", relief="flat", borderwidth=0, highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC, font=("Consolas", 9), state="disabled")
        self.plan_text.pack(fill="both", expand=True)
        self.plan_text.tag_configure("warn", foreground=WARN)
        self.plan_text.tag_configure("bad", foreground=BAD)
        self.plan_text.tag_configure("h", foreground=ACC)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(6, 0))
        self.plan_apply = ttk.Button(bar, text="Approve", style="Accent.TButton", command=self.approve_plan, state="disabled")
        self.plan_apply.pack(side="left")
        ttk.Button(bar, text="Discard", command=self.discard_plan).pack(side="left", padx=8)

    def refresh_local_status(self):
        self.local_status.set("Local AI engine: " + localai.status())

    def install_local_ai(self):
        model = localai.MODELS[self.local_model.current()][0]
        if not messagebox.askyesno("Install local AI",
                                   f"This downloads Ollama (about 1.5 GB) and the model {model}.\n\nContinue?"):
            return

        def done(res, err):
            self.load_ai()
            self.refresh_local_status()
            if err is None:
                messagebox.showinfo("Local AI", "Local AI is ready. You can use the plan box below.")
        self.run_job("Install local AI", lambda log: localai.setup(model, log), done)

    def ai_provider_key(self):
        sel = self.ai_prov.get()
        return next((k for k, v in AI_LABELS.items() if v == sel), "none")

    def on_ai_provider(self, _e=None):
        prov = self.ai_provider_key()
        d = ai.PROVIDER_DEFAULTS.get(prov, {})
        if not self.ai_vars["base_url"].get() or self.ai_vars["base_url"].get() in [x["base_url"] for x in ai.PROVIDER_DEFAULTS.values()]:
            self.ai_vars["base_url"].set(d.get("base_url", ""))
        self.set_ai_enabled(prov != "none")

    def set_ai_enabled(self, on):
        for e in self.ai_entries.values():
            e.configure(state="normal" if on else "disabled")

    def load_ai(self):
        cfg = settings.load_ai()
        self.ai_prov.set(AI_LABELS.get(cfg["provider"], AI_LABELS["none"]))
        for k in ("model", "base_url", "api_key"):
            self.ai_vars[k].set(cfg.get(k, ""))
        self.set_ai_enabled(cfg["provider"] != "none")

    def ai_cfg(self):
        return {"provider": self.ai_provider_key(), **{k: v.get().strip() for k, v in self.ai_vars.items() if k != "provider"}}

    def save_ai(self):
        settings.save_ai(self.ai_cfg())
        self.log_write("AI settings saved.", "ok")

    def test_ai(self):
        cfg = self.ai_cfg()
        self.run_job("Test AI connection", lambda log: log("Reply: " + ai.test(cfg)))

    def set_plan_text(self, parts):
        t = self.plan_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for text, tag in parts:
            t.insert("end", text, tag)
        t.configure(state="disabled")

    def make_plan(self):
        req = self.ai_prompt.get("1.0", "end-1c").strip()
        if not req:
            return
        self.discard_plan()
        s = settings.load()

        def done(plan, err):
            if err:
                self.set_plan_text([(f"{type(err).__name__}: {err}\n", "bad")])
                return
            self.plan = plan
            self.show_plan(plan)
        self.run_job("Create plan", lambda log: ai.plan(s, req), done)

    def show_plan(self, p):
        parts = [(p["summary"] or "(no description)", None), ("\n\n", None)]
        if p["settings_patch"]:
            parts.append(("Setting changes\n", "h"))
            parts += [(f"  {k} = {v!r}\n", None) for k, v in p["settings_patch"].items()]
        if p["flags"]:
            parts.append(("Launch flags\n", "h"))
            parts += [(f"  {x}\n", None) for x in p["flags"]]
        for m in p["mods"]:
            parts.append((f"\nMod: {m['name']}  ({', '.join(m['matches'])})\n", "h"))
            if m["css"]:
                parts.append(("/* CSS */\n" + m["css"] + "\n", None))
            if m["js"]:
                parts.append(("// JS\n" + m["js"] + "\n", None))
            for w in m.get("warnings", []):
                parts.append((f"  WARNING: {w}\n", "warn"))
        if p["recommended_extensions"]:
            parts.append(("\nRecommended extensions (install them yourself)\n", "h"))
            parts += [(f"  - {r['name']}: {r['reason']}\n", None) for r in p["recommended_extensions"]]
        if p["issues"]:
            parts.append(("\nRejected / ignored\n", "bad"))
            parts += [(f"  - {i}\n", "bad") for i in p["issues"]]
        self.set_plan_text(parts)
        if p["settings_patch"] or p["flags"] or p["mods"]:
            self.plan_apply.configure(state="normal")

    def approve_plan(self):
        p = self.plan
        if not p:
            return
        if p["warnings"] and not messagebox.askyesno(
                "Warnings", "This plan contains code with warnings:\n\n- " + "\n- ".join(p["warnings"][:8]) +
                "\n\nHave you reviewed the code and still want to apply it?"):
            return
        actions.apply_plan(p)
        self.discard_plan()
        self.reload_all()
        self.log_write("Plan approved and saved. Press 'Apply settings' on the Home tab to use it.", "ok")

    def discard_plan(self):
        self.plan = None
        self.plan_apply.configure(state="disabled")
        self.set_plan_text([])

    # ---------- Mods ----------
    def tab_mods(self, f):
        self.mod_tree = ttk.Treeview(f, columns=("on", "name", "where"), show="headings", selectmode="browse")
        for c, w, t in (("on", 60, "On"), ("name", 260, "Name"), ("where", 500, "Runs on")):
            self.mod_tree.heading(c, text=t)
            self.mod_tree.column(c, width=w, anchor="w")
        self.mod_tree.pack(fill="both", expand=True)
        self.mod_tree.bind("<Double-1>", lambda e: self.edit_mod())
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 0))
        for text, cmd in (("Add mod", self.add_mod), ("Edit", self.edit_mod), ("Enable / disable", self.toggle_mod),
                          ("Delete", self.delete_mod)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Label(bar, style="Muted.TLabel", text="  Changes take effect after Apply / Launch.").pack(side="left")

    def refresh_mods(self):
        self.mod_tree.delete(*self.mod_tree.get_children())
        for m in mods.list_mods():
            self.mod_tree.insert("", "end", iid=m["id"], values=("yes" if m.get("enabled", True) else "no", m["name"], ", ".join(m["matches"])))

    def sel_mod(self):
        sel = self.mod_tree.selection()
        if not sel:
            messagebox.showinfo("Mods", "Select a mod first.")
            return None
        return next((m for m in mods.list_mods() if m["id"] == sel[0]), None)

    def add_mod(self):
        d = ModDialog(self.root)
        self.root.wait_window(d)
        if d.result:
            mods.snapshot("Before adding mod")
            mods.save_mod(d.result)
            self.refresh_mods()

    def edit_mod(self):
        m = self.sel_mod()
        if not m:
            return
        d = ModDialog(self.root, m)
        self.root.wait_window(d)
        if d.result:
            mods.snapshot("Before editing mod")
            mods.save_mod({**d.result, "id": m["id"], "enabled": m.get("enabled", True)})
            self.refresh_mods()

    def toggle_mod(self):
        m = self.sel_mod()
        if m:
            mods.toggle_mod(m["id"], not m.get("enabled", True))
            self.refresh_mods()

    def delete_mod(self):
        m = self.sel_mod()
        if m and messagebox.askyesno("Delete", f"Delete mod '{m['name']}'?"):
            mods.snapshot("Before mod deletion")
            mods.delete_mod(m["id"])
            self.refresh_mods()

    # ---------- Profiles ----------
    def tab_profiles(self, f):
        ttk.Label(f, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "Each profile has its own settings, mods, history and browser data (bookmarks, cookies, logins). "
            "Export saves settings and mods only, never browsing data or API keys.")).pack(anchor="w", pady=(0, 8))
        self.prof_tree = ttk.Treeview(f, columns=("name", "active"), show="headings", selectmode="browse", height=8)
        self.prof_tree.heading("name", text="Profile")
        self.prof_tree.heading("active", text="")
        self.prof_tree.column("name", width=400)
        self.prof_tree.column("active", width=120)
        self.prof_tree.pack(fill="both", expand=True)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 0))
        for text, cmd in (("Switch to", self.p_switch), ("New", self.p_new), ("Duplicate", self.p_dup),
                          ("Rename", self.p_rename), ("Delete", self.p_delete)):
            ttk.Button(bar, text=text, command=cmd).pack(side="left", padx=(0, 6))
        bar2 = ttk.Frame(f)
        bar2.pack(fill="x", pady=(8, 0))
        ttk.Button(bar2, text="Export current profile...", command=self.p_export).pack(side="left", padx=(0, 6))
        ttk.Button(bar2, text="Import profile...", command=self.p_import).pack(side="left")

    def refresh_profiles(self):
        names = profiles.list_profiles()
        self.prof_box.configure(values=names)
        self.prof_var.set(settings.active())
        self.prof_tree.delete(*self.prof_tree.get_children())
        for n in names:
            self.prof_tree.insert("", "end", iid=n, values=(n, "(active)" if n == settings.active() else ""))

    def sel_profile(self):
        sel = self.prof_tree.selection()
        if not sel:
            messagebox.showinfo("Profiles", "Select a profile first.")
            return None
        return sel[0]

    def guarded(self, fn):
        try:
            fn()
        except (ValueError, OSError) as e:
            messagebox.showerror("Profiles", str(e))

    def p_switch(self):
        n = self.sel_profile()
        if n:
            self.guarded(lambda: self.switch_profile(n))

    def p_new(self):
        name = simpledialog.askstring("New profile", "Profile name:", parent=self.root)
        if name:
            copy = messagebox.askyesno("New profile", "Copy settings and mods from the current profile?")
            self.guarded(lambda: profiles.create(name.strip(), settings.active() if copy else None))
            self.refresh_profiles()

    def p_dup(self):
        n = self.sel_profile()
        if n:
            name = simpledialog.askstring("Duplicate", f"Name for the copy of '{n}':", parent=self.root)
            if name:
                self.guarded(lambda: profiles.create(name.strip(), n))
                self.refresh_profiles()

    def p_rename(self):
        n = self.sel_profile()
        if n:
            name = simpledialog.askstring("Rename", f"New name for '{n}':", parent=self.root)
            if name:
                self.guarded(lambda: profiles.rename(n, name.strip()))
                self.refresh_profiles()

    def p_delete(self):
        n = self.sel_profile()
        if n and messagebox.askyesno("Delete profile", f"Delete profile '{n}' including its bookmarks, "
                                     "cookies and all browser data? This cannot be undone."):
            self.guarded(lambda: profiles.delete(n))
            self.refresh_profiles()

    def p_export(self):
        p = filedialog.asksaveasfilename(defaultextension=".ccprofile", initialfile=f"{settings.active()}.ccprofile",
                                         filetypes=[("ChromiumChanger profile", "*.ccprofile")])
        if p:
            self.guarded(lambda: self.log_write(f"Exported {transfer.export_profile(p)} mods and settings to {p}", "ok"))

    def p_import(self):
        p = filedialog.askopenfilename(filetypes=[("ChromiumChanger profile", "*.ccprofile"), ("All files", "*.*")])
        if not p:
            return
        try:
            r = transfer.import_profile(p)
        except (ValueError, OSError) as e:
            messagebox.showerror("Import failed", str(e))
            return
        self.refresh_profiles()
        msg = f"Imported as new profile '{r['profile']}'."
        if r["held_js_mods"]:
            msg += f"\n\n{r['held_js_mods']} mod(s) containing JavaScript were imported DISABLED. Review them on the Mods tab before enabling."
        if r["warnings"]:
            msg += "\n\nWarnings:\n- " + "\n- ".join(r["warnings"][:8])
        if r["issues"]:
            msg += "\n\nIgnored:\n- " + "\n- ".join(r["issues"][:8])
        messagebox.showinfo("Import finished", msg)
        if messagebox.askyesno("Switch", f"Switch to '{r['profile']}' now?"):
            self.switch_profile(r["profile"])

    # ---------- Developer ----------
    def tab_dev(self, f):
        ttk.Label(f, text="Developer options (saved per profile)", style="H.TLabel").pack(anchor="w")
        for key, label in DEV_OPTIONS:
            var = tk.BooleanVar()
            self.dev_vars[key] = var
            ttk.Checkbutton(f, text=label, variable=var).pack(anchor="w", pady=2)
        row = ttk.Frame(f)
        row.pack(anchor="w", pady=8)
        ttk.Button(row, text="Save", command=lambda: self.save_dev(False)).pack(side="left")
        ttk.Button(row, text="Save and launch", style="Accent.TButton", command=lambda: self.save_dev(True)).pack(side="left", padx=8)

        ttk.Label(f, text="Open an internal page", style="H.TLabel").pack(anchor="w", pady=(16, 4))
        grid = ttk.Frame(f)
        grid.pack(anchor="w")
        for i, (title, url) in enumerate(DEV_PAGES):
            ttk.Button(grid, text=title, command=lambda u=url: self.do_launch(u)).grid(row=i // 4, column=i % 4, padx=(0, 6), pady=3, sticky="ew")
        ttk.Label(f, text="Open a folder", style="H.TLabel").pack(anchor="w", pady=(16, 4))
        row = ttk.Frame(f)
        row.pack(anchor="w")
        for title, key in (("Profile folder", "profile_dir"), ("Browser data", "profile"),
                           ("Generated extension", "ext"), ("Workspace", "work")):
            ttk.Button(row, text=title, command=lambda k=key: open_path(settings.paths()[k])).pack(side="left", padx=(0, 6))
        ttk.Button(row, text="Browser log", command=self.open_log).pack(side="left")
        ttk.Label(f, style="Muted.TLabel", wraplength=900, justify="left", text=(
            "\nTip: after editing a mod, press Apply, then open chrome://extensions in the browser and click the reload "
            "icon on the Core extension (or simply restart the browser).")).pack(anchor="w")

    def save_dev(self, launch):
        try:
            actions.save_settings({"developer": {k: v.get() for k, v in self.dev_vars.items()}})
        except ValueError as e:
            messagebox.showerror("Cannot save", str(e))
            return
        self.log_write("Developer options saved.", "ok")
        if launch:
            self.do_launch()

    def open_log(self):
        p = settings.paths()["profile"] / "chrome_debug.log"
        if p.exists():
            open_path(p)
        else:
            messagebox.showinfo("Browser log", "No log yet. Enable 'Write a browser log' and launch the browser first.")

    # ---------- History ----------
    def tab_history(self, f):
        self.hist_tree = ttk.Treeview(f, columns=("id", "label", "mods"), show="headings", selectmode="browse")
        for c, w, t in (("id", 160, "When"), ("label", 520, "Change"), ("mods", 80, "Mods")):
            self.hist_tree.heading(c, text=t)
            self.hist_tree.column(c, width=w)
        self.hist_tree.pack(fill="both", expand=True)
        bar = ttk.Frame(f)
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Restore selected point", command=self.restore).pack(side="left")
        ttk.Label(bar, style="Muted.TLabel", text="  A snapshot is saved automatically before every change.").pack(side="left")

    def refresh_history(self):
        self.hist_tree.delete(*self.hist_tree.get_children())
        for h in mods.list_history():
            self.hist_tree.insert("", "end", iid=h["id"], values=(h["id"], h["label"], h["mods"]))

    def restore(self):
        sel = self.hist_tree.selection()
        if sel and messagebox.askyesno("Restore", "Restore settings and mods from this point?"):
            mods.rollback(sel[0])
            self.reload_all()
            self.log_write("Restored. Press Apply to rebuild.", "ok")

    # ---------- reload ----------
    def reload_all(self):
        self.refresh_profiles()
        self.load_form()
        self.load_ai()
        self.refresh_mods()
        self.refresh_history()
        s = settings.load()
        for k, v in self.dev_vars.items():
            v.set(bool(s["developer"].get(k)))
        self.refresh_home()


def main():
    if sys.platform == "win32" and not os.environ.get("CC_NO_ADMIN") and not policies.is_admin():
        if relaunch_admin():  # the elevated copy takes over; if the user declines UAC we simply continue
            return
    settings.init()
    root = tk.Tk()
    App(root)
    root.mainloop()
