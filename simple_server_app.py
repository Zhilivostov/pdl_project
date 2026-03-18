import sys
import socket
import time
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QApplication

class Server(QObject):
    def __init__(self):
        super().__init__()
        self.addr =  ('172.16.1.166',  2195)
        self.mes =b'123'
        self.initSocket()

    def initSocket():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        #addr = ('172.16.1.166',  2195)
        try:
            #mes ="123"
            print(f"mes")
            sock.sendto(self.mes, self.addr)
            try:
                data, server = sock.recvfrom(1024)
                print(f"Получено {len(data)} байт от {address}")
            except socket.timeout:
                print(f"no answ")
        except:
            pass


if __name__ == '__main__':
    app = QApplication(sys.argv)
    s = Server()


    sys.exit(app.exec_())
