import sys
import math
import time
import json

from PyQt5.QtCore import QTimer
from PyQt5.QtNetwork import QTcpServer, QTcpSocket, QHostAddress
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QTextEdit

from configurator import Current_conf


class TcpServerWindow(QMainWindow):
    def __init__(self, host='127.0.0.1', port=8888):
        super().__init__()
        self.host = host
        self.port = port

        self.clients = set()
        self.client_ids = {}
        self.next_client_id = 1
        self._read_buffers = {}
        self.buffer = []       # храним последние N значений
        self.buffer_size = 1000

        self.start_time = time.time()

        # Локальная конфигурация ПДА на стороне сервера
        self.conf = Current_conf()
        self.conf.init_config()

        self._init_ui()
        self._init_server()
        self._init_main_loop()

    def _init_ui(self):
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
        """Добавляет строку в окно логов сервера."""
        timestamp = time.strftime("%H:%M:%S")
        self.log_widget.append(f"[{timestamp}] {message}")

    def _init_server(self):
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

    def _init_main_loop(self):
        # основной цикл сервера: генерирует данные и рассылает их клиентам
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.main_loop_iteration)
        self.timer.start(50)  # период 50 мс (20 Гц)
        self.log("Основной цикл сервера запущен (50 мс шаг)")
        self.log("Конфигурация загружена на сервере и хранится в памяти")

    def on_new_connection(self):
        while self.tcp_server.hasPendingConnections():
            sock = self.tcp_server.nextPendingConnection()
            sock.disconnected.connect(self.on_client_disconnected)
            sock.readyRead.connect(self.on_client_ready_read)
            self.clients.add(sock)
            client_id = self.next_client_id
            self.client_ids[sock] = client_id
            self._read_buffers[sock] = b""
            self.next_client_id += 1

        self.status_label.setText(
            f"Клиенты подключены: {len(self.clients)}"
        )
        self.log(
            f"Клиент #{client_id} подключился. Всего клиентов: {len(self.clients)}"
        )

    def on_client_disconnected(self):
        sock = self.sender()
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
        """Приём сообщений от клиентов (в т.ч. обновлённой конфигурации)."""
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

    def main_loop_iteration(self):
        """
        Основной цикл:
        1. Генерируем новое значение и пишем в буфер.
        2. Отправляем последнее значение всем клиентам.
        """
        # 1. Генерация данных (синусоидальный сигнал)
        t = time.time() - self.start_time
        value = math.sin(t) + 0.1 * math.sin(5 * t)

        self.buffer.append(value)
        if len(self.buffer) > self.buffer_size:
            self.buffer = self.buffer[-self.buffer_size:]

        # Логируем факт генерации нового значения
        self.log(f"Сгенерированы новые данные: {value:.6f}")

        # 2. Отправка данных клиентам (одно значение в строке)
        if not self.clients:
            return

        line = f"{value:.6f}\n".encode("utf-8")

        for sock in list(self.clients):
            if sock.state() == QTcpSocket.ConnectedState:
                try:
                    sock.write(line)
                except Exception:
                    if sock in self.clients:
                        client_id = self.client_ids.get(sock, "?")
                        self.clients.remove(sock)
                        self.client_ids.pop(sock, None)
                        self.log(
                            f"Ошибка при отправке данных клиенту #{client_id}, клиент удалён из списка"
                        )


def main():
    app = QApplication(sys.argv)
    win = TcpServerWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

