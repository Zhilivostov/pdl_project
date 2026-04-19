"""Клиент-визуализатор данных из JSON без TCP-сервера.

Поведение максимально близко к tcp_client.py:
- источник данных: data.json вместо сокета;
- внутренний формат кадра: тот же payload, что и в TCP (timestamp, rows, cols, dtype, int16 values);
- обработка: через тот же decode -> numpy matrix -> SimpleViewClientWindow.data_received.
"""

import json
import struct
import sys
import time
from pathlib import Path

import numpy as np

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui_simple_view_client import SimpleViewClientWindow


class JsonClientWindow(QMainWindow):
    """Окно клиента, имитирующего входящие TCP-кадры из файла data.json."""

    FRAME_DTYPE_INT16 = 1

    def __init__(self, data_path: str = "data.json"):
        super().__init__()
        self.data_path = Path(data_path)

        self._rows = []
        self._max_rows = 500
        self._read_buffer = b""

        self._source_matrix = np.empty((0, 16), dtype=np.int16)
        self._source_index = 0
        self._chunk_rows = 8

        self._init_ui()
        self._init_view()
        self._init_timer()
        self._load_source()

    def _init_ui(self):
        self.setWindowTitle("JSON клиент (эмуляция TCP)")
        self.setGeometry(200, 200, 420, 220)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.status_label = QLabel("Источник: не загружен")
        self.last_value_label = QLabel("Последнее значение: -")

        self.reload_button = QPushButton("Перечитать data.json")
        self.start_button = QPushButton("Старт")
        self.stop_button = QPushButton("Стоп")

        self.reload_button.clicked.connect(self._reload_and_restart)
        self.start_button.clicked.connect(self.start_stream)
        self.stop_button.clicked.connect(self.stop_stream)

        layout.addWidget(self.status_label)
        layout.addWidget(self.last_value_label)
        layout.addWidget(self.reload_button)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)

    def _init_view(self):
        self.simple_view = SimpleViewClientWindow(self)
        self.simple_view.show()

    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._feed_next_chunk)

    def _load_source(self):
        if not self.data_path.exists():
            self.status_label.setText(f"Файл не найден: {self.data_path}")
            self._source_matrix = np.empty((0, 16), dtype=np.int16)
            return

        try:
            with self.data_path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except Exception as exc:
            self.status_label.setText(f"Ошибка чтения JSON: {exc}")
            self._source_matrix = np.empty((0, 16), dtype=np.int16)
            return

        matrix = self._json_to_matrix(raw)
        if matrix.size == 0:
            self.status_label.setText("В data.json нет корректных каналов ch0..ch15")
            self._source_matrix = np.empty((0, 16), dtype=np.int16)
            return

        self._source_matrix = matrix
        self._source_index = 0
        self._rows.clear()
        self._read_buffer = b""
        self.status_label.setText(
            f"Загружено строк: {self._source_matrix.shape[0]}, каналов: {self._source_matrix.shape[1]}"
        )

    def _json_to_matrix(self, data: dict) -> np.ndarray:
        channels = []
        for channel_idx in range(16):
            key = f"ch{channel_idx}"
            values = data.get(key, [])
            if not isinstance(values, list):
                return np.empty((0, 16), dtype=np.int16)
            channels.append(np.asarray(values, dtype=np.int16))

        min_len = min((len(ch) for ch in channels), default=0)
        if min_len <= 0:
            return np.empty((0, 16), dtype=np.int16)

        channels = [ch[:min_len] for ch in channels]
        # Было: 16 каналов по N отсчётов; нужно: N строк по 16 каналов.
        matrix = np.stack(channels, axis=1)
        return matrix.astype(np.int16, copy=False)

    def _reload_and_restart(self):
        self.stop_stream()
        self._load_source()
        self.start_stream()

    def start_stream(self):
        if self._source_matrix.size == 0:
            self.status_label.setText("Нечего воспроизводить: источник пуст")
            return
        if not self.timer.isActive():
            self.timer.start()
            self.status_label.setText("Воспроизведение: запущено")

    def stop_stream(self):
        if self.timer.isActive():
            self.timer.stop()
            self.status_label.setText("Воспроизведение: остановлено")

    def _feed_next_chunk(self):
        if self._source_matrix.size == 0:
            self.stop_stream()
            return

        start = self._source_index
        end = min(start + self._chunk_rows, self._source_matrix.shape[0])
        if start >= end:
            self.stop_stream()
            self.status_label.setText("Воспроизведение: завершено")
            return

        chunk_matrix = self._source_matrix[start:end]
        self._source_index = end

        frame = self._build_frame(chunk_matrix)
        # Имитируем приход бинарного кадра в буфер так же, как это делает QTcpSocket.
        self._read_buffer += frame
        self._process_read_buffer()

    def _build_frame(self, matrix: np.ndarray) -> bytes:
        rows, cols = matrix.shape
        timestamp_ms = int(time.time() * 1000)

        payload_header = struct.pack(">QHHB", timestamp_ms, rows, cols, self.FRAME_DTYPE_INT16)
        payload_values = matrix.astype(np.int16, copy=False).tobytes(order="C")
        payload = payload_header + payload_values

        frame_header = struct.pack(">I", len(payload))
        return frame_header + payload

    def _process_read_buffer(self):
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
            self.last_value_label.setText(f"Последнее значение (ch0): {data[-1, 0]:.5f}")
            self.simple_view.data_received(data)

    def _decode_payload_to_matrix(self, payload: bytes):
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
        return values.reshape((rows, cols))


def main():
    app = QApplication(sys.argv)
    window = JsonClientWindow("data.json")
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
