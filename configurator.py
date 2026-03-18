"""Хранение и трансляция конфигурации ПДА.

`Current_conf`:
- поддерживает текущее состояние регистров и параметров ПДА;
- периодически рассылает изменения серверу и клиентскому GUI;
- конвертирует человеко‑читаемые параметры в бинарные регистры и обратно.
"""

from PyQt5.QtCore import QObject, pyqtSignal, QTimer
import json
import struct


REG_KEYS = [
    b"\x00",  # [-2] - inner/outer trigger, [-1] - gain
    b"\x01",  # Nc - here turns number x 12
    b"\x02",  # Nc (one more)
    b"\x04",  # fronts overlapping
    b"\x06",  # separatrix code
    b"\x08",  # fine delay
    b"\x09",  # should be 0x0a for correct ADC data writing
]

PRMS = {
    "Turns number": [0, 2729, 1],  # 0x02 and 0x01 registers values together / 12
    "Separatrix": [0, 13, 1],  # 0x06 : val = (255 - reg value)
    "Fine delay (ns)": [0, 10.23, 0.1],  # 0x08 : 1 unit = 10 ps = 0.01 ns
    "Fronts overlay": [0, 15, 1],  # 0x04 : val ? - it depends
    "ADC delay": [10, 10, 1],  # 0x09 : value should be 10 (0x0a) for correct ADC data writing
    "Trigger": [0, 1, 1],  # 0x00, 15th bit (0 - internal, 1 - external)
    "Gain": [0, 1, 1],  # 0x00, 0th bit
}


class Current_conf(QObject):
    data_type = type({})
    regs_for_to_change = pyqtSignal(data_type)
    PDA_prms_changed = pyqtSignal(data_type)

    def __init__(self, parent=None):
        super(Current_conf, self).__init__(parent)

        self.cur_regs = dict.fromkeys(REG_KEYS)
        self.PDA_regs = dict.fromkeys(REG_KEYS)

        self.cur_prms = dict.fromkeys(PRMS.keys())
        self.PDA_prms = dict.fromkeys(PRMS.keys())

        # Периодические рассылки конфигурации (серверу и клиенту)
        interval = 1500
        self.timer_to_PDA = QTimer()
        self.timer_to_PDA.setInterval(interval)
        self.timer_to_PDA.timeout.connect(self.timer_to_PDA_upd)
        self.timer_to_PDA.start()

        interval = 1000
        self.timer_to_Client = QTimer()
        self.timer_to_Client.setInterval(interval)
        self.timer_to_Client.timeout.connect(self.timer_to_Client_upd)
        self.timer_to_Client.start()

        self.save_regs_timer = QTimer()
        self.save_regs_timer.setInterval(4 * 1000)
        self.save_regs_timer.timeout.connect(self.upd_PDA_regs)

        self.save_regs_timer.setSingleShot(True)

    def upd_PDA_regs(self):
        print("conf: PDA configuration saved")
        tmp = self.PDA_prms
        with open("configuration_of_prms.json", "w", encoding = "utf-8") as f:
            for chunk in json.JSONEncoder(ensure_ascii = False, indent = 4).iterencode(tmp):
                f.write(chunk)
        self.save_regs_timer.start()

    def timer_to_PDA_upd(self):
        self.regs_for_to_change.emit(self.cur_regs)

    def timer_to_Client_upd(self):
        self.PDA_prms_changed.emit(self.PDA_prms)
        
    def init_config(self):
        for i in self.cur_regs.keys():
            self.cur_regs[i] = b"\x00\x00"

        with open("configuration_of_prms.json", "r", encoding="utf-8") as config:
            tmp = config.read()
        str_dict = json.loads(tmp)

        regs = {}
        for i in str_dict.keys():
            self.convert_prm_to_reg(i, str_dict[i])

        self.convert_regs_to_prms(self.cur_regs, self.cur_prms)

        self.save_regs_timer.start()

        return self.cur_regs


    def convert_regs_to_prms(self, regs_dict, tmp):
        val = struct.unpack('>i', regs_dict[b'\x02'] + regs_dict[b'\x01'])[0] / 12
        tmp["Turns number"] = val

        val = 255 - struct.unpack('>H', regs_dict[b'\x06'])[0]
        tmp["Separatrix"] = val

        val = struct.unpack('>H', regs_dict[b'\x08'])[0] * 10 / 1000
        tmp["Fine delay (ns)"] = val

        val = struct.unpack('>H', regs_dict[b'\x04'])[0]
        tmp["Fronts overlay"] = val

        val = struct.unpack('>H', regs_dict[b'\x09'])[0]
        tmp["ADC delay"] = val

        val = struct.unpack('>H', regs_dict[b'\x00'])[0]
        tmp["Trigger"] = val >> 15 & 1
        tmp["Gain"] = val & 1


    def set_cur_reg(self, reg, value):
        self.cur_regs[reg] = value

    def PDA_conf_updated(self, regs_dict):
        self.convert_regs_to_prms(regs_dict, self.PDA_prms)
        # self.PDA_prms_changed.emit(self.PDA_prms) # it is wrong emition!!!

    def user_prms_changed(self, prms_dict):
        print("conf:", "upd")
        for i in prms_dict.keys():
            self.convert_prm_to_reg(i, prms_dict[i])

    def convert_prm_to_reg(self, name, prm):
        """Преобразует человеко‑читаемый параметр в значение регистра.

        Если значение параметра отсутствует (`None`), просто ничего не делает,
        оставляя регистр в текущем состоянии.
        """
        if prm is None:
            # Нечего конвертировать — используем уже существующее значение
            return

        if name == "Turns number":
            reg_1 = b'\x01'
            reg_2 = b'\x02'
            N = struct.pack('>L', int(prm * 12)) #L - unsigned long integer 4 bytes
            self.set_cur_reg(reg_1, N[2:])
            self.set_cur_reg(reg_2, N[:2])

        elif name == "Separatrix":
            reg = b'\x06'
            val = struct.pack('>H', 255 - int(prm))
            self.set_cur_reg(reg, val)

        elif name == "Fine delay (ns)":
            reg = b'\x08'
            val = struct.pack('>H', int(prm / 10 * 1000))
            self.set_cur_reg(reg, val)

        elif name == "Fronts overlay":
            reg = b'\x04'
            val = struct.pack('>H', int(prm))
            self.set_cur_reg(reg, val)

        elif name == "ADC delay":
            reg = b'\x09'
            val = struct.pack('>H', int(prm))
            self.set_cur_reg(reg, val)

        elif name == "Gain":
            reg = b'\x00'
            another = struct.unpack('>H', self.cur_regs[reg])[0] & (1 << 15)
            val = struct.pack('>H', int(prm) | another)
            self.set_cur_reg(reg, val)

        elif name == "Trigger":
            reg = b'\x00'
            another = struct.unpack('>H', self.cur_regs[reg])[0] & 1
            val = struct.pack('>H', int(prm) << 15 | another)
            self.set_cur_reg(reg, val)

        else:
            print("ERROR(Current_conf.convert_prm_to_reg): Unknown name of parameter:", name)
