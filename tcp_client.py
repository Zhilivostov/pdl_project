"""TCP‑клиент для TCP‑сервера.

Использует существующие компоненты:
- `Current_conf` из `configurator.py` для хранения/трансляции конфигурации;
- `ConfClientWindow` из `gui_conf_client.py` для редактирования параметров;
- `SimpleViewClientWindow` из `gui_simple_view_client.py` для просмотра данных.

Подключается к `tcp_server.py` (localhost:8888), принимает бинарные кадры
с префиксом длины, преобразует их в 2D массив
(обороты × 16 АЦП) и отдаёт в
`SimpleViewClientWindow.data_received`.
"""

import sys
import json
import struct

import numpy as np

from PyQt6.QtNetwork import QTcpSocket, QHostAddress, QAbstractSocket
from PyQt6.QtWidgets import (
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
    """
    Основное окно клиента.

    Клиент объединяет 3 подсистемы:
    1) TCP-сокет (получение данных и отправка конфигурации на сервер),
    2) окно конфигурации (`ConfClientWindow`) + объект `Current_conf`,
    3) окно визуализации (`SimpleViewClientWindow`).
    """

    def __init__(self, host="127.0.0.1", port=8888):
        super().__init__()
        self.FRAME_DTYPE_INT16 = 1
        # Параметры подключения к серверу.
        self.host = host
        self.port = port

        # Хранилище последних измерений (список строк длиной 16)
        # simple_view ожидает 2D-массив, где каждая строка - "оборот",
        # а 16 столбцов - условные ADC-каналы.
        self._rows = []
        self._max_rows = 500  # глубина буфера для графика
        # Буфер для приёма бинарных TCP-кадров (на случай частичных пакетов).
        self._read_buffer = b""

        # Конфигурация ПДА и её GUI
        self._init_config()

        self._init_ui()
        self._init_socket()
        self._init_view()

        # Автоматически пробуем подключиться к серверу при запуске
        self.connect_to_server()

    def _init_config(self):
        """
        Создаёт локальную конфигурацию и окно редактирования параметров.

        Связи:
        - GUI -> _on_prms_changed_from_gui: пользователь меняет параметры.
        - conf.PDA_prms_changed -> GUI: периодическая синхронизация отображения.
        """
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
        """
        Обновляет конфигурацию после редактирования в окне настроек.

        Шаги:
        1) Обновляем локальный `Current_conf` (конвертация prms -> regs).
        2) Если есть TCP-соединение, отправляем серверу команду:
           CONF <json>\n
        """
        # Обновляем локальный объект конфигурации (регистры и prms)
        self.conf.user_prms_changed(prms)

        # Отправляем новые параметры на сервер, если есть соединение
        if self.socket.state() == QAbstractSocket.SocketState.ConnectedState:
            try:
                payload = json.dumps(prms, ensure_ascii=False)
                line = f"CONF {payload}\n".encode("utf-8")
                self.socket.write(line)
            except Exception:
                # В случае ошибки отправки просто игнорируем, GUI продолжит работать локально
                pass

    def _init_ui(self):
        """Создаёт небольшую панель состояния и кнопки управления подключением."""
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
        """Создаёт и показывает окно просмотра графиков/карт данных."""
        self.simple_view = SimpleViewClientWindow(self)
        self.simple_view.show()

    def _init_socket(self):
        """
        Инициализирует QTcpSocket и подключает все основные сигналы.

        readyRead      -> on_ready_read
        connected      -> on_connected
        disconnected   -> on_disconnected
        errorOccurred  -> on_error
        """
        self.socket = QTcpSocket(self)
        self.socket.readyRead.connect(self.on_ready_read)
        self.socket.connected.connect(self.on_connected)
        self.socket.disconnected.connect(self.on_disconnected)
        self.socket.errorOccurred.connect(self.on_error)

    def connect_to_server(self):
        """
        Запускает подключение к серверу.

        Защита от дублирования:
        если сокет уже connected/connecting, повторно connectToHost не вызывается.
        """
        if self.socket.state() in (
            QAbstractSocket.SocketState.ConnectedState,
            QAbstractSocket.SocketState.ConnectingState,
        ):
            return
        self.status_label.setText(f"Подключение к {self.host}:{self.port}...")
        self.socket.connectToHost(QHostAddress(self.host), self.port)

    def disconnect_from_server(self):
        """Корректно закрывает соединение с сервером."""
        if self.socket.state() != QAbstractSocket.SocketState.UnconnectedState:
            self.socket.disconnectFromHost()

    def on_connected(self):
        """Срабатывает после успешного TCP-подключения."""
        self.status_label.setText("Подключено")

    def on_disconnected(self):
        """Срабатывает при разрыве соединения."""
        self.status_label.setText("Отключено")

    def on_error(self, socket_error):
        """Показывает текст ошибки сокета в основном окне клиента."""
        # Показ простой текстовой ошибки
        self.status_label.setText(f"Ошибка: {self.socket.errorString()}")

    def on_ready_read(self):
        """
        Обрабатывает входящий поток бинарных кадров от сервера.
        Формат кадра:
        [uint32 payload_len][payload],
        где payload содержит:
        - uint64 timestamp_ms
        - uint16 rows
        - uint16 cols
        - uint8 dtype_code (1 = int16)
        - rows*cols значений int16 (row-major)
        """
        self._read_buffer += bytes(self.socket.readAll())
        while True:
            if len(self._read_buffer) < 4:
                return

            payload_len = struct.unpack(">I", self._read_buffer[:4])[0]
            if payload_len <= 0:
                self._read_buffer = self._read_buffer[4:]
                continue

            frame_len = 4 + payload_len
            if len(self._read_buffer) < frame_len:
                return

            payload = self._read_buffer[4:frame_len]
            self._read_buffer = self._read_buffer[frame_len:]

            matrix = self._decode_payload_to_matrix(payload)
            if matrix is None or matrix.size == 0:
                continue

            self._rows.extend(matrix.tolist())
            if len(self._rows) > self._max_rows:
                self._rows = self._rows[-self._max_rows:]

            data = np.array(self._rows, dtype=float)
            self.last_value_label.setText(
                f"Последнее значение (ch0): {data[-1, 0]:.5f}"
            )
            self.simple_view.data_received(data)

    def _decode_payload_to_matrix(self, payload):
        """Декодирует payload бинарного кадра в numpy-массив формы (rows, cols)."""
        header_len = struct.calcsize(">QHHB")
        if len(payload) < header_len:
            return None

        _timestamp_ms, rows, cols, dtype_code = struct.unpack(">QHHB", payload[:header_len])
        if rows <= 0 or cols <= 0:
            return None
        if dtype_code != self.FRAME_DTYPE_INT16:
            return None

        values_bytes = payload[header_len:]
        expected_bytes = rows * cols * np.dtype(np.int16).itemsize
        if len(values_bytes) != expected_bytes:
            return None

        values = np.frombuffer(values_bytes, dtype=np.int16)
        values = values.astype(np.float64, copy=False)
        matrix = values.reshape((rows, cols))
        return matrix


def main():
    """Точка входа: запускает Qt-приложение и окно клиента."""
    app = QApplication(sys.argv)
    window = ClientWindow()
    window.show()
    #sys.exit(app.exec_())
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

