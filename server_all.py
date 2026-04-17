import os
import sys
import time
import json
import struct
import numpy as np

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress, QUdpSocket
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QTextEdit

from configurator import Current_conf


class TcpServerWindow(QMainWindow):
    """
    Окно TCP-сервера.

    Сервер выполняет две параллельные задачи:
    1) В таймерном цикле генерирует числовые данные и отправляет их всем клиентам.
    2) Принимает от клиентов команды обновления конфигурации (строки формата CONF <json>).

    Благодаря использованию Qt-сигналов и сокетов всё работает в одном GUI-потоке
    без ручного создания потоков.
    """

    def __init__(self, host='127.0.0.1', port=8888):
        super().__init__()
        # Адрес и порт, на которых сервер слушает входящие подключения.
        self.host = host
        self.port = port

        #Адрес и порт, на котором сервер общается с прибором
        self.host_device = '172.16.1.166'
        self.port_device = 2195

        #Значения регистров для общения с прибором
        self.ACK_GOOD = b'\x0f'
        self.STOP_COMMAND = b'\x05\x00\x00\x00\x00\x00'
        self.START_COMMAND = b'\x03\x00\x00\x00\x00\x00'
        self.WRITE_REGISTERS_COMMAND = b'\x00\x00\x00\x00\x00\x00' #пока только для 00 регистра
        self.READ_REGISTERS_COMMAND = b'\x04\x00\x00\x00\x00\x00' #пока только для 00 регистра
        self.READ_DATA_COMMAND = b'\x0D\x00\x00\x00\x00\x00'
        # Порядок соответствия битов каналам АЦП (как в pages_conv.py).
        self.D = [12, 13, 14, 15, 8, 9, 10, 11, 4, 5, 6, 7, 0, 1, 2, 3]
        # 16 отдельных массивов для хранения результатов по каждому каналу.
        self.adc_channels = [[] for _ in range(16)]

        self.start_register_values = {
            '00': b'\x00\x00\x00\x00\x00\x00',
            '01': b'\x00\x01\x79\x20\x00\x00',
            '02': b'\x00\x02\x00\x00\x00\x00',
            '04': b'\x00\x04\x00\x00\x00\x00',
            '06': b'\x00\x06\x00\xff\x00\x00',
            '08': b'\x00\x08\x00\x00\x00\x00',
            '09': b'\x00\x09\x00\x0a\x00\x00',
        }


        # Множество активных клиентских сокетов.
        self.clients = set()
        # Словарь "сокет -> номер клиента" для читаемых логов.
        self.client_ids = {}
        # Счётчик следующего клиентского ID (монотонно растёт).
        self.next_client_id = 1
        # Буферы приёма для каждого клиента (нужны для "обрезанных" TCP-строк).
        self._read_buffers = {}
        # Буфер сырых данных, собранных из UDP-пакетов прибора.
        self.buffer_data = bytearray()

        # Локальная конфигурация ПДА на стороне сервера
        # (загружается из configuration_of_prms.json через configurator.py).
        self.conf = Current_conf()
        self.conf.init_config()

        # Пошаговая инициализация UI, сети и главного цикла.
        self._init_ui()
        self._init_server()
        self._init_device()
        self._init_main_loop()


    def _init_device(self):
        self.my_socket = QUdpSocket()
        self.log("Соединение с прибором")
        self.my_socket.connectToHost(self.host_device,  self.port_device)
        

    def _init_ui(self):
        """Создаёт простое окно: статус сервера + окно логов."""
        self.setWindowTitle("TCP сервер")
        self.setGeometry(100, 100, 480, 300)

        central = QWidget(self)
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        self.status_label = QLabel("Инициализация сервера...", self)
        self.status_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.status_label)

        self.log_widget = QTextEdit(self)
        self.log_widget.setReadOnly(True)
        self.log_widget.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        layout.addWidget(self.log_widget)

    def log(self, message: str) -> None:
        """
        Добавляет строку в окно логов сервера.

        Каждый лог снабжается временем, чтобы удобно отслеживать порядок событий.
        """
        timestamp = time.strftime("%H:%M:%S")
        self.log_widget.append(f"[{timestamp}] {message}")
        # Во время блокирующих UDP-операций принудительно обновляем UI,
        # чтобы лог сразу появлялся в окне приложения.
        app = QApplication.instance()
        if app is not None:
            app.processEvents()

    def _init_server(self):
        """
        Создаёт QTcpServer и запускает прослушивание порта.

        После вызова listen() Qt начнёт генерировать сигнал newConnection
        при каждом новом клиенте.
        """
        self.tcp_server = QTcpServer(self)
        self.tcp_server.newConnection.connect(self.on_new_connection)

        if not self.tcp_server.listen(QHostAddress(self.host), self.port):
            self.status_label.setText(
                f"Ошибка запуска сервера: {self.tcp_server.errorString()}"
            )
            self.log(f"Ошибка запуска сервера: {self.tcp_server.errorString()}")
        else:
            addr = self.tcp_server.serverAddress().toString()
            port = self.tcp_server.serverPort()
            self.status_label.setText(
                f"Сервер запущен на {addr}:{port}\nОжидание клиентов..."
            )
            self.log(f"Сервер запущен на {addr}:{port}")

    def _init_main_loop(self): #добавить сюда запуск общения с прибором
        """
        Запускает основной периодический цикл генерации данных.

        Используется QTimer с шагом 50 мс (20 Гц).
        """
        # основной цикл сервера: генерирует данные и рассылает их клиентам
        self.timer = QTimer(self)
        #self.timer.timeout.connect(self.main_loop_iteration)
        self.timer.timeout.connect(self.main_loop_iteration)
        #self.timer.start(50)  # период 50 мс (20 Гц)
        self.timer.start(5000)
        #self.log("Основной цикл сервера запущен (50 мс шаг)")
        self.log("Основной цикл сервера запущен (5000 мс шаг)")
        self.log("Конфигурация загружена на сервере и хранится в памяти")

    def _recv_udp(self, bufsize): #это для ожидания ответа от прибора(потом возможно от этого можно будет избавиться)
        self.my_socket.waitForReadyRead(-1)
        data, host, port = self.my_socket.readDatagram(bufsize)
        address = (host.toString(), port)
        return data, address

    def reset_adc_channels(self):
        """Очищает накопленные данные по всем 16 каналам."""
        self.adc_channels = [[] for _ in range(16)]

    def parse_one_turn(self, byte_mess):
        """
        Разбирает один "оборот" данных (24 байта) в 16 значений каналов.

        Логика полностью соответствует pages_conv.py:
        - берём 12 слов по 16 бит;
        - по маске D раскладываем биты в правильный порядок каналов;
        - вычитаем 2048 для перевода в знаковый диапазон.
        """
        if len(byte_mess) != 24:
            return None

        adc_val_arr = np.zeros(16, dtype=int)
        k = 0
        bit = 0
        while k < 24:
            one_bit = struct.unpack('>H', byte_mess[k:k + 2])[0]
            for i, val in enumerate(self.D):
                arr_val = (one_bit >> (15 - i)) & 1
                adc_val_arr[val] = adc_val_arr[val] | (arr_val << bit)
            k += 2
            bit += 1
        return adc_val_arr - 2048

    def parse_raw_udp_payload(self, payload):
        """
        Разбирает сырой UDP payload как набор оборотов по 24 байта.
        Возвращает список из 16 списков (по одному на канал).
        """
        channels = [[] for _ in range(16)]
        turns_count = len(payload) // 24
        if turns_count <= 0:
            return channels

        payload = payload[:turns_count * 24]
        for idx in range(turns_count):
            turn = payload[idx * 24:(idx + 1) * 24]
            parsed = self.parse_one_turn(turn)
            if parsed is None:
                continue
            for ch in range(16):
                channels[ch].append(int(parsed[ch]))
        return channels

    def receive_and_sort_udp_raw(self, bufsize=4096):
        """
        Парсит накопленные сырые данные из buffer_data и раскладывает
        значения по 16 каналам согласно маске D.

        Параметр bufsize оставлен для обратной совместимости и не используется.
        """
        parsed_channels = self.parse_raw_udp_payload(bytes(self.buffer_data))
        self.reset_adc_channels()
        appended = 0
        for ch in range(16):
            if parsed_channels[ch]:
                self.adc_channels[ch].extend(parsed_channels[ch])
                appended += len(parsed_channels[ch])
        self.log(f"buffer_data parsed: добавлено {appended} точек в 16 каналов")
        return self.adc_channels

    def write_processed_adc_to_file(self, filepath=None):
        """
        Записывает полностью обработанные данные (16 каналов из self.adc_channels)
        в текстовый файл: строка = один отсчёт, столбцы разделены запятой.
        """
        if filepath is None:
            base = os.path.dirname(os.path.abspath(__file__)) or os.getcwd()
            filepath = os.path.join(
                base,
                "adc_processed_{}.txt".format(time.strftime("%Y%m%d_%H%M%S")),
            )
        try:
            n = self._adc_rows_count()
            if n <= 0:
                self.log("Запись в файл: нет данных в adc_channels, файл не создан")
                return filepath
            with open(filepath, "w", encoding="utf-8", newline="") as f:
                f.write(",".join("ch{}".format(i) for i in range(16)) + "\n")
                for line in self._iter_adc_rows(n):
                    f.write(line + "\n")
            self.log("Обработанные данные записаны в файл: {} ({} строк данных)".format(filepath, n))
        except OSError as e:
            self.log("Ошибка записи обработанных данных в файл: {}".format(e))
        return filepath

    def write_adc_channels_arrays_to_file(self, filepath=None):
        """
        Записывает полученные массивы int по всем каналам в JSON-файл.
        Формат: {"ch0":[...], ..., "ch15":[...]}.
        """
        if filepath is None:
            base = os.path.dirname(os.path.abspath(__file__)) or os.getcwd()
            filepath = os.path.join(
                base,
                "adc_channels_arrays_{}.json".format(time.strftime("%Y%m%d_%H%M%S")),
            )
        try:
            n = self._adc_rows_count()
            if n <= 0:
                self.log("Запись массивов каналов: нет данных в adc_channels, файл не создан")
                return filepath

            data = {
                "ch{}".format(ch): [int(value) for value in self.adc_channels[ch]]
                for ch in range(16)
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.log("Массивы int по каналам записаны в файл: {}".format(filepath))
        except OSError as e:
            self.log("Ошибка записи массивов каналов в файл: {}".format(e))
        return filepath

    def broadcast_adc_channels_to_clients(self):
        """
        Отправляет всем TCP-клиентам обработанные данные прибора:
        каждая строка — один отсчёт, 16 значений через запятую (как в файле).
        """
        if not self.clients:
            self.log("Нет подключенных клиентов, данные не отправляются")
            return
        n = self._adc_rows_count()
        if n <= 0:
            self.log("Нет данных в adc_channels, данные не отправляются")
            return
        lines = list(self._iter_adc_rows(n))
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        for sock in list(self.clients):
            if sock.state() == QTcpSocket.ConnectedState:
                try:
                    sock.write(payload)
                except Exception:
                    if sock in self.clients:
                        client_id = self.client_ids.get(sock, "?")
                        self.clients.remove(sock)
                        self.client_ids.pop(sock, None)
                        self._read_buffers.pop(sock, None)
                        self.log(
                            "Ошибка при отправке данных прибора клиенту #{}, клиент удалён".format(
                                client_id
                            )
                        )

    def _adc_rows_count(self):
        """Возвращает число полностью готовых строк по всем 16 каналам."""
        lengths = [len(self.adc_channels[ch]) for ch in range(16)]
        if not lengths or max(lengths) == 0:
            return 0
        return min(lengths)

    def _iter_adc_rows(self, rows_count=None):
        """Генерирует строки вида 'ch0,...,ch15' для готовых отсчётов."""
        if rows_count is None:
            rows_count = self._adc_rows_count()
        for i in range(rows_count):
            yield ",".join(str(int(self.adc_channels[ch][i])) for ch in range(16))

    def receive_udp_data_to_buffer(self, packets_count=64, header_size=10, payload_size=1024):
        """
        Получает `packets_count` UDP-пакетов от прибора и накапливает полезные данные.

        Для каждого пакета:
        - удаляет шапку размером `header_size` байт из начала;
        - проверяет, что полезная часть имеет размер `payload_size` байт;
        - добавляет полезную часть в `self.buffer_data`.

        После получения последнего пакета пишет лог об окончании приёма.
        """
        received_packets = 0
        skipped_packets = 0
        while received_packets < packets_count:
            if not self.my_socket.hasPendingDatagrams():
                # Ждём новые данные от прибора; выходим при таймауте.
                if not self.my_socket.waitForReadyRead(2000):
                    self.log(
                        "Таймаут ожидания UDP данных: получено {} из {} пакетов".format(
                            received_packets, packets_count
                        )
                    )
                    break

            while self.my_socket.hasPendingDatagrams() and received_packets < packets_count:
                datagram_size = self.my_socket.pendingDatagramSize()
                data, _, _ = self.my_socket.readDatagram(datagram_size)

                if len(data) < header_size:
                    skipped_packets += 1
                    self.log(
                        "UDP пакет #{}: слишком короткий ({} байт), пакет пропущен".format(
                            received_packets + skipped_packets + 1, len(data)
                        )
                    )
                    continue

                clean_data = data[header_size:]
                if len(clean_data) != payload_size:
                    skipped_packets += 1
                    self.log(
                        "UDP пакет #{}: полезная нагрузка {} байт вместо {}, пакет пропущен".format(
                            received_packets + skipped_packets + 1,
                            len(clean_data),
                            payload_size,
                        )
                    )
                    continue

                self.buffer_data.extend(clean_data)
                received_packets += 1

        self.log(
            "Получение данных от прибора завершено: валидных пакетов {}/{}, пропущено {}, байт в buffer_data: {}".format(
                received_packets, packets_count, skipped_packets, len(self.buffer_data)
            )
        )

    def on_new_connection(self):
        """
        Обрабатывает все ожидающие подключения (их может быть несколько сразу).

        Для каждого клиента:
        - подписываемся на disconnected и readyRead;
        - выделяем уникальный ID;
        - создаём отдельный буфер входящих байтов.
        """
        last_client_id = None
        while self.tcp_server.hasPendingConnections():
            sock = self.tcp_server.nextPendingConnection()
            sock.disconnected.connect(self.on_client_disconnected)
            sock.readyRead.connect(self.on_client_ready_read)
            self.clients.add(sock)
            client_id = self.next_client_id
            self.client_ids[sock] = client_id
            self._read_buffers[sock] = b""
            self.next_client_id += 1
            last_client_id = client_id

        self.status_label.setText(
            f"Клиенты подключены: {len(self.clients)}"
        )
        if last_client_id is not None:
            self.log(
                f"Клиент #{last_client_id} подключился. Всего клиентов: {len(self.clients)}"
            )


    def print_raw_bytes(self, data): #перенести print в логи
        #print(''.join(f'\\x{b:02x}' for b in data)) #потому что на диспетчерской стоит 3.11.2(лучше без ф-строк)
        self.log(''.join(f'\\x{b:02x}' for b in data))

    def check_ack(self, data):
        if data[-1:] == self.ACK_GOOD:
            #print("ACK received") #перенести это в логи
            self.log("Device ACK received")
            self.print_raw_bytes(data)
        else:
            #print("NACK received") #перенести это в логи
            self.log("Device NACK received")

    def stop_work(self):
        self.my_socket.write(self.STOP_COMMAND)
        data, address = self._recv_udp(4096) 
        self.check_ack(data)
        #print("Work stopped") #перенести это в логи
        self.log("Device work stopped")

    def write_registers_value(self):
        for register_name, register_command in self.start_register_values.items():
            self.write_register(register_command)
            self.log("Регистр {} записан".format(register_name))

    def write_register(self, command = b'\x00\x00\x00\x00\x00\x00'):
        self.my_socket.write(command)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        #print("Device register was written") #перенести это в логи
        self.log("Device register was written")
        
    def read_register(self):
        self.my_socket.write(self.READ_REGISTERS_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        
        data, address = self._recv_udp(4096)
        self.print_raw_bytes(data)
        print("Register was read") #перенести это в логи

    def start_work(self):
        self.my_socket.write(self.START_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)
        print("Work started") #перенести это в логи
        
        #пока ждём до конца(либо отправит правильный ответ конф, либо не отправит его вообще, поэтому проверка на соответствие не нужно, максимум таймер для исключения "несрабатывания")
        data, address = self._recv_udp(4096)
        self.print_raw_bytes(data)
        print("Work ended") #перенести это в логи

    def on_client_disconnected(self):
        """
        Обработчик отключения клиента.

        Удаляет клиента из всех внутренних структур:
        - списка активных сокетов,
        - таблицы ID,
        - буфера входящих данных.
        """
        sock = self.sender()
        client_id = "?"
        if isinstance(sock, QTcpSocket) and sock in self.clients:
            client_id = self.client_ids.get(sock, "?")
            self.clients.remove(sock)
            self.client_ids.pop(sock, None)
            self._read_buffers.pop(sock, None)
        if self.clients:
            self.status_label.setText(
                f"Клиенты подключены: {len(self.clients)}"
            )
            self.log(
                f"Клиент #{client_id} отключился. Осталось клиентов: {len(self.clients)}"
            )
        else:
            self.status_label.setText(
                "Сервер запущен\nОжидание клиентов..."
            )
            self.log("Все клиенты отключены, ожидание новых подключений")

    def on_client_ready_read(self):
        """
        Принимает сообщения от клиента.

        TCP не гарантирует, что одна отправленная строка придёт одним куском,
        поэтому здесь используется накопительный буфер по каждому сокету:
        - добавляем новые байты в буфер;
        - делим по '\n';
        - последний фрагмент оставляем как "хвост" до следующего readyRead.

        Поддерживаемая команда:
        - CONF <json>  -> обновление конфигурации на сервере.
        """
        sock = self.sender()
        if not isinstance(sock, QTcpSocket):
            return

        buf = self._read_buffers.get(sock, b"") + bytes(sock.readAll())
        lines = buf.split(b"\n")
        self._read_buffers[sock] = lines.pop()  # неполная строка

        client_id = self.client_ids.get(sock, "?")

        for raw in lines:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            # Протокол: строки, начинающиеся с "CONF " содержат JSON с параметрами
            if line.startswith("CONF "):
                payload = line[5:]
                try:
                    prms = json.loads(payload)
                except Exception:
                    self.log(f"Клиент #{client_id}: ошибка разбора JSON конфигурации")
                    continue

                # Обновляем серверную конфигурацию
                self.conf.user_prms_changed(prms)
                self.log(f"Клиент #{client_id}: обновил конфигурацию {prms}")

    def main_loop(self):

        pass

    def device_loop_iteration(self):
        self.stop_work()
        self.write_registers_value()
        #self.read_register()
        self.start_work()
        self.read_data()
        

    def read_data(self):
        """
        Читает данные от прибора по UDP и накапливает их в buffer_data.
        Обработка пакетов выполняется методом receive_udp_data_to_buffer().
        """
        self.request_data_from_device()
        self.log("Этап collect: начинаем сбор UDP-пакетов в буфер")
        self.buffer_data.clear()
        self.receive_udp_data_to_buffer()
        self.process_buffer_data()

    def request_data_from_device(self):
        """Отправляет команду чтения данных прибору и проверяет ACK."""
        self.log("Этап request: отправляем команду чтения данных прибору")
        self.my_socket.write(self.READ_DATA_COMMAND)
        data, address = self._recv_udp(4096)
        self.check_ack(data)

    def process_buffer_data(self):
        """Разбирает буфер, сохраняет данные в файл и рассылает клиентам."""
        self.log("Этап process: разбираем buffer_data и отправляем результат")
        self.receive_and_sort_udp_raw()
        self.write_adc_channels_arrays_to_file()
        self.write_processed_adc_to_file()
        self.broadcast_adc_channels_to_clients()

    def read_json_parameters(self): #пока только для чтения конфигурации из файла, добавить переформатирование для отправки прибору
        with open('configuration_of_prms.json', 'r') as file:
            self.json_parameters = json.load(file)
        return self.json_parameters

    def main_loop_iteration(self):
        """
        Периодический цикл: опрос прибора по UDP, разбор данных и рассылка
        обработанных 16 каналов всем TCP-клиентам (строка = один отсчёт).
        """
        self.device_loop_iteration()


def main():
    """Точка входа: создаёт Qt-приложение и запускает окно сервера."""
    app = QApplication(sys.argv)
    win = TcpServerWindow()
    win.show()
    #sys.exit(app.exec_()) #не работает в 6 версии
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

