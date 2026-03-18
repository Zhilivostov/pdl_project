import sys
import socket
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QApplication

class Server(QObject):
    def __init__(self):
        super().__init__()

        self.initSocket()
        #self.receiveSocket()

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.start(1000)
        self.timer.timeout.connect(self.send_msg)

    def initSocket(self):
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.my_socket.connect(('172.16.1.166',  2195))
        # #my_socket.send(b'\x04\x00\x00\x00\x00\x00')
        # #self.my_socket.send(b'\x04\x09\x00\x00\x00\x00')
        self.send_msg()

        # #data, address = self.my_socket.recvfrom(4096)  # 4096 - размер буфера

        # #print(f"Получено {len(data)} байт от {address}")
        #print(f"Сообщение: {data.decode('utf-8')}")
        # #print(f"Сообщение: {data}")

        self.my_socket.send(b'ls')
        data, address = self.my_socket.recvfrom(4096)  # 4096 - размер буфера

        print(f"Получено {len(data)} байт от {address}")
        #print(f"Сообщение: {data.decode('utf-8')}")
        print(f"Сообщение: {data}")

        data, address = self.my_socket.recvfrom(4096)  # 4096 - размер буфера

        print(f"Получено {len(data)} байт от {address}")
        #print(f"Сообщение: {data.decode('utf-8')}")
        print(f"Сообщение: {data}")

    #def receiveSocket()

    def send_msg(self):
        print("I sent")
        self.my_socket.send(b'\x04\x09\x00\x00\x00\x00')

        # #data, address = self.my_socket.recvfrom(4096)  # 4096 - размер буфера

        # #print(f"Получено {len(data)} байт от {address}")
        # #print(f"Сообщение 1: {data}")

        data, address = self.my_socket.recvfrom(4096)  # 4096 - размер буфера
        print(f"Получено {len(data)} байт от {address}")
        print(f"Сообщение: {data}")





if __name__ == '__main__':
    app = QApplication(sys.argv)
    s = Server()


    sys.exit(app.exec_())
