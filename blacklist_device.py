import sys
from PyQt6.QtCore import QObject, QTimer, QFile, QTextStream
from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QUdpSocket

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
READ_DATA_COMMAND = b'\x0D\x00\x00\x00\x00\x00' #только 0 страницу
READ_ALL_DATA_COMMAND = b'\x0D\x00\x00\x00\x00\x3F' #все страницы с 0 по 63(3F)

# LIST_REGISTERS = { 

# }

class Server(QObject):
    def __init__(self):
        super().__init__()

        self.initSocket()
        self.work_loop()
        #self.stop_work()
        #self.start_work()
        #self.write_register()


        # Повторный вызов send_msg каждые 5 с (цикл событий Qt)
        # self.timer = QTimer(self)
        # self.timer.setInterval(5000)
        # ##self.timer.timeout.connect(self.send_msg)
        # self.timer.timeout.connect(self.stop_work)
        # self.timer.timeout.connect(self.read_register)
        # self.timer.start()

    def initSocket(self):
        self.device_socket = QUdpSocket()
        self.device_socket.connectToHost('172.16.1.166',  2195)
        
        
    def _recv_udp(self, bufsize):
        self.device_socket.waitForReadyRead(-1)
        data, host, port = self.device_socket.readDatagram(4096)
        address = (host.toString(), port)
        return data, address 

    def work_loop(self):
        self.stop_work()
        self.start_work()
        self.read_data()

    def readPendingDatagrams(self):
        """Вызывается автоматически при получении пакета"""
        # Обрабатываем все ожидающие дейтаграммы, чтобы ничего не потерять
        while self.udpSocket.hasPendingDatagrams():
            # Рекомендуется использовать receiveDatagram, он содержит адрес отправителя
            datagram = self.udpSocket.receiveDatagram()
            data = datagram.data()  # Извлекаем данные (QByteArray)
            sender_ip = datagram.senderAddress().toString()
            sender_port = datagram.senderPort()

            # Декодируем данные в строку (предполагаем, что приходит текст)
            # Для бинарных данных можно писать напрямую data
            text = data.data().decode('utf-8', errors='ignore')
            
            # Форматируем строку для записи: например "[IP:Port] данные"
            line = f"[{sender_ip}:{sender_port}] {text}\n"
            self.stream << line
            self.stream.flush()  # Немедленно сохраняем на диск
            
            # Выводим в консоль
            print(f"Получено от {sender_ip}:{sender_port}: {text}")

        self.file.close() #закрытие файла
        print("File closed")


    def read_data(self):
        self.device_socket.write(READ_DATA_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        #Подключаем сигнал: при получении данных вызывается функция
        self.udpSocket.readyRead.connect(self.readPendingDatagrams)

        self.file = QFile("received_data.txt")
        if not self.file.open(QFile.OpenModeFlag.WriteOnly | QFile.OpenModeFlag.Append | QFile.OpenModeFlag.Text):
            print("Не удалось открыть файл для записи")
            return
        
        self.stream = QTextStream(self.file)
        #self.stream.setEncoding(QStringConverter.Encoding.Utf8) # Устанавливаем кодировку UTF-8
        print("Слушаем порт, данные будут записаны в received_data.txt...")

        # #после этого ловим данные от прибора и накапливаем в buffer_data
        # self.buffer_data.clear()
        # self.receive_udp_data_to_buffer()
        # #после завершения чтения полностью разбираем накопленный buffer_data
        # self.receive_and_sort_udp_raw()
        # self.write_processed_adc_to_file()
        # self.broadcast_adc_channels_to_clients()

    # def closeEvent(self):
    #     """Закрываем ресурсы"""
    #     self.file.close()
    #     print("File closed")

    def write_registers(self):
        pass

    def stop_work(self):
        print("Stop work sent")
        self.device_socket.write(STOP_COMMAND)
        data, address = self._recv_udp(4096) 
        self.check_ack(data)
        print("Work stopped")
            
    def start_work(self):
        self.device_socket.write(START_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        print("Work started")
        
        #пока ждём до конца(либо отправит правильный ответ конф, либо не отправит его вообще, поэтому проверка на соответствие не нужно, максимум таймер для исключения "несрабатывания")
        data, address = self._recv_udp(4096)
        self.print_raw_bytes(data)
        print("Work ended")

    def read_register(self):
        self.device_socket.write(READ_REGISTERS_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        
        data, address = self._recv_udp(4096)
        self.print_raw_bytes(data)
        print("Register was read")
        
    def write_register(self):
        self.device_socket.write(WRITE_REGISTERS_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        print("Register was written")
        
    
    def read_registers(self):
        pass

    def print_raw_bytes(self, data):
        print(''.join(f'\\x{b:02x}' for b in data)) #потому что на диспетчерской стоит 3.11.2(лучше без ф-строк)
        

    def check_ack(self, data):
        if data[-1:] == ACK_GOOD:
            print("ACK received")
            self.print_raw_bytes(data)
        else:
            print("NACK received")
            self.print_raw_bytes(data)

    

if __name__ == '__main__':
    app = QApplication(sys.argv)
    s = Server()


    #sys.exit(app.exec_())
    sys.exit(app.exec())