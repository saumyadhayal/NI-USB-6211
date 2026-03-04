'''
import nidaqmx

with nidaqmx.Task() as task:
    task.ao_channels.add_aio_voltage_chan(
        "Dev1/ao0",
        terminal_config=nidaqmx.constants.TerminalConfiguration.RSE,
        min_val=-10.0,
        max_val=10.0,)
    val = task.read()
    print("AI0 value: ", val)

'''
# main_gui.py
import sys
from PyQt5 import QtWidgets, QtCore, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import os, time
from daq_reader import DAQReader
import nidaqmx


class MplCanvas(FigureCanvasQTAgg):
    """Simple Matplotlib canvas widget."""
    def __init__(self):
        fig = Figure(figsize=(8, 5))    # size for the graph
        self.ax = fig.add_subplot(111)  # Create a single subplot, 111 means 1 row, 1 column, 1st plot
        super().__init__(fig)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NI USB-6211 DAQ Reader")

        # ---- Layout ----
        main = QtWidgets.QHBoxLayout()

        # LEFT column: reading UI
        left = QtWidgets.QVBoxLayout()
        left.addWidget(QtWidgets.QLabel("Reading Commands:"))
        self.ai_input = QtWidgets.QLineEdit("ai0, ai1")
        left.addWidget(QtWidgets.QLabel("Analog channels (comma-separated):"))
        left.addWidget(self.ai_input)

        
        term_row = QtWidgets.QHBoxLayout()
        term_row.addWidget(QtWidgets.QLabel("Terminal mode:"))
        self.ai_term_combo = QtWidgets.QComboBox()
        self.ai_term_combo.addItems(["RSE", "DIFF"])  # default first is RSE
        term_row.addWidget(self.ai_term_combo)
        term_row.addStretch(2)
        left.addLayout(term_row)


        self.di_input = QtWidgets.QLineEdit("line<0..4>")
        left.addWidget(QtWidgets.QLabel("Digital channels:"))
        left.addWidget(self.di_input)

        self.one_value_check = QtWidgets.QCheckBox("Show only one value")
        left.addWidget(self.one_value_check)

        btns = QtWidgets.QHBoxLayout()
        self.start_btn = QtWidgets.QPushButton("Start")
        self.stop_btn  = QtWidgets.QPushButton("Stop")
        btns.addWidget(self.start_btn)
        btns.addWidget(self.stop_btn)
        left.addLayout(btns)

        self.canvas = MplCanvas()
        left.addWidget(self.canvas)

        self.save_btn = QtWidgets.QPushButton("Save Plot")
        left.addWidget(self.save_btn)

        left.addWidget(QtWidgets.QLabel("Output:"))
        self.output_box = QtWidgets.QTextEdit()
        self.output_box.setReadOnly(True)
        left.addWidget(self.output_box)

        # ---------- RIGHT column: writing UI -------------
        right = QtWidgets.QVBoxLayout()
        right_in = QtWidgets.QGroupBox()
        rform = QtWidgets.QFormLayout()
        rform.addWidget(QtWidgets.QLabel("Write Instructions:"))

        self.ao_channels = QtWidgets.QLineEdit("ao0, ao1")
        rform.addWidget(QtWidgets.QLabel("Analog output channels (comma-separated):"))
        rform.addWidget(self.ao_channels)

        rform.addWidget(QtWidgets.QLabel("Supply Voltages (MAX 10V):"))
        self.write_voltages = QtWidgets.QLineEdit("2.50, 3.00")
        rform.addWidget(self.write_voltages)
        self.ao_start_btn  = QtWidgets.QPushButton("Start Supply")
        self.ao_stop_btn  = QtWidgets.QPushButton("Stop Supply")

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.ao_start_btn)
        row.addWidget(self.ao_stop_btn)
        rform.addRow(row)
        
        self.do_channels = QtWidgets.QLineEdit("line<0..4>")
        rform.addWidget(QtWidgets.QLabel("Digital output channels (comma-separated):"))
        rform.addWidget(self.do_channels)
        
        self.do_values = QtWidgets.QLineEdit("1, 0")   # 1 = HIGH, 0 = LOW
        rform.addWidget(QtWidgets.QLabel("DO Values (1=HIGH, 0=LOW):"))
        rform.addWidget(self.do_values)

        self.do_write_btn = QtWidgets.QPushButton("Write Digital Outputs")
        rform.addWidget(self.do_write_btn)
        right_in.setLayout(rform)
        right.addWidget(right_in)
        # Add both columns to the main row
        main.addLayout(left, stretch=4)
        main.addLayout(right, stretch=2)
        
        container = QtWidgets.QWidget()
        container.setLayout(main)
        self.setCentralWidget(container)

        # ---- Signals ----
        self.start_btn.clicked.connect(self.start_reading)
        self.stop_btn.clicked.connect(self.stop_reading)
        self.do_write_btn.clicked.connect(self.write_do)
        self.ao_start_btn.clicked.connect(self.supply_voltage)
        self.ao_stop_btn.clicked.connect(self.stop_voltage)

        self.reader = None
    # --------------------------------------------------------
    def start_reading(self):
        # Get user input for channels and mode
        ai_chs = [s.strip() for s in self.ai_input.text().split(",") if s.strip()]
        di_chs = [s.strip() for s in self.di_input.text().split(",") if s.strip()]
        one_mode = self.one_value_check.isChecked()

        # Clear plot
        self.canvas.ax.clear()
        self.canvas.ax.set_title("Live Plot")
        self.canvas.ax.set_xlabel("Samples")
        self.canvas.ax.set_ylabel("Value")
        self.canvas.draw()

        # Stop previous reader
        self.stop_reading()
        # Start DAQ thread

        self.reader = DAQReader(ai_chs, di_chs, one_mode, self.ai_term_combo.currentText())
        self.reader.data_ready.connect(self.update_plot)
        self.reader.one_value.connect(self.update_one_value)
        self.reader.start()

    def save_plot(self):
        # folder for saving images
        folder = "saved_plots"
        if not os.path.exists(folder):
            os.makedirs(folder)
        # build a simple filename with timestamp
        timestamp = time.strftime("%Y%m%d-%H%M%S")  # saved with date - time for uniqueness
        filepath = os.path.join(folder, f"plot_{timestamp}.png")
        self.canvas.figure.savefig(filepath, dpi=150)

    def write_do(self):
        do_chs = [s.strip() for s in self.do_channels.text().split(",") if s.strip()]
        do_vals = [int(s.strip()) for s in self.do_values.text().split(",") if s.strip()]
        with nidaqmx.Task() as t:
            for ch in do_chs:
                t.do_channels.add_do_chan(f"Dev1/port1/{ch}")
            t.write([bool(v) for v in do_vals])

    def supply_voltage(self):
        ao_chs = [s.strip() for s in self.ao_channels.text().split(",") if s.strip()]
        voltages = [float(s.strip()) for s in self.write_voltages.text().split(",") if s.strip()]
        with nidaqmx.Task() as t:
            for ch in ao_chs:
                t.ao_channels.add_ao_voltage_chan(
                    f"Dev1/{ch}",
                    min_val=-10.0,
                    max_val=10.0
                )
            t.write(voltages)
            
    def stop_voltage(self):
        ao_chs = [s.strip() for s in self.ao_channels.text().split(",") if s.strip()]
        with nidaqmx.Task() as t:
            for ch in ao_chs:
                t.ao_channels.add_ao_voltage_chan(
                    f"Dev1/{ch}",
                    min_val=-10.0,
                    max_val=10.0
                )
            t.write([0.0] * len(ao_chs))

    def update_plot(self, x, y_dict):   # basically caling matplotlib for updating plot
        """Plot multiple AI + DI channels."""
        self.canvas.ax.clear()
        for ch, ys in y_dict.items():
            self.canvas.ax.plot(x, ys, label=ch)

        self.canvas.ax.legend() # show channel names in legend
        self.canvas.ax.set_xlabel("Samples")
        self.canvas.ax.set_ylabel("Value")
        self.canvas.draw()

    def update_one_value(self, ai_vals, di_vals):
        """Show only single values (no plot)."""
        self.output_box.append(f"AI: {ai_vals}")    # show only latest value for each channel
        self.output_box.append("")
        self.output_box.append(f"DI: {di_vals}")
        self.output_box.append("-----")

    def closeEvent(self, event):    # if the window is closed this function gets called 
        # and we stop the thread to prevent it from running in the background
        """Stop thread on window close."""
        self.stop_reading()
        event.accept()  # accept the close event to actually close the window

    def stop_reading(self, event=None):
        if getattr(self, 'reader', None) is not None:
            try:
                if self.reader is not None or event is not None:
                    self.reader.stop()
                    self.reader = None
            except Exception as e:
                print(f"Reader not started/stopped. {e}")

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.resize(1100, 750)
    window.show()
    sys.exit(app.exec())