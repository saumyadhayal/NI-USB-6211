# main_gui.py
import sys
import time
import os

from PyQt5.QtWidgets import QFileDialog
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QGroupBox, QGridLayout,
    QCheckBox, QHBoxLayout, QDoubleSpinBox, QLineEdit, QComboBox,
    QPushButton, QDialog, QMessageBox, 
)
from PyQt5.QtCore import Qt, QTimer
from toggle_switch import ToggleSwitch
# ---- Matplotlib for AI graph ----

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure


from daq_io import write_do, read_di, write_ao, read_ai, HAVE_NIDAQMX


class DOCircle(QLabel):
    def __init__(self, size=18):
        super().__init__()
        self.size = size
        self.setFixedSize(size, size)
        self.set_color("red")

    def set_color(self, color): # to set color of circle
        self.setStyleSheet(
            f"background-color:{color}; border-radius:{self.size//2}px; border:1px solid black;")


class AIGraph(QDialog):
    """
    AI live graph dialog.
    - If used in snapshot mode: call .plot_snapshot(t_list, y_dict) and exec()/exec_().
    - If used in live mode: call .init_live(channels) once, then call .update_plot(t_list, y_dict) repeatedly.
    """
    def __init__(self, ax=None, fig=None): # setting up the figure and axes for plotting
        super().__init__()
        self.setWindowTitle("AI Inputs Over Time")
        self._live = False
        self._channels = [] # list of channel names in current graph
        self._t0 = None # time origin for x-axis 

        self.layout = QVBoxLayout(self)

        self.fig = fig or Figure(figsize=(7, 3.8))  # continue using main window's figure if already using one
                                                    # otherwise create new
        self.ax = ax or self.fig.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.fig)

        self.layout.addWidget(self.canvas)

        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.set_title("AI (Analog Inputs) History")
        self.ax.grid(True, alpha=0.3)

        self._lines = {}  # ch -> Line2D object for live updates

    def init_live(self, channels):
        """Prepare the figure for live updates with given channels."""

        self._live = True
        self._channels = list(channels)
        self._t0 = None
        self.ax.clear()
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.set_title("Analog Inputs History")
        self.ax.grid(True, alpha=0.3)   # apha for lighter grid

        colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
                  "#17becf", "#8c564b", "#7f7f7f", "#bcbd22", "#e377c2"]
        self._lines = {}
        for i, ch in enumerate(self._channels):
            (line,) = self.ax.plot([], [], label=ch, color=colors[i % len(colors)], linewidth=2)
            self._lines[ch] = line

        self.ax.legend(ncol=2)  # ncolumn legend for compactness
        self.canvas.draw()

    def update_plot(self, t_list, y_dict):
        """Update live lines in-place. Safe to call every timer tick."""

        # Normalize time so plot starts at 0 s
        if self._t0 is None:
            self._t0 = t_list[0]
        xs = [t - self._t0 for t in t_list]

        for ch in self._channels:
            ys = y_dict.get(ch, []) # get y axis values
            n = min(len(xs), len(ys))   # get max and min length
            line = self._lines.get(ch)  # gets the channels
            if line:
                line.set_data(xs[:n], ys[:n])   # set data on matplotlib graph

        # Autoscale axes to new data
        self.ax.relim()
        self.ax.autoscale_view()
        self.ax.set_ylim(bottom=-1.0, top=3.5)

        self.canvas.draw_idle()

    def plot_snapshot(self, t_list, y_dict):
        """One-off static plot."""
        self._live = False
        self.ax.clear()

        if not t_list or all(len(y) == 0 for y in y_dict.values()):
            self.ax.text(0.5, 0.5, "No AI samples collected yet.", ha="center", va="center")
            self.canvas.draw()
            return

        t0 = t_list[0]
        xs = [t - t0 for t in t_list]

        colors = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e",
                  "#17becf", "#8c564b", "#7f7f7f", "#bcbd22", "#e377c2"]
        for i, (ch, ys) in enumerate(y_dict.items()):
            if not ys:
                continue
            n = min(len(xs), len(ys))
            self.ax.plot(xs[:n], ys[:n], label=ch, color=colors[i % len(colors)], linewidth=2)

        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.set_title("AI (Analog Inputs) History")
        self.ax.grid(True, alpha=0.3)
        self.ax.legend(ncol=2)
        self.canvas.draw()


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        
        self.fig = Figure(figsize=(7, 3.8))
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.fig)

        self.setWindowTitle(f"Ni-DAQ Deck")

        self.device = "Dev1"

        # --- AI history buffers (rolling) ---
        self.ai_hist_t = []     # list[float]
        self.ai_hist_y = {}     # dict[str, list[float]]
        self.AI_MAX_POINTS = 1000  # keep last ~150s at 150 ms interval

        # Live graph dialog reference
        self.ai_graph_dlg = None

        root = QVBoxLayout(self)

        # -------------------------
        # Simulation banner
        # -------------------------
        if not HAVE_NIDAQMX:
            banner = QLabel("SIMULATION MODE (No NI-DAQmx or device not accessible)")
            banner.setStyleSheet("color:white; background:#c97a00; padding:6px;")
            root.addWidget(banner)

        # -------------------------
        # DIGITAL OUTPUTS (DO)
        # -------------------------
        do_box = QGroupBox("Digital Outputs")
        do_grid = QGridLayout(do_box)

        self.do_lines = [f"port1/line{i}" for i in range(4)]
        self.do_switches = []
        self.do_circles = []

        for i, ch in enumerate(self.do_lines):
            lbl = QLabel(ch)
            sw = ToggleSwitch()
            sw.toggled.connect(self.update_do)
            circ = DOCircle()

            do_grid.addWidget(lbl, i, 0)
            do_grid.addWidget(sw,  i, 1)
            do_grid.addWidget(circ, i, 2)

            self.do_switches.append(sw)
            self.do_circles.append(circ)

        root.addWidget(do_box)

        # -------------------------
        # DIGITAL INPUTS (DI)
        # -------------------------
        di_box = QGroupBox("Digital Inputs (live)")
        di_grid = QGridLayout(di_box)

        # digital values for port0/line<0..3>
        self.di_lines = [f"port0/line{i}" for i in range(4)]
        self.di_labels = []

        di_grid.addWidget(QLabel("Channel"), 0, 0)
        di_grid.addWidget(QLabel("Value"),   0, 1)

        for i, ch in enumerate(self.di_lines, start=1):
            lbl = QLabel(ch)
            val = QLabel("0")
            val.setAlignment(Qt.AlignCenter)
            val.setFixedWidth(36)
            di_grid.addWidget(lbl, i, 0)
            di_grid.addWidget(val, i, 1)
            self.di_labels.append(val)

        root.addWidget(di_box)

        # -------------------------
        # ANALOG OUTPUTS (AO)
        # -------------------------
        ao_box = QGroupBox("Analog Outputs (0-3.3 V)")
        ao_layout = QGridLayout(ao_box)

        self.ao_channels = ["ao0", "ao1"]
        self.ao_spins = []

        for i, ch in enumerate(self.ao_channels):
            lbl = QLabel(ch)
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 3.3)   # clamp in UI
            spin.setSingleStep(0.1)
            spin.setDecimals(3)
            spin.setValue(0.0)
            self.ao_spins.append(spin)

            ao_layout.addWidget(lbl,  i, 0)
            ao_layout.addWidget(spin, i, 1)

        # Buttons: Apply, Zero All
        btn_row = QHBoxLayout()
        apply_btn = QPushButton("Apply")
        zero_btn  = QPushButton("Zero All")
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(zero_btn)
        ao_layout.addLayout(btn_row, len(self.ao_channels), 0, 1, 2)

        # Wire buttons
        apply_btn.clicked.connect(self.apply_ao)
        zero_btn.clicked.connect(self.zero_ao)

        root.addWidget(ao_box)

        # -------------------------
        # ANALOG INPUTS (AI)
        # -------------------------
        ai_box = QGroupBox("Analog Inputs (0-3.3 V)")
        ai_layout = QVBoxLayout(ai_box)

        # Config row: channels + terminal mode + Graph AI + Live checkbox
        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("Channels (comma):"))
        self.ai_edit = QLineEdit("0,1")
        cfg_row.addWidget(self.ai_edit)

        cfg_row.addWidget(QLabel("Terminal:"))
        self.ai_term = QComboBox()
        self.ai_term.addItems(["RSE", "DIFF"])
        cfg_row.addWidget(self.ai_term)

        apply_ai_btn = QPushButton("Apply Channels")
        cfg_row.addWidget(apply_ai_btn)

        self.ai_live_check = QCheckBox("Live")
        cfg_row.addWidget(self.ai_live_check)

        graph_ai_btn = QPushButton("Graph AI")
        cfg_row.addWidget(graph_ai_btn)

        ai_layout.addLayout(cfg_row)

        # Rule/wiring note and inline warning area
        rules = QLabel("Rules: DIFF -> ai0..ai7 (connect to A-). RSE -> ai0..ai15 (ref to device GND).")
        rules.setStyleSheet("color:#333;")  # color: grey
        ai_layout.addWidget(rules)

        self.save_btn = QPushButton("Save Plot")
        ai_layout.addWidget(self.save_btn)
        self.save_btn.clicked.connect(self.save_plot)

        self.ai_warn = QLabel("")
        self.ai_warn.setStyleSheet("color:#a00;")
        ai_layout.addWidget(self.ai_warn)

        # Table/grid for live values
        self.ai_grid = QGridLayout()
        self.ai_label_pairs = []  # list[ (ch_label, val_label) ]
        ai_layout.addLayout(self.ai_grid)

        
        # Build initial table
        self.rebuild_ai_table()

        # Wire config actions
        apply_ai_btn.clicked.connect(self.rebuild_ai_table)
        self.ai_term.currentIndexChanged.connect(self.rebuild_ai_table)
        graph_ai_btn.clicked.connect(self.on_graph_ai_clicked)

        root.addWidget(ai_box)

        # -------------------------
        # Timers: poll DI + AI
        # -------------------------
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_di_ai)
        self.timer.start(150)  # calls function every 150 ms

    # -------------------------
    # Helpers
    # -------------------------
    def parse_ai_channels(self):
        text = self.ai_edit.text().strip()
        if not text:
            return []
        return [s.strip() for s in text.split(",") if s.strip()]

    def filter_ai_by_mode(self, channels, term_mode):
        """Enforce rule: DIFF -> ai0..ai7, RSE -> ai0..ai15. Checks user inputs.
           Returns (allowed_channels, invalid_channels)"""
        term_mode = term_mode.upper()
        if term_mode == "DIFF":
            allowed = {f"{i}" for i in range(8)}
        else:  # RSE
            allowed = {f"{i}" for i in range(16)}
        filtered = [ch for ch in channels if ch in allowed]
        invalid = [ch for ch in channels if ch not in allowed]
        return filtered, invalid

    def _close_live_graph_if_any(self, reason: str = ""):
        """Close live graph dialog if open (e.g., when channels/mode change)."""
        if self.ai_graph_dlg is not None:
            try:
                self.ai_graph_dlg.close()
            except Exception:
                pass
            self.ai_graph_dlg = None
            self.ai_live_check.setChecked(False)
            if reason:
                # user feedback in status-like label
                self.ai_warn.setText((self.ai_warn.text() + "  ").strip() + f"(Live graph closed: {reason})")

    def rebuild_ai_table(self):
        self._close_live_graph_if_any("AI config changed")

        # Clear old widgets
        while self.ai_label_pairs:
            ch_lbl, val_lbl = self.ai_label_pairs.pop()
            ch_lbl.deleteLater()
            val_lbl.deleteLater()

        # Header
        self.ai_grid.addWidget(QLabel("Channel"), 0, 0)
        self.ai_grid.addWidget(QLabel("Value (V)"), 0, 1)

        # Channels + enforce mode rules
        term = self.ai_term.currentText().strip().upper()
        raw_channels = self.parse_ai_channels()
        channels, invalid = self.filter_ai_by_mode(raw_channels, term)

        if invalid:
            self.ai_warn.setText(f"Dropped invalid for {term}: {', '.join(invalid)}")
        else:
            self.ai_warn.setText("")

        self.ai_channels = channels

        # Reset AI history buffers to match current set
        self.ai_hist_t = []
        self.ai_hist_y = {ch: [] for ch in self.ai_channels}

        # Create rows for current channels
        self.ai_val_labels = []
        for i, ch in enumerate(self.ai_channels, start=1):
            ch_lbl = QLabel(ch)
            val_lbl = QLabel("0.0000")
            val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            val_lbl.setFixedWidth(80)
            self.ai_grid.addWidget(ch_lbl, i, 0)
            self.ai_grid.addWidget(val_lbl, i, 1)
            self.ai_label_pairs.append((ch_lbl, val_lbl))
            self.ai_val_labels.append(val_lbl)

    # -------------------------
    # DO write
    # -------------------------
    def update_do(self):
        states = [sw.isChecked() for sw in self.do_switches]
        write_do(self.device, self.do_lines, states)
        for st, circ in zip(states, self.do_circles):
            circ.set_color("green" if st else "red")

    # -------------------------
    # AO write
    # -------------------------
    def apply_ao(self):
        volts = [spin.value() for spin in self.ao_spins]
        v_applied = write_ao(self.device, ["ao0", "ao1"], volts)
        # Snap UI to clamped values (0..3.3)
        for spin, v in zip(self.ao_spins, v_applied):
            if abs(spin.value() - v) > 1e-6:
                spin.blockSignals(True)
                spin.setValue(v)
                spin.blockSignals(False)

    def zero_ao(self):
        for spin in self.ao_spins:
            spin.setValue(0.0)
        self.apply_ao()

    # -------------------------
    # DI + AI update (with maintaining history for graphing)
    # -------------------------
    def update_di_ai(self):
        # DI values
        di_vals = read_di(self.device, self.di_lines)
        for i, ch in enumerate(self.di_lines):
            v = di_vals.get(ch, 0)
            self.di_labels[i].setText(str(v))
            self.di_labels[i].setStyleSheet(
                "color:green; font-weight:bold;" if v else "color:red; font-weight:bold;")

        # AI values + history
        term = self.ai_term.currentText().strip().upper()
        now = time.time()
        ai_vals = read_ai(self.device, getattr(self, "ai_channels", []), term)

        # Append to history (and trim)
        if self.ai_channels:
            self.ai_hist_t.append(now)
            if len(self.ai_hist_t) > self.AI_MAX_POINTS:
                self.ai_hist_t.pop(0)

        for i, ch in enumerate(getattr(self, "ai_channels", [])):
            v = float(ai_vals.get(ch, float('nan')))
            self.ai_val_labels[i].setText(f"{v:0.4f}" if v == v else "nan")  # NaN check
            lst = self.ai_hist_y.setdefault(ch, [])
            lst.append(v)
            if len(lst) > self.AI_MAX_POINTS:
                lst.pop(0)

        # If live graph is active, push latest history
        if self.ai_graph_dlg is not None and self.ai_live_check.isChecked():
            try:
                # Build a dict for current channels only
                y_curr = {ch: self.ai_hist_y.get(ch, []) for ch in self.ai_channels}
                self.ai_graph_dlg.update_plot(self.ai_hist_t, y_curr)
            except Exception:
                pass  # avoid crashing UI if dialog was closed unexpectedly

    # -------------------------
    # Graph AI button handler
    # -------------------------
    def on_graph_ai_clicked(self):

        channels = getattr(self, "ai_channels", [])
        if not channels:
            QMessageBox.information(self, "AI Plot", "No AI channels selected.")
            return

        # Live or snapshot?
        live = self.ai_live_check.isChecked()

        # If live: open non-modal dialog and keep updating from timer
        if live:
            # Close any existing live graph first
            self._close_live_graph_if_any()

            self.ai_graph_dlg = AIGraph(ax=self.ax, fig=self.fig)
            self.ai_graph_dlg.init_live(channels)
            try:
                self.ai_graph_dlg.show()  # non-modal window that updates continuously
            except Exception:
                pass

            # Push an initial frame immediately
            y_curr = {ch: self.ai_hist_y.get(ch, []) for ch in self.ai_channels}
            self.ai_graph_dlg.update_plot(self.ai_hist_t, y_curr)
            return
        else:
            t_copy = self.ai_hist_t[:]
            y_copy = {ch: self.ai_hist_y.get(ch, [])[:] for ch in channels}
            dlg = AIGraph(ax=self.ax, fig=self.fig)
            dlg.plot_snapshot(t_copy, y_copy)
            dlg.exec()
        # Snapshot: modal dialog with current history
        

    def save_plot(self):
        os.makedirs("saved_plots", exist_ok=True)
        ts = time.strftime("%m.%d-%H.%M.%S")
        path = os.path.join("saved_plots", f"{ts}.png")

        
        if self.ai_graph_dlg is not None:
            self.ai_graph_dlg.canvas.draw()
            self.ai_graph_dlg.fig.savefig(path, dpi=150, bbox_inches="tight")
            QMessageBox.information(self, "Saved", f"Saved plot to:\n{path}")
            return

        QMessageBox.information(self, "Saved", f"Saved plot to:\n{path}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(720, 780)
    w.show()
    try:
        sys.exit(app.exec())
    except Exception:
        sys.exit(app.exec_())