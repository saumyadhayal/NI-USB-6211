# daq_io.py

import time
from matplotlib import lines

# Try importing NI‑DAQmx
try:
    import nidaqmx
    from nidaqmx.constants import LineGrouping, TerminalConfiguration
    HAVE_NIDAQMX = True
except Exception:
    HAVE_NIDAQMX = False

# -----------------------------
#   SIMULATION STORAGE
# -----------------------------
_sim_do_states = {}            # stores last DO states per line
_sim_ai_t0 = time.time()       # AI sim time origin


# -----------------------------
#   DIGITAL OUTPUT (DO)
# -----------------------------
def write_do(device, lines, states):
    """
    lines  = ["port1/line0", "port1/line1", ...]
    states = [True, False, ...]
    """
    global _sim_do_states

    if not HAVE_NIDAQMX:
        # Simulate by storing values
        for ch, st in zip(lines, states):
            _sim_do_states[f"{device}/{ch}"] = bool(st)
        return

    try:
        with nidaqmx.Task() as t:
            states = states[-1::-1]
            for ch in lines:
                t.do_channels.add_do_chan(
                    f"{device}/{ch}")
                t.write([bool(s) for s in states], auto_start=True)
    except Exception:
        # Hardware error -> simulation fallback
        for ch, st in zip(lines, states):
            _sim_do_states[f"{device}/{ch}"] = bool(st)


# -----------------------------
#   DIGITAL INPUT (DI)
# -----------------------------
def read_di(device, lines):
    """
    Returns dict: {"port0/line0": 0/1, ...}
    """
    vals = {}

    if not HAVE_NIDAQMX:
        # Simple, visible toggling pattern for simulation
        for i, ch in enumerate(lines):
            vals[ch] = i
        return vals

    try:
        for ch in lines:
            with nidaqmx.Task() as t:
                t.di_channels.add_di_chan(f"{device}/{ch}")
                v = t.read()
                vals[ch] = 1 if bool(v) else 0
        return vals
    except Exception:
        # Hardware error -> simulation
        for i, ch in enumerate(lines):
            vals[ch] = i
        return vals


# -----------------------------
#   ANALOG OUTPUT (AO)
# -----------------------------
def write_ao(device, ao_channels, voltages):
    """
    Write analog voltages (clamped to 0..3.3 V).
    ao_channels = ["ao0", "ao1"])
    voltages    = [v0, v1, ...] (both should be same length)
    """
    # Clamp voltages to 0..3.3 V
    v_clamped = [max(0.0, min(3.3, float(v))) for v in voltages]

    if not HAVE_NIDAQMX:
        return v_clamped    # send/simulate by returning clamped values

    try:
        with nidaqmx.Task() as t:
            for ch in ao_channels:
                t.ao_channels.add_ao_voltage_chan(
                    f"{device}/{ch}",
                    min_val=0.0,
                    max_val=3.3
                )
            t.write(v_clamped, auto_start=True) # auto_start=True to write immediately
    except Exception:
        # On failure, just simulate (return clamped values so UI can echo what would be set)
        pass

    return v_clamped


# -----------------------------
#   ANALOG INPUT (AI)
# -----------------------------
def read_ai(device, ai_channels, term_mode="RSE"):
    """
    Read analog inputs; returns dict { "ai0": float, ... }.
    term_mode: "RSE" or "DIFF" (passed to NI-DAQmx if available).
    """
    vals = {}

    if not HAVE_NIDAQMX:
        # Simulation
        t = time.time() - _sim_ai_t0
        for i, ch in enumerate(ai_channels):
            vals[ch] = float(i)
        return vals

    # NI‑DAQmx path
    try:
        # Map mode to enum; RSE accepts ai0..ai15; DIFF accepts ai0..ai7 per rule.
        from nidaqmx.constants import TerminalConfiguration
        term = TerminalConfiguration.RSE if str(term_mode).upper() != "DIFF" else TerminalConfiguration.DIFF

        for ch in ai_channels:
            with nidaqmx.Task() as t:
                t.ai_channels.add_ai_voltage_chan(
                    f"{device}/ai{ch}",
                    terminal_config=term,
                    min_val=-10.0,
                    max_val=10.0
                )
                v = t.read()
                vals[ch] = float(v)
        return vals
    
    except Exception:
        # Hardware error -> simulation
        t = time.time() - _sim_ai_t0
        for i, ch in enumerate(ai_channels):
            vals[ch] = 0.0
        return vals