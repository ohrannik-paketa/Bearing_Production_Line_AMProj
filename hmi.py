"""
hmi.py
======
Scalable, modern Tkinter HMI for the parallel ball bearing production line.
Features grid-based resizing and a dark industrial color palette.
"""

import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk
from collections import deque

# ---------------------------------------------------------------------------
# Modern Industrial Color Palette
# ---------------------------------------------------------------------------
BG_BASE      = "#080c16"  # Deep dark navy background
PANEL_BG     = "#121b2d"  # Slightly lighter panel background
PANEL_BORDER = "#1f3a5e"  # Subtle border for panels
TEXT_MAIN    = "#00E5FF"  # Bright cyan for primary readouts
TEXT_DIM     = "#4d789e"  # Muted steel blue for labels
OK_GREEN     = "#00FF88"  # Neon green for active/running
ALARM_RED    = "#FF2A55"  # Piercing red for faults
WARNING      = "#FFD700"  # Amber/gold

STEP_DELAY = 0.40

EVT_ASSEMBLED = "assembled"
EVT_REJECTED  = "rejected"
EVT_STAGE     = "stage"
EVT_STATUS    = "status"
EVT_STOPPED   = "stopped"

# ---------------------------------------------------------------------------
# Instrumented Logic
# ---------------------------------------------------------------------------
class InstrumentedLine:
    def __init__(self, event_queue: queue.Queue, stop_event: threading.Event):
        self._q = event_queue
        self._stop = stop_event
        self.components = ["outer_ring", "inner_ring", "steel_balls", "cage"]
        self.bins = {n: deque() for n in self.components}
        self.serial_counters = {n: 0 for n in self.components}
        self.bearing_counter = 0
        self.shipped = 0
        self._run_flag = threading.Event()
        self._run_flag.set()
        # Updated defect reasons mapped to the new backend logic
        self.defect_reasons = {
            "outer_ring": "Machining tolerance exceeded",
            "inner_ring": "Inner diameter too small",
            "steel_balls": "Out of roundness",
            "cage": "Bent retainer prong",
            "assembly": "Component dropped/lost during transfer",
            "packaging": "Carton jam / Packaging destroyed"
        }

    def _stage(self, key: str, component: str) -> None:
        if not self._stop.is_set():
            self._q.put({"type": EVT_STAGE, "stage": key, "component": component})
            # Replaces time.sleep() with an interruptible tick loop
            elapsed = 0
            while elapsed < STEP_DELAY:
                self._run_flag.wait()  # Blocks instantly if E-Stop clears this flag
                if self._stop.is_set(): break
                time.sleep(0.05)
                elapsed += 0.05

    def _maybe_fail(self, threshold: float = 0.05):
        return random.random() < threshold

    def _produce_lane(self, name: str):
        while len(self.bins[name]) < 1:
            if self._stop.is_set(): return
            self.serial_counters[name] += 1
            serial = self.serial_counters[name]
            
            self._stage(f"make_{name}", name)
            self._stage(f"qc_{name}", name)
            
            if self._maybe_fail():
                self._q.put({
                    "type": EVT_REJECTED,
                    "item": f"{name.replace('_', ' ').title()} #{serial}",
                    "station": f"QC - {name}",
                    "reason": self.defect_reasons[name],
                })
            else:
                self._stage(f"bin_{name}", name)
                self.bins[name].append(serial)

    def _refill_bins(self):
        threads = []
        for name in self.components:
            t = threading.Thread(target=self._produce_lane, args=(name,))
            threads.append(t)
            t.start()
        for t in threads: t.join()

    def _assemble_one(self):
        if self._stop.is_set(): return
        self._stage("assembly", "bearing")
        for n in self.components: self.bins[n].popleft()
        
        self.bearing_counter += 1
        b_serial = self.bearing_counter
        self._stage("final_qc", "bearing")
        
        if self._maybe_fail(0.06): # Assembly fault chance
            self._q.put({"type": EVT_REJECTED, "item": f"Bearing #{b_serial}", "station": "Final QC", "reason": self.defect_reasons["assembly"]})
            return
            
        self._stage("packaging", "bearing")
        if self._maybe_fail(0.03): # Packaging fault chance
            self._q.put({"type": EVT_REJECTED, "item": f"Bearing #{b_serial}", "station": "Packaging", "reason": self.defect_reasons["packaging"]})
            return

        self._q.put({"type": EVT_ASSEMBLED, "serial": b_serial})
        self._stage("shipped", "bearing")
        self.shipped += 1

    def run_until_stopped(self):
        self._q.put({"type": EVT_STATUS, "msg": "SYSTEM: ONLINE - PROCESSING"})
        while not self._stop.is_set():
            self._refill_bins()
            if self._stop.is_set(): break
            self._assemble_one()
        self._q.put({"type": EVT_STATUS, "msg": f"SYSTEM: HALTED - {self.shipped} UNITS SECURED"})
        self._q.put({"type": EVT_STOPPED})


# ---------------------------------------------------------------------------
# Scalable HMI GUI
# ---------------------------------------------------------------------------
class HMI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SRH Robotics - Production Dashboard")
        self.configure(bg=BG_BASE)
        # HMI is now fully scalable
        self.geometry("900x600")
        self.minsize(800, 500)
        
        # Configure root grid scaling
        self.grid_rowconfigure(2, weight=1) 
        self.grid_columnconfigure(0, weight=1)

        self._q = queue.Queue()
        self._stop_event = threading.Event()
        self._thread = None
        self._n_assembled = 0
        self._n_rejected = 0
        self._stage_cards = {} # Holds references to change card colors dynamically
        
        self._style_treeview()
        self._build_ui()
        self._poll()

    def _style_treeview(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", 
                        background=PANEL_BG, foreground=TEXT_MAIN, 
                        fieldbackground=PANEL_BG, rowheight=25, 
                        font=("Consolas", 10), borderwidth=0)
        style.configure("Treeview.Heading", 
                        background=BG_BASE, foreground=TEXT_DIM, 
                        font=("Consolas", 10, "bold"), borderwidth=1, relief="solid")
        style.map("Treeview", background=[("selected", PANEL_BORDER)], foreground=[("selected", "#ffffff")])

    def _build_ui(self):
        # 1. Top Header & Alarm Banner
        hdr_frame = tk.Frame(self, bg=BG_BASE, pady=5)
        hdr_frame.grid(row=0, column=0, sticky="ew", padx=10)
        hdr_frame.columnconfigure(0, weight=1)
        
        self._alarm_banner = tk.Label(hdr_frame, text="SYSTEM CLEAR", bg=PANEL_BORDER, fg=TEXT_DIM, font=("Consolas", 12, "bold"), pady=8)
        self._alarm_banner.grid(row=0, column=0, sticky="ew")

        # 2. Control Panel (Counters & Buttons)
        ctrl_frame = tk.Frame(self, bg=BG_BASE)
        ctrl_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=10)
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=1)
        ctrl_frame.columnconfigure(2, weight=1)

        self._assembled_var = tk.StringVar(value="0000")
        self._rejected_var = tk.StringVar(value="0000")
        self._counter_tile("UNITS ASSEMBLED", self._assembled_var, TEXT_MAIN, ctrl_frame, 0)
        self._counter_tile("REJECTED PARTS", self._rejected_var, ALARM_RED, ctrl_frame, 1)

        btn_frame = tk.Frame(ctrl_frame, bg=BG_BASE)
        btn_frame.grid(row=0, column=2, sticky="e")
        self._btn_start = tk.Button(btn_frame, text="INITIATE", bg=PANEL_BORDER, fg=OK_GREEN, activebackground=OK_GREEN, activeforeground="#000", font=("Consolas", 12, "bold"), width=12, relief="flat", command=self._start)
        self._btn_start.pack(side="left", padx=5)
        self._btn_soft_stop = tk.Button(btn_frame, text="SOFT HALT", bg=PANEL_BORDER, fg=TEXT_DIM, activebackground=WARNING, font=("Consolas", 12, "bold"), width=10, relief="flat", state="disabled", command=self._soft_stop)
        self._btn_soft_stop.pack(side="left", padx=5)

        self._btn_estop = tk.Button(btn_frame, text="E-STOP", bg=ALARM_RED, fg=BG_BASE, activebackground="#ff0000", font=("Consolas", 12, "bold"), width=10, relief="flat", state="disabled", command=self._trigger_estop)
        self._btn_estop.pack(side="left", padx=5)

        # 3. Dynamic Pipeline Dashboard (Scalable Grid instead of Canvas)
        pipe_frame = tk.Frame(self, bg=BG_BASE)
        pipe_frame.grid(row=2, column=0, sticky="nsew", padx=10)
        
        # Create a 4-row (components) by 7-col (stages) grid
        for r in range(4): pipe_frame.rowconfigure(r, weight=1)
        for c in range(7): pipe_frame.columnconfigure(c, weight=1)

        components = ["outer_ring", "inner_ring", "steel_balls", "cage"]
        abbr = ["OUTER RNG", "INNER RNG", "STL BALLS", "CAGE RETAIN"]
        
        for i, name in enumerate(components):
            self._create_stage_card(pipe_frame, i, 0, f"MAKE\n{abbr[i]}", f"make_{name}")
            self._create_stage_card(pipe_frame, i, 1, "QC", f"qc_{name}")
            self._create_stage_card(pipe_frame, i, 2, "BUFFER", f"bin_{name}")

        # Shared downstream stages span across all 4 rows visually
        self._create_stage_card(pipe_frame, 0, 3, "ASSEMBLY\nSTATION", "assembly", rowspan=4)
        self._create_stage_card(pipe_frame, 0, 4, "FINAL\nQC", "final_qc", rowspan=4)
        self._create_stage_card(pipe_frame, 0, 5, "PACKAGE\nLINE", "packaging", rowspan=4)
        self._create_stage_card(pipe_frame, 0, 6, "SHIPPING\nLOGISTICS", "shipped", rowspan=4)

        # 4. Status Bar & Log Area
        log_frame = tk.Frame(self, bg=BG_BASE)
        log_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=10)
        log_frame.columnconfigure(0, weight=1)

        self._status_var = tk.StringVar(value="SYSTEM: STANDBY")
        tk.Label(log_frame, textvariable=self._status_var, bg=BG_BASE, fg=WARNING, font=("Consolas", 10)).pack(anchor="w")

        self._tree = ttk.Treeview(log_frame, columns=("Item", "Station", "Reason"), show="headings", height=5)
        self._tree.heading("Item", text="IDENTIFIER")
        self._tree.heading("Station", text="FAULT ORIGIN")
        self._tree.heading("Reason", text="DIAGNOSTIC REASON")
        self._tree.column("Item", width=150, anchor="center")
        self._tree.column("Station", width=150, anchor="center")
        self._tree.column("Reason", width=400, anchor="w")
        self._tree.pack(fill="x", pady=5)

    def _counter_tile(self, label, var, color, parent, col):
        tile = tk.Frame(parent, bg=PANEL_BG, highlightbackground=PANEL_BORDER, highlightthickness=1, padx=20, pady=10)
        tile.grid(row=0, column=col, sticky="ew", padx=5)
        tk.Label(tile, text=label, bg=PANEL_BG, fg=TEXT_DIM, font=("Consolas", 10)).pack(anchor="w")
        tk.Label(tile, textvariable=var, bg=PANEL_BG, fg=color, font=("Consolas", 24, "bold")).pack(anchor="e")

    def _create_stage_card(self, parent, row, col, label, key, rowspan=1):
        """Creates a scalable dashboard tile for a specific pipeline stage."""
        card = tk.Frame(parent, bg=PANEL_BG, highlightbackground=PANEL_BORDER, highlightthickness=1)
        card.grid(row=row, column=col, rowspan=rowspan, sticky="nsew", padx=3, pady=3)
        # Center the text inside the frame
        lbl = tk.Label(card, text=label, bg=PANEL_BG, fg=TEXT_DIM, font=("Consolas", 9, "bold"), justify="center")
        lbl.place(relx=0.5, rely=0.5, anchor="center")
        self._stage_cards[key] = (card, lbl)

    def _highlight_stage(self, stage):
        if stage in self._stage_cards:
            card, lbl = self._stage_cards[stage]
            card.config(bg=TEXT_DIM, highlightbackground=TEXT_MAIN)
            lbl.config(bg=TEXT_DIM, fg=BG_BASE)
            self.after(int(STEP_DELAY * 1000), self._clear_stage, stage)

    def _clear_stage(self, stage):
        if stage in self._stage_cards:
            card, lbl = self._stage_cards[stage]
            card.config(bg=PANEL_BG, highlightbackground=PANEL_BORDER)
            lbl.config(bg=PANEL_BG, fg=TEXT_DIM)

    def _trigger_alarm(self, reason):
        self._alarm_banner.config(text=f"CRITICAL FAULT: {reason.upper()}", bg=ALARM_RED, fg=BG_BASE)
        self.after(2000, lambda: self._alarm_banner.config(text="SYSTEM CLEAR", bg=PANEL_BORDER, fg=TEXT_DIM))

    def _start(self):
        # Check if we are resuming from an E-Stop
        if hasattr(self, 'line') and not self.line._run_flag.is_set():
            self.line._run_flag.set()
            self._q.put({"type": EVT_STATUS, "msg": "SYSTEM: ONLINE - RESUMED"})
            self._btn_start.config(state="disabled", fg=TEXT_DIM, text="INITIATE")
            self._btn_estop.config(state="normal")
            self._btn_soft_stop.config(state="normal", fg=WARNING)
            self._alarm_banner.config(text="SYSTEM CLEAR", bg=PANEL_BORDER, fg=TEXT_DIM)
            return

        # Normal cold start
        if self._thread and self._thread.is_alive(): return
        self._stop_event.clear()
        self.line = InstrumentedLine(self._q, self._stop_event) # Saved to self.line to access run_flag
        self._thread = threading.Thread(target=self.line.run_until_stopped, daemon=True)
        self._thread.start()
        
        self._btn_start.config(state="disabled", fg=TEXT_DIM, text="INITIATE")
        self._btn_soft_stop.config(state="normal", fg=WARNING)
        self._btn_estop.config(state="normal")

    def _soft_stop(self):
        self._stop_event.set() # Lets current loops finish out naturally
        self._btn_soft_stop.config(state="disabled", fg=TEXT_DIM)
        self._btn_estop.config(state="disabled")
        self._q.put({"type": EVT_STATUS, "msg": "SYSTEM: SOFT HALT - FINISHING CYCLE"})

    def _trigger_estop(self):
        if self._thread and self._thread.is_alive():
            self.line._run_flag.clear() # Instantly blocks the _stage wait loops
            self._q.put({"type": EVT_STATUS, "msg": "SYSTEM: E-STOP ENGAGED - FROZEN"})
            self._btn_start.config(state="normal", fg=OK_GREEN, text="RESUME")
            self._btn_estop.config(state="disabled")
            self._btn_soft_stop.config(state="disabled", fg=TEXT_DIM)
            self._alarm_banner.config(text="E-STOP ACTIVE - PIPELINE FROZEN", bg=ALARM_RED, fg=BG_BASE)
    def _poll(self):
        try:
            while True:
                evt = self._q.get_nowait()
                t = evt["type"]
                if t == EVT_ASSEMBLED:
                    self._n_assembled += 1
                    self._assembled_var.set(f"{self._n_assembled:04d}")
                elif t == EVT_REJECTED:
                    self._n_rejected += 1
                    self._rejected_var.set(f"{self._n_rejected:04d}")
                    self._tree.insert("", "end", values=(evt["item"].upper(), evt["station"].upper(), evt["reason"].upper()))
                    self._tree.yview_moveto(1.0)
                    self._trigger_alarm(evt["reason"])
                elif t == EVT_STAGE:
                    self._highlight_stage(evt["stage"])
                elif t == EVT_STATUS:
                    self._status_var.set(evt["msg"])
                elif t == EVT_STOPPED:
                    self._btn_start.config(state="normal", fg=OK_GREEN)
        except queue.Empty: pass
        self.after(50, self._poll)

if __name__ == "__main__":
    HMI().mainloop()