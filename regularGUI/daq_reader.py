# daq_module.py

import nidaqmx
from nidaqmx.constants import TerminalConfiguration
from PyQt5.QtCore import QThread, pyqtSignal
import time


class DAQReader(QThread):
    """
    Reads analog and digital input channels continuously
    and emits:
        data_ready(x_array, y_dict) for graphing
        one_value(ai_values, di_values) for single-value mode
    """
    data_ready = pyqtSignal(object, object)
    one_value = pyqtSignal(object, object)

    def __init__(self, ai_channels, di_channels, one_value_mode, ai_terminal_config, device="Dev1"):
        super().__init__()
        self.ai_channels = ai_channels        # e.g., ["ai0", "ai1"] from the user input
        self.di_channels = di_channels        # e.g., ["port0/line0"] from user input
        self.ai_config = ai_terminal_config   # terminal configuration for AI channels
        self.one_mode = one_value_mode      # True if "Show only one value" is checked
        self.device = device        #  our Device = 'Dev2'
        self.running = True         # Flag to control reading loop for input channels

        # For plot mode
        self.x = []     # x values (time or sample index)
        self.y_dict = {ch: [] for ch in self.ai_channels + self.di_channels} # y values for each channel

    def run(self):
        """
        Loop: read all analog + digital channels and send results to GUI.
        """
        while self.running:
            # ---- Read all analog channels ----
            ai_vals = {}
            for ch in self.ai_channels:
                with nidaqmx.Task() as t:   # task for analog inputs
                    t.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{ch}",  # ai channel name
                        terminal_config=getattr(TerminalConfiguration, self.ai_config),  # terminal config from GUI
                        min_val=-10.0,
                        max_val=10.0
                    )
                    ai_vals[ch] = t.read() # dictionary with channel name: data value

            # ---- Read all digital channels ----
            di_vals = {}
            for ch in self.di_channels:
                with nidaqmx.Task() as t:
                    t.di_channels.add_di_chan(f"{self.device}/port0/{ch}")
                    val = t.read()
                    di_vals[ch] = 1 if val else 0

            # ---- Single value mode ----
            if self.one_mode:
                self.one_value.emit(ai_vals, di_vals)
                # time.sleep(0.1)
                # continue
                break  # Stop after one read if in single value mode

            # ---- Plot mode ----
            self.x.append(len(self.x))

            # Append new readings to the history for each channel
            for ch in self.ai_channels:
                self.y_dict[ch].append(ai_vals[ch]) 
                # dictionary with channel name: list of data values for plotting
            for ch in self.di_channels:
                self.y_dict[ch].append(di_vals[ch])

            # Send to GUI
            # Emits a copy of data which is k is channel name and v is list of values from the 
            # dictionary created for the plot mode.
            self.data_ready.emit(self.x.copy(), {k: v[:] for k, v in self.y_dict.items()})

            time.sleep(0.05)

    def stop(self):
        self.running = False