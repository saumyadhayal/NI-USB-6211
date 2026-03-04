import nidaqmx

dev = "Dev1"

with nidaqmx.Task() as task:
    task.do_channels.add_do_chan(f"{dev}/port1/line0")
    task.write(True, auto_start=True)
    # input("Output is being held. Measure now and press <Enter> to finish...")