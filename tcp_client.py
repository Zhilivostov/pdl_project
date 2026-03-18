"""TCP‑клиент для TCP‑сервера.

Использует существующие компоненты:
- `Current_conf` из `configurator.py` для хранения/трансляции конфигурации;
- `ConfClientWindow` из `gui_conf_client.py` для редактирования параметров;
- `SimpleViewClientWindow` из `gui_simple_view_client.py` для просмотра данных.

Подключается к `tcp_server.py` (localhost:8888), принимает поток чисел,
преобразует его в псевдо‑2D массив (обороты × 16 АЦП) и отдаёт в
`SimpleViewClientWindow.data_received`.
"""

import sys
import json

import numpy as np

from PyQt5.QtNetwork import QTcpSocket, QHostAddress
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QLabel,
    QVBoxLayout,
    QWidget,
    QPushButton,
)

from gui_simple_view_client import SimpleViewClientWindow
from gui_conf_client import ConfClientWindow
from configurator import Current_conf


class ClientWindow(QMainWindow):
    def __init__(self, host="127.0.0.1", port=8888):
        super().__init__()
        self.host = host
        self.port = port

        # Хранилище последних измерений (список строк длиной 16)
        self._rows = []
        self._max_rows = 500  # глубина буфера для графика
        self._read_buffer = b""  # неполная строка от сокета

        # Конфигурация ПДА и её GUI
        self._init_config()

        self._init_ui()
        self._init_socket()
        self._init_view()

        # Автоматически пробуем подключиться к серверу при запуске
        self.connect_to_server()

    def _init_config(self):
        """Создаём объект конфигурации и окно конфигуратора."""
        self.conf = Current_conf()
        # Инициализируем текущие параметры из файла и сразу применяем их к GUI
        self.conf.init_config()
        self.conf_window = ConfClientWindow(self)
        self.conf_window.initiate_prms(self.conf.cur_prms)

        # Двусторонняя связь параметров:
        # изменения в GUI → в конфигурацию
        self.conf_window.prms_changed.connect(self._on_prms_changed_from_gui)
        # актуальные параметры ПДА → в GUI (через таймер в Current_conf)
        self.conf.PDA_prms_changed.connect(self.conf_window.PDA_prms_changed)
        self.conf_window.show()

    def _on_prms_changed_from_gui(self, prms: dict) -> None:
        """Обновляем локальную конфигурацию и отправляем новые параметры на сервер."""
        # Обновляем локальный объект конфигурации (регистры и prms)
        self.conf.user_prms_changed(prms)

        # Отправляем новые параметры на сервер, если есть соединение
        if self.socket.state() == QTcpSocket.ConnectedState:
            try:
                payload = json.dumps(prms, ensure_ascii=False)
                line = f"CONF {payload}\n".encode("utf-8")
                self.socket.write(line)
            except Exception:
                # В случае ошибки отправки просто игнорируем, GUI продолжит работать локально
                pass

    def _init_ui(self):
        self.setWindowTitle("TCP‑клиент (конфиг + просмотр)")
        self.setGeometry(200, 200, 400, 300)

        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)

        self.status_label = QLabel("Не подключено")
        self.last_value_label = QLabel("Последнее значение: —")

        self.connect_button = QPushButton("Подключиться")
        self.disconnect_button = QPushButton("Отключиться")

        self.connect_button.clicked.connect(self.connect_to_server)
        self.disconnect_button.clicked.connect(self.disconnect_from_server)

        layout.addWidget(self.status_label)
        layout.addWidget(self.last_value_label)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.disconnect_button)

    def _init_view(self):
        """Создаём и показываем окно простого просмотра."""
        self.simple_view = SimpleViewClientWindow(self)
        self.simple_view.show()

    def _init_socket(self):
        self.socket = QTcpSocket(self)
        self.socket.readyRead.connect(self.on_ready_read)
        self.socket.connected.connect(self.on_connected)
        self.socket.disconnected.connect(self.on_disconnected)
        self.socket.errorOccurred.connect(self.on_error)

    def connect_to_server(self):
        if self.socket.state() in (
            QTcpSocket.ConnectedState,
            QTcpSocket.ConnectingState,
        ):
            return
        self.status_label.setText(f"Подключение к {self.host}:{self.port}...")
        self.socket.connectToHost(QHostAddress(self.host), self.port)

    def disconnect_from_server(self):
        if self.socket.state() != QTcpSocket.UnconnectedState:
            self.socket.disconnectFromHost()

    def on_connected(self):
        self.status_label.setText("Подключено")

    def on_disconnected(self):
        self.status_label.setText("Отключено")

    def on_error(self, socket_error):
        # Показ простой текстовой ошибки
        self.status_label.setText(f"Ошибка: {self.socket.errorString()}")

    def on_ready_read(self):
        """Читаем все пришедшие данные, разбираем по строкам и один раз обновляем график — без зависаний."""
        self._read_buffer += bytes(self.socket.readAll())
        lines = self._read_buffer.split(b"\n")
        self._read_buffer = lines.pop()  # последний фрагмент может быть неполной строкой

        new_values = []
        for raw in lines:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                new_values.append(float(line))
            except ValueError:
                continue

        if not new_values:
            return

        self.last_value_label.setText(f"Последнее значение: {new_values[-1]:.5f}")

        for value in new_values:
            # Простое отображение: одна строка = 16 одинаковых каналов
            row = [value] * 16
            self._rows.append(row)
            if len(self._rows) > self._max_rows:
                self._rows.pop(0)

        data = np.array(self._rows, dtype=float)
        self.simple_view.data_received(data)


def main():
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

