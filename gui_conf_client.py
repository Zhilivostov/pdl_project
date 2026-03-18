"""Графический интерфейс для настройки параметров ПДА.

`ConfClientWindow` отображает пользовательские параметры и реальные
параметры ПДА, синхронизирует изменения через сигналы с
`Current_conf` и протокольным сервером.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
                QApplication,
                QCheckBox,
                QComboBox,
                QDateTimeEdit,
                QDial,
                QDialog,
                QGridLayout,
                QGroupBox,
                QHBoxLayout,
                QLabel,
                QLineEdit,
                QProgressBar,
                QPushButton,
                QRadioButton,
                QScrollBar,
                QSizePolicy,
                QSlider,
                QSpinBox,
                QStyleFactory,
                QTableWidget,
                QTabWidget,
                QTextEdit,
                QVBoxLayout,
                QWidget,
                QDoubleSpinBox,
                QMainWindow
                )

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui


# from my_led import LedIndicator

import sys
import numpy as np

PRMS = {"Turns number"    : [0, 2729, 1],    # 0x02 and 0x01 registers values together / 12
        "Separatrix"      : [0, 13, 1],      # 0x06 : val = (255 - reg value)
        "Fine delay (ns)" : [0, 10.23, 0.1], # 0x08 : 1 unit = 10 ps = 0.01 ns
        "Fronts overlay"  : [0, 15, 1],      # 0x04 : val ? - it depends
        "ADC delay"       : [10, 10, 1],     # 0x09 : value should be 10 (0x0a) for correct ADC data writing
        "Trigger"         : [0, 1, 1],       # 0x00, 15th bit (0 - internal, 1 - external)
        "Gain"            : [0, 1, 1]        # 0x00, 0th bit
        }

class ConfClientWindow(QDialog): #initial version

    prms_changed = pyqtSignal(dict)

    def __init__(self, parent=None): #initial version
    # def __init__(self):
        super(ConfClientWindow, self).__init__(parent) #initial version
        # super().__init__() #initial version
        self.setWindowTitle("PDA Configuration utility")

        # Немного косметики для стиля приложения
        QApplication.setStyle(QStyleFactory.create("QtCurve"))

        self.prms = PRMS

        self.createUserPrmsGB()
        self.createPdaPrmsGB()

        mainLayout = QGridLayout()

        mainLayout.addWidget(self.userPrmsGB, 0, 0)

        mainLayout.addWidget(self.pdaPrmsGB, 0, 2)

        self.setLayout(mainLayout)


    def prm_updated(self):
        # print("gui_conf: updated")
        for i in self.userPrmsItems.keys():
            self.prms[i] = self.userPrmsItems[i][1].value()
        self.prms_changed.emit(self.prms)

    def createUserPrmsGB(self):
        self.userPrmsGB = QGroupBox("User parameters:")

        self.userPrmsItems = {}

        layout_V = QVBoxLayout()

        for i in self.prms.keys():
            layout_H = QHBoxLayout()

            val = np.array(self.prms[i], dtype = float)
            # print("test", val)
            label = QLabel(i)
            spinbox = QDoubleSpinBox()
            spinbox.setRange(val[0], val[1])
            spinbox.setSingleStep(val[2])
            spinbox.setKeyboardTracking(False)
            self.userPrmsItems[i] = [label, spinbox]

            spinbox.valueChanged.connect(self.prm_updated)
            # self.userPrmsItems[i][1].valueChanged.connect(self.prm_updated)


            layout_H.addWidget(self.userPrmsItems[i][0])
            layout_H.addWidget(self.userPrmsItems[i][1])

            layout_V.addLayout(layout_H)

        self.userPrmsGB.setLayout(layout_V)

    def createPdaPrmsGB(self):
        self.pdaPrmsGB = QGroupBox("PDA parameters:")

        self.pdaPrmsItems = {}

        layout_V = QVBoxLayout()

        for i in self.prms.keys():
            layout_H = QHBoxLayout()

            val = np.array(self.prms[i], dtype = float)
            # print("test", val)
            label = QLabel(i)
            spinbox = QDoubleSpinBox()
            spinbox.setRange(val[0], val[1])
            spinbox.setSingleStep(val[2])
            spinbox.setKeyboardTracking(False)
            self.pdaPrmsItems[i] = [label, spinbox]



            layout_H.addWidget(self.pdaPrmsItems[i][0])
            layout_H.addWidget(self.pdaPrmsItems[i][1])

            layout_V.addLayout(layout_H)

        self.pdaPrmsGB.setLayout(layout_V)

    def PDA_prms_changed(self, prms):
        # print("client: PDA changed", prms)
        for i in prms.keys():
            val = prms[i]
            if val != None:
                self.pdaPrmsItems[i][1].setValue(val)

    def initiate_prms(self, prms_dict):
        for i in self.prms.keys():
            self.userPrmsItems[i][1].setValue(prms_dict[i])



if __name__ == '__main__':
    app = QApplication(sys.argv)
    confClient = ConfClientWindow()
    confClient.show()
    sys.exit(app.exec())







