import sys
import socket
from PyQt5.QtCore import QObject, QTimer
from PyQt5.QtWidgets import QApplication
from PyQt5.QtNetwork import QUdpSocket

# CMD_ID = { 0x03 : "start_meas",
#            0x05 : "stop_meas",
#            0x0d : "read_data",
#            0x0c : "rw_reg",
#            0x00 : "write_reg",
#            0x00 : "write_reg",
#            0x04 : "read_reg"
#             }


# ANSW_ID = { 0x10 : "ACK",
#             0x11 : "CONF",
#             0xf4 : "REG",
#             0xfd : "DATA"
#             }
ACK_GOOD = b'\x0f'
STOP_COMMAND = b'\x05\x00\x00\x00\x00\x00'
START_COMMAND = b'\x03\x00\x00\x00\x00\x00'
WRITE_REGISTERS_COMMAND = b'\x00\x00\x00\x00\x00\x00' #пока только для 00 регистра
READ_REGISTERS_COMMAND = b'\x04\x00\x00\x00\x00\x00' #пока только для 00 регистра
# LIST_REGISTERS = { 

# }

class Server(QObject):
    def __init__(self):
        super().__init__()

        self.initSocket()
        #self.stop_work()
        #self.start_work()
        #self.write_register()


        # Повторный вызов send_msg каждые 5 с (цикл событий Qt)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        ##self.timer.timeout.connect(self.send_msg)
        self.timer.timeout.connect(self.stop_work)
        self.timer.timeout.connect(self.read_register)
        self.timer.start()

    def initSocket(self):
        #self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        #self.my_socket.connect(('172.16.1.166',  2195))
        self.my_socket = QUdpSocket()
        self.my_socket.connectToHost('172.16.1.166',  2195)
        
        # self.my_socket.send(b'\x04\x09\x00\x00\x00\x00')
        #self.send_msg()
        
    def _recv_udp(self, bufsize):
        self.my_socket.waitForReadyRead(-1)
        data, host, port = self.my_socket.readDatagram(4096)
        address = (host.toString(), port)
        return data, address 

    #def send_msg(self):
    #    print("Package sent")
    #    self.my_socket.send(b'\x04\x09\x00\x00\x00\x00')
     #   data, address = self.my_socket.recvfrom(4096)  # 4096 - размер буфера \ можно сделать кастомную функцию, в которую встроен таймер ожидания ответа(для QT через timer)
        #if self.check_ack(data):
        #    print("ACK received")
        #else:
        #    print("NACK received")
      #  print(f"Получено {len(data)} байт от {address}")
        #print(f"Сообщение: {data}")
       # self.print_raw_bytes(data)

    def write_registers(self):
        pass

    def stop_work(self):
        self.my_socket.write(STOP_COMMAND)
        data, address = self._recv_udp(4096) 
        self.check_ack(data)
        print("Work stopped")
            
    def start_work(self):
        self.my_socket.write(START_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        print("Work started")
        
        #пока ждём до конца(либо отправит правильный ответ конф, либо не отправит его вообще, поэтому проверка на соответствие не нужно, максимум таймер для исключения "несрабатывания")
        data, address = self._recv_udp(4096)
        self.print_raw_bytes(data)
        #self.check_ack(data)
        print("Work ended")

    def read_data(self):
        pass
        
    def read_register(self):
        self.my_socket.write(READ_REGISTERS_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        
        data, address = self._recv_udp(4096)
        self.print_raw_bytes(data)
        print("Register was read")
        
    def write_register(self):
        self.my_socket.write(WRITE_REGISTERS_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        print("Register was written")
        
    
    def read_registers(self):
        pass

    def print_raw_bytes(self, data):
        # print(f"Сообщение: {''.join(f'\\x{b:02x}' for b in data)}")
        print(''.join(f'\\x{b:02x}' for b in data)) #потому что на диспетчерской стоит 3.11.2(лучше без ф-строк)
        #print(''.join("\\x{%s:02x}" % b for b in data))

    def check_ack(self, data):
        if data[-1:] == ACK_GOOD:
            print("ACK received")
            self.print_raw_bytes(data)
        else:
            print("NACK received")

    

if __name__ == '__main__':
    app = QApplication(sys.argv)
    s = Server()


    sys.exit(app.exec_())
