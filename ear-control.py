"""Nothing-styled GUI for Nothing Ear (2), built with CustomTkinter.

Uses the protocol and CLI code from ear2.py (keep both files in the same folder).
Protokoll: https://bharadwajraju.com/posts/nothing-ear-2-on-linux/

    python -m pip install customtkinter
    python ear2_gui.py
"""

import os
import queue
import sys
import threading

try:
    import customtkinter as ctk
except ImportError:
    raise SystemExit("customtkinter is missing. Install with: python -m pip install customtkinter")

from ear2 import (ANC_BYTE, FIT_TEST, MAC_RE, PACKETS, QUERY, list_devices,
                  load_saved_address, packet, save_address, talk)

ANC_LABELS = {
    "high": "High", "mid": "Medium", "low": "Low",
    "adaptive": "Adaptive", "off": "Off", "transparency": "Transparency",
}

BLACK, CARD, BORDER = "#000000", "#101010", "#2a2a2a"
BTN, BTN_HOVER = "#1c1c1c", "#2c2c2c"
WHITE, GREY = "#ffffff", "#8a8a8a"
RED, RED_HOVER = "#d71921", "#a8121a"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MONO = "Consolas" if sys.platform.startswith("win") else "DejaVu Sans Mono"
COLORS = {"info": GREY, "ok": WHITE, "error": RED}

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")
        self.configure(fg_color=BLACK)
        self.title("Nothing Ear")
        self.set_icon()
        self.geometry("440x610")
        self.resizable(False, False)

        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.anc_buttons = {}
        self.current_anc = None

        self.addr_var = ctk.StringVar(
            value=os.environ.get("NOTHING_EAR_DEVICE") or load_saved_address() or "")
        self.build()
        self.after(50, self.poll)

        if MAC_RE.match(self.addr_var.get().strip()):
            self.after(300, self.read_anc)
        else:
            self.after(300, self.search)

    def font(self, size=13, bold=False):
        return ctk.CTkFont(family=MONO, size=size, weight="bold" if bold else "normal")

    def set_icon(self):
        ico = os.path.join(HERE, "ear2_logo.ico")
        try:
            if sys.platform.startswith("win"):
                self.iconbitmap(ico)
            else:
                import tkinter as tk
                self._icon = tk.PhotoImage(file=os.path.join(HERE, "ear2_logo.png"))
                self.iconphoto(True, self._icon)
        except Exception:
            pass

    def card(self, title):
        frame = ctk.CTkFrame(self, corner_radius=18, fg_color=CARD,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkLabel(frame, text=title, font=self.font(12), text_color=GREY
                     ).pack(anchor="w", padx=16, pady=(12, 4))
        return frame

    def build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(18, 12))
        try:
            from PIL import Image
            logo = ctk.CTkImage(Image.open(os.path.join(HERE, "ear2_logo.png")), size=(40, 40))
            ctk.CTkLabel(head, text="", image=logo).pack(side="left")
        except Exception:
            ctk.CTkLabel(head, text="●", font=self.font(18), text_color=RED).pack(side="left")
        ctk.CTkLabel(head, text="  NOTHING EAR", font=self.font(24, True),
                     text_color=WHITE).pack(side="left")

        c = self.card("DEVICE")
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(0, 12))
        self.combo = ctk.CTkComboBox(
            row, variable=self.addr_var, values=[], command=self.on_pick, font=self.font(),
            fg_color=BTN, border_color=BORDER, text_color=WHITE,
            button_color=BTN_HOVER, button_hover_color=RED,
            dropdown_fg_color=CARD, dropdown_hover_color=BTN_HOVER,
            dropdown_text_color=WHITE, dropdown_font=self.font())
        self.combo.pack(side="left", fill="x", expand=True, padx=(4, 8))
        ctk.CTkButton(row, text="SEARCH", width=70, font=self.font(12, True),
                      fg_color=RED, hover_color=RED_HOVER, text_color=WHITE,
                      command=self.search).pack(side="right")

        c = self.card("NOISE CANCELLATION")
        grid = ctk.CTkFrame(c, fg_color="transparent")
        grid.pack(fill="x", padx=12, pady=(0, 8))
        for i, mode in enumerate(PACKETS["anc"]):
            grid.columnconfigure(i % 3, weight=1)
            b = ctk.CTkButton(grid, text=ANC_LABELS[mode].upper(), height=46,
                              font=self.font(12, True), corner_radius=12,
                              fg_color=BTN, hover_color=BTN_HOVER, text_color=WHITE,
                              command=lambda m=mode: self.set_anc(m))
            b.grid(row=i // 3, column=i % 3, padx=4, pady=4, sticky="ew")
            self.anc_buttons[mode] = b
        ctk.CTkButton(c, text="READ CURRENT MODE", font=self.font(12),
                      fg_color="transparent", border_width=1, border_color=GREY,
                      hover_color=BTN_HOVER, text_color=WHITE, command=self.read_anc
                      ).pack(padx=16, pady=(4, 14), fill="x")

        c = self.card("SETTINGS")
        for title, key in (("In-ear detection", "in-ear"), ("Low latency", "latency")):
            row = ctk.CTkFrame(c, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row, text=title, font=self.font(), text_color=WHITE).pack(side="left")
            sw = ctk.CTkSwitch(row, text="", width=46, fg_color="#333333",
                               progress_color=RED, button_color=WHITE,
                               button_hover_color="#dddddd")
            sw.configure(command=lambda k=key, s=sw, t=title: self.send(
                PACKETS[k]["on" if s.get() else "off"], f"{t}: {'on' if s.get() else 'off'}"))
            sw.pack(side="right")
        ctk.CTkButton(c, text="START EAR TIP FIT TEST", font=self.font(12, True),
                      fg_color=WHITE, hover_color="#cccccc", text_color=BLACK,
                      command=lambda: self.send(FIT_TEST, "Ear tip fit test")
                      ).pack(padx=16, pady=(8, 14), fill="x")

        self.status = ctk.CTkLabel(self, text="Ready", anchor="w", font=self.font(12),
                                   text_color=GREY)
        self.status.pack(fill="x", padx=22, pady=(0, 10))

    def set_status(self, text, kind="info"):
        self.status.configure(text=text, text_color=COLORS[kind])

    def highlight(self, mode):
        self.current_anc = mode
        for m, b in self.anc_buttons.items():
            if m == mode:
                b.configure(fg_color=RED, hover_color=RED_HOVER)
            else:
                b.configure(fg_color=BTN, hover_color=BTN_HOVER)

    def poll(self):
        while True:
            try:
                self.q.get_nowait()()
            except queue.Empty:
                break
        self.after(50, self.poll)

    def run(self, work, done=None, busy=""):
        if busy:
            self.set_status(busy)

        def target():
            with self.lock:
                try:
                    result = work()
                except (OSError, ValueError, SystemExit) as e:
                    msg = f"Error: {e}"
                    self.q.put(lambda: self.set_status(msg, "error"))
                    return
            if done:
                self.q.put(lambda: done(result))
        threading.Thread(target=target, daemon=True).start()

    def addr(self):
        text = self.addr_var.get().strip()
        for token in text.split():
            if MAC_RE.match(token):
                return token.upper()
        self.set_status("Select or enter a valid address (AA:BB:CC:DD:EE:FF)", "error")
        return None

    def send(self, hexstr, label, on_ok=None):
        a = self.addr()
        if not a:
            return

        def done(_):
            self.set_status(f"{label} ✓", "ok")
            if load_saved_address() != a:
                save_address(a)
            if on_ok:
                on_ok()
        self.run(lambda: talk(a, packet(hexstr)), done, f"Sending {label}...")

    def set_anc(self, mode):
        self.send(PACKETS["anc"][mode], f"ANC: {ANC_LABELS[mode]}",
                  on_ok=lambda: self.highlight(mode))

    def read_anc(self):
        a = self.addr()
        if not a:
            return

        def done(resp):
            if resp and len(resp) >= 10:
                name = ANC_BYTE.get(resp[9])
                if name:
                    self.highlight(name.lower())
                    self.set_status(f"Current ANC: {ANC_LABELS[name.lower()]}", "ok")
                    return
            self.set_status("Could not read ANC mode", "error")
        self.run(lambda: talk(a, packet(QUERY), want_reply=True), done, "Reading ANC mode...")

    def search(self):
        def done(devs):
            self.combo.configure(values=[f"{mac}  {name}" for name, mac in devs])
            if not devs:
                self.set_status("No paired devices found", "error")
                return
            pick = next((d for d in devs if "nothing" in d[0].lower()
                         or "ear" in d[0].lower()), None)
            if pick:
                self.addr_var.set(f"{pick[1]}  {pick[0]}")
            self.set_status(f"Found {len(devs)} device(s)", "ok")
        self.run(list_devices, done, "Searching for devices...")

    def on_pick(self, _value):
        self.read_anc()

if __name__ == "__main__":
    App().mainloop()
