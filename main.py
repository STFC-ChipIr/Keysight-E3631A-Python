import Keysight_E3631A as keysight

from PySide6 import QtWidgets, QtGui, QtCore
import pyqtgraph as pg

import argparse
import json
import time

from datetime import datetime

pg.setConfigOptions(antialias=True)

class PSUWorker(QtCore.QObject):

    read_current = QtCore.Signal(float)
    read_voltage = QtCore.Signal(float)

    def __init__(self, port: str, current: str, voltage: str, silent: bool):
        super().__init__()

        self.current = current
        self.voltage = voltage

        self.psu = keysight.Keysight_E3631A(port=port, _sound=not silent)
        # self.psu.send_scpi_command("DISPlay:WINDow:STATe OFF")
    
    def run(self):

        threshold_crossed = None
        while True:

            with open("limits.json", "r") as f:
                limits_json = json.loads(f.read())

            if self.current != "":
                current = self.psu.send_scpi_command("MEASure:CURRent:DC?")
                self.read_current.emit(float(current))

                self.write_to_log(self.current, current)

                if float(current) > limits_json["current_threshold_mA"] / 1000:

                    if threshold_crossed is None:
                        threshold_crossed = datetime.now()

                    # If threshold has been crossed for > hold_time, set voltage to 0
                    elif (datetime.now() - threshold_crossed).total_seconds() > limits_json["hold_time"]:
                        self.psu.set_P6V_voltage(0)

                        # Keep PSU at 0V for cut_time
                        time.sleep(limits_json["cut_time"])

                        # Return to 3.3V
                        self.psu.set_P6V_voltage(3.3)

                        with open("latchup_log.txt", "a") as f:
                            f.write(f"{threshold_crossed}\t{datetime.now()}\n")

                        threshold_crossed = None

                else:
                    threshold_crossed = None
                
            if self.voltage != "":
                voltage = self.psu.send_scpi_command("MEASure:VOLTage:DC?")
                self.read_voltage.emit(float(voltage))

                self.write_to_log(self.voltage, voltage)
        
            
    def write_to_log(self, path: str, value: str):
        with open(path, "a") as f:
            f.write(f"{datetime.now()}\t{value}\n")


class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, port: str, current: str, voltage: str, silent: bool):
        super(MainWindow, self).__init__()

        self.current = current
        self.voltage = voltage

        self.current_time: list[datetime] = []
        self.current_values: list[float] = []

        self.voltage_time: list[datetime] = []
        self.voltage_values: list[float] = []

        self.setWindowTitle("Agilent E3631A Data Logger")

        plot_widget = pg.PlotWidget()
        legend = plot_widget.addLegend()
        self.setCentralWidget(plot_widget)

        # Have two y-axes: https://github.com/pyqtgraph/pyqtgraph/blob/master/pyqtgraph/examples/MultiplePlotAxes.py
        self.p1 = plot_widget.plotItem
        self.p1.setLabels(left='Current [mA]')

        ## create a new ViewBox, link the right axis to its coordinate system
        self.p2 = pg.ViewBox()
        self.p1.showAxis('right')
        self.p1.scene().addItem(self.p2)
        self.p1.getAxis('right').linkToView(self.p2)
        self.p2.setXLink(self.p1)
        self.p1.getAxis('right').setLabel('Voltage [V]')#, color='#ffff00')
        self.p1.getAxis("bottom").setLabel("Time")


        axis = pg.DateAxisItem()
        plot_widget.setAxisItems({'bottom': axis})


        self.current_plot = pg.PlotCurveItem(pen="r", name="Current (mA)")
        self.p1.addItem(self.current_plot)

        self.voltage_plot = pg.PlotCurveItem(pen="y", name="Voltage (V)")
        legend.addItem(self.voltage_plot, self.voltage_plot.name())
        self.p2.addItem(self.voltage_plot)

        self.p1.vb.sigResized.connect(self.updateViews)


        self.worker = PSUWorker(port=port, current=current, voltage=voltage, silent=silent)
        self.worker.read_current.connect(self.on_current_read)
        self.worker.read_voltage.connect(self.on_voltage_read)

        self.t = QtCore.QThread(parent=self)
        self.worker.moveToThread(self.t)
        self.t.started.connect(self.worker.run)
        self.t.start()
    
    def updateViews(self):
        ## view has resized; update auxiliary views to match
        self.p2.setGeometry(self.p1.vb.sceneBoundingRect())
        
        ## need to re-update linked axes since this was called
        ## incorrectly while views had different shapes.
        ## (probably this should be handled in ViewBox.resizeEvent)
        self.p2.linkedViewChanged(self.p1.vb, self.p2.XAxis)

    
    def on_current_read(self, current: float):
        
        # if len(self.current_time) > 0:
        #     prev_time = self.current_time[-1]
        timestamp = datetime.now()
        self.current_time.append(timestamp.timestamp())
        self.current_values.append(current * 1000)

        # if len(self.current_time) > 0:
        #     print(f"interval: {timestamp.timestamp() - prev_time}")

        self.current_plot.setData(self.current_time, self.current_values)


    def on_voltage_read(self, voltage: float):
        timestamp = datetime.now()
        self.voltage_time.append(timestamp.timestamp())
        self.voltage_values.append(voltage)

        self.voltage_plot.setData(self.voltage_time, self.voltage_values)

    

parser = argparse.ArgumentParser()
parser.add_argument("port", type=str)
parser.add_argument("--current", type=str, default="")
parser.add_argument("--voltage", type=str, default="")
parser.add_argument("--silent", action="store_true")

if __name__ == "__main__":
    args = parser.parse_args()

    print(f"Port: {args.port}\nCurrent log: {args.current}\nVoltage log: {args.voltage}\nSilent: {args.silent}")

    app = QtWidgets.QApplication()
    window = MainWindow(port=args.port, current=args.current, voltage=args.voltage, silent=args.silent)
    window.show()
    app.exec()

