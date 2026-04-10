# import socket
#import struct
# from threading import Thread
#import time
#from datetime import datetime
from PyQt6 import QtCore
from PyQt6.QtCore import QObject, pyqtSignal, QByteArray, QTimer
from PyQt6.QtNetwork import QUdpSocket, QHostAddress

import traceback
import str_byte_conv

from PyQt6.QtWidgets import QApplication

import sys

UDP_IP_glob = "172.16.1.166"
UDP_PORT_glob = 2195

class Network(QObject):
    """   """
    msg_received = pyqtSignal(bytes)
    connected = pyqtSignal(bool)
    disconnected = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(Network, self).__init__(parent)
        self.UDP_IP = UDP_IP_glob
        self.UDP_PORT = UDP_PORT_glob
        self.sock = QUdpSocket()
        ttt = self.sock.bind(QHostAddress(0), 0)
        print("ttt", ttt)
        self.sock.readyRead.connect(self.receiver)
        # self.sock.readyRead.connect(lambda x: print("dododod"))

    def connect(self, UDP_IP = UDP_IP_glob, UDP_PORT = UDP_PORT_glob):
        try:

            self.connected.emit(True)
            print("Network: connected")

        except Exception:
            traceback.print_exc()
            print("ERROR: connection failed")

    def disconnect(self):
        try:
            self.sock.close()
            self.disconnected.emit(False)
            print("Network: disconnected")
        except Exception:
            traceback.print_exc()
            print("ERROR: socket isn't connected")

    def send_message(self, message):
        datagram = QByteArray(message)
        bytes_written = self.sock.writeDatagram(datagram, QHostAddress(self.UDP_IP), self.UDP_PORT)

        if bytes_written == -1:
            print(f"Failed to send datagram: {self.sock.errorString()}")
        else:
            print("network: sent message", str_byte_conv.bytes_to_str(message))

        # print(self.sock.hasPendingDatagrams(), self.sock.pendingDatagramSize() )

        # print("network: receive data", self.sock.receiveDatagram().data())

    def send(self):
        self.send_message(b'\x0d\x00\x00\x00\x00\x01')


    def receiver(self):
        # print("go")
        while self.sock.hasPendingDatagrams():
            datagram = self.sock.receiveDatagram()
            bytes_data = datagram.data().data()
            print("network: receive data", str_byte_conv.bytes_to_str(bytes_data))
            # print("network: receive data", datagram)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    net = Network()
    net.connect()

    def send():
        net.send_message(b'\x0d\x00\x00\x00\x00\x01')

    timer = QTimer()
    timer.start(1000)
    timer.timeout.connect(send)

    sys.exit(app.exec())


