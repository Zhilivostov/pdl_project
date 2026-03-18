"""Окно простого просмотра данных ПДА.

`SimpleViewClientWindow` принимает 2D‑массив с помощью метода
`data_received` и отображает:
- тепловую карту интенсивностей;
- срез по выбранному АЦП;
- спектр и профиль с аппроксимацией.
"""
import sys

from PyQt5.QtCore import Qt
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


import numpy as np

from scipy.fft import fft, fftfreq
from scipy.optimize import curve_fit


class SimpleViewClientWindow(QDialog):
    # This "window" is a QWidget. If it has no parent,
    # it will appear as a free-floating window.

    def __init__(self, parent=None):
        super(SimpleViewClientWindow, self).__init__(parent)
        self.setWindowTitle("PDA_app_plots")

        self.data = np.array([])

        mainLayout = QGridLayout()

        gr_wid = pg.GraphicsLayoutWidget(show=True)

        p1 = gr_wid.addPlot()
        self.colorMap = pg.ImageItem()
        p1.addItem( self.colorMap )
        # p1.addColorBar( self.colorMap, colorMap='CET-L9', values=(0, 2729) ) # , interactive=False)
        # p1.addColorBar( self.colorMap, orientation = 'h', colorMap='plasma', values=(0, 2729) ) # , interactive=False)

        cmap = pg.colormap.get('plasma')
        self.bar = pg.ColorBarItem(
            values = (0, 2**11),
            limits = (0, 2**11), # start with full range...
            # interactive = False,
            # rounding=10,
            # width = 10,
            colorMap=cmap )
        # bar.setLevels(0, 3000)
        self.bar.setImageItem( self.colorMap )
        # bar.getAxis('bottom').setHeight(21)
        # bar.getAxis('top').setHeight(31)

        # p1.setMouseEnabled( x=True, y=False)
        self.bar.disableAutoRange()
        # p1.hideButtons()
        # p1.setRange(xRange=(0,100), yRange=(0,100), padding=0)
        p1.showAxes(True, showValues=(True,False,False,True) )

        self.plot_oneADC = pg.PlotWidget(name='ADC')
        self.plot_oneADC.setLabel('left', 'ADC values')
        self.plot_fft = pg.PlotWidget(name='fft plot')
        self.plot_fft.setLabel('left', 'FFT')
        self.plot_profile = pg.PlotWidget(name='avg profile')
        self.plot_profile.setLabel('left', 'Profile')

        # plot_item1 = gr_wid.getPlotItem()
        # plot_item2 = self.plot_oscil.getPlotItem()
        self.plot_oneADC.getPlotItem().setXLink(p1)

        self.plot_profile.getPlotItem().setYLink(p1)

        self.curve_oneADC = self.plot_oneADC.plot(np.array([]), np.array([]))
        self.curve_fft = self.plot_fft.plot(np.array([]), np.array([]))

        self.curve_profile = self.plot_profile.plot(np.array([]), np.array([]),
                            pen=None, symbol='o')
        self.curve_fit = self.plot_profile.plot(np.array([]), np.array([]))
        # self.curve_ADC_line = self.plot_profile.plot(np.array([]), np.array([]))
        self.curve_ADC_line_1 = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('r', width=1))
        self.curve_ADC_line_2 = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen('w', width=1))
        self.plot_profile.addItem(self.curve_ADC_line_1)
        p1.addItem(self.curve_ADC_line_2)

        self.curve_profile.getViewBox().invertX(True)


        ADC_numb_label = QLabel("ADC number:")
        self.ADC_numb = QSpinBox()
        self.ADC_numb.setRange(0, 15)
        self.ADC_numb.setSingleStep(1)
        self.ADC_numb.setKeyboardTracking(False)

        self.ADC_numb.valueChanged.connect(self.set_turn_data)

        turn_numb_label = QLabel("turn number:")
        self.turn_numb = QSpinBox()
        self.turn_numb.setRange(0, 2729)
        self.turn_numb.setSingleStep(1)
        self.turn_numb.setKeyboardTracking(False)
        self.turn_numb.setEnabled(False)

        self.turn_numb.valueChanged.connect(self.set_profile_data)

        self.avg_profile_RB = QRadioButton("average profile")
        self.single_turn_RB = QRadioButton("single turn profile")
        self.avg_profile_RB.setChecked(True)

        self.single_turn_RB.toggled.connect(self.turn_numb.setEnabled)
        self.single_turn_RB.toggled.connect(self.set_profile_data)

        self.mu_label = QLabel("mu:")
        self.sigma_label = QLabel("sigma:")
        self.mu = 0
        self.sigma = 0

        self.auto_lvl_CB = QCheckBox("Auto exposure")
        self.auto_lvl = 1
        self.auto_lvl_CB.setCheckState(self.auto_lvl)
        self.auto_lvl_CB.setTristate(False)

        # self.auto_lvl_CB.valueChanged.connect(lambda x: self.auto_lvl = x)
        self.auto_lvl_CB.stateChanged.connect(self.set_auto_exp)



        m, n = 10, 4
        f, g = 32, 8
        k = 0
        mainLayout.addWidget(gr_wid, k, 0, 1, 10)
        mainLayout.setRowStretch(k, m)
        mainLayout.addWidget(self.plot_profile, k, 11, 1, 2)
        mainLayout.setColumnStretch(0, f)
        mainLayout.setColumnStretch(11, g)
        mainLayout.setColumnStretch(12, 3)

        k+=1
        mainLayout.addWidget(self.plot_oneADC, k, 0, 1, 10)
        mainLayout.setRowStretch(k, n)

        vl = QVBoxLayout()
        vl.addWidget(self.auto_lvl_CB)
        hl = QHBoxLayout()
        hl.addWidget(turn_numb_label)
        hl.addWidget(self.turn_numb)
        vl.addLayout(hl)
        vl.addWidget(self.avg_profile_RB)
        vl.addWidget(self.single_turn_RB)

        vl2 = QVBoxLayout()
        vl2.addWidget(self.mu_label)
        vl2.addWidget(self.sigma_label)
        vl.addLayout(vl2)

        hl = QHBoxLayout()
        ADC_numb_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.ADC_numb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        hl.addWidget(ADC_numb_label, alignment=Qt.AlignTop | Qt.AlignLeft)
        hl.addWidget(self.ADC_numb, alignment=Qt.AlignTop | Qt.AlignLeft)
        vl.addLayout(hl)

        mainLayout.addLayout(vl, k, 11, 2, 1)

        gr_wid2 = pg.GraphicsLayoutWidget(show=True)
        gr_wid2.addItem(self.bar, 0, 2)

        mainLayout.addWidget(gr_wid2, k, 12, 2, 1)

        k+=1
        mainLayout.addWidget(self.plot_fft, k, 0, 1, 10)
        mainLayout.setRowStretch(k, n)

        # mainLayout.setRowStretch(0, 10)
        # mainLayout.setRowStretch(1, 1)
        # mainLayout.setColumnStretch(2, 1)

        self.setLayout(mainLayout)

        self.ADC = np.arange(0, 16)

    def set_auto_exp(self, val):
        self.auto_lvl = val
        self.colorMap.setLevels(low = 0, high = 2**11)

    def data_received(self, data):
        self.data = data
        self.set_color_data()
        self.set_turn_data()
        self.set_profile_data()


    def set_color_data(self):
        self.colorMap.setImage(self.data, autoRange=False, autoLevels = self.auto_lvl)

    def set_turn_data(self):
        turns = np.arange(0, self.data.shape[0])
        tr_data = np.transpose(self.data)

        i = self.ADC_numb.value()
        self.curve_oneADC.setData([], [])
        self.curve_oneADC.setData(turns, tr_data[i])

        x, y = self.fft_func(tr_data[i])
        self.curve_fft.setData([],[])
        self.curve_fft.setData(x, y)

    def set_profile_data(self):
        self.curve_profile.setData([],[])

        if self.single_turn_RB.isChecked():
            j = self.turn_numb.value()
            profile = self.data[j]

        elif self.avg_profile_RB.isChecked():
            profile = np.mean(self.data, axis = 0)

        x_fit, y_fit, mu, sigma = self.calc_turn(profile)
        self.curve_fit.setData(y_fit, x_fit)
        # self.curve_fit.setData(x_fit, y_fit)
        self.mu_label.setText("mu: %.3f" % mu)
        self.sigma_label.setText("sigma: %.3f" % sigma)

        # self.curve_profile.setData(self.ADC, profile)
        self.curve_profile.setData(profile, self.ADC)

        # a, b = self.plot_profile.viewRange()
        # a, b = 0, 200
        # print("a,b", a[0], b[0])
        # input()
        # exit()
        i = self.ADC_numb.value()

        # self.curve_ADC_line.setData([a[0], b[1]], [i, i])
        self.curve_ADC_line_1.setPos(i)
        self.curve_ADC_line_2.setPos(i)
        # self.curve_ADC_line.setData([0, 600], [5, 5])
        # self.curve_ADC_line.setData([5, 5], [0, 600])


    def fft_func(self, y):
        # print("y", y)
        # print("shape", y.shape)
        N = len(y)
        # sample spacing
        T = 1.0 / 1.0
        x = np.linspace(0.0, N*T, N, endpoint=False)
        yf = fft(y)
        xf = fftfreq(N, T)[:N//2]
        spect = np.abs(yf[0:N//2])
        return xf, spect

    def fit_func(self, x, mu, sigma, A, B):
        return A * np.exp(- (x-mu)**2 / (2 * sigma**2)) + B

    def calc_turn(self, turn):
        B0 = min(turn)
        A0 = max(turn) - min(turn)
        x = np.arange(0, len(turn))
        # mu0 = stats.moment(turn, moment = 1)
        mu0 = np.sum(x*(turn-B0)) / np.sum(turn)
        # sigma0 = stats.moment(turn, moment = 2)
        sigma0 = (np.sum((turn-B0) * (x-mu0)**2) / np.sum(turn-B0))**.5
        p0 = [mu0, sigma0, A0, B0]
        # print("test1", mu0)
        # print("test2", sigma0)
        popt, pcov = curve_fit(self.fit_func, x, turn, p0 = p0)

        x_fit = np.arange(0, len(turn), 0.1)
        y_fit = self.fit_func(x_fit, *popt)
        # return popt[0], popt[1]
        return x_fit, y_fit, popt[0], popt[1]



if __name__ == '__main__':
    app = QApplication(sys.argv)
    viewClient = SimpleViewClientWindow()
    viewClient.show()
    sys.exit(app.exec())


