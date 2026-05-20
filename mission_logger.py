#!/usr/bin/env python3
# =============================================================
# ФАЙЛ: mission_logger.py
# КУДА ЗАПУСКАТЬ: ноутбук, ПАРАЛЛЕЛЬНО с основной миссией
# НАЗНАЧЕНИЕ: Создание лог-файла (регламент п.12 — +2 балла!)
# =============================================================
# Логгер пишет файл mission_log_ДАТА_ВРЕМЯ.txt
# Подключается к Pioneer через SDK и записывает телеметрию.
# Запустите ДО начала зачётной попытки.
# =============================================================

import datetime
import time
import os

# Если Pioneer SDK доступен — используем его для телеметрии
# Если нет — логгер работает как ручной журнал
try:
    from pioneer_sdk import Pioneer
    PIONEER_AVAILABLE = True
except ImportError:
    PIONEER_AVAILABLE = False
    print("[Logger] pioneer_sdk не найден — используется ручной режим")

# ==================== НАСТРОЙКА ====================
LOG_DIR      = "logs"
POLL_INTERVAL = 0.5  # секунд между записями телеметрии

os.makedirs(LOG_DIR, exist_ok=True)

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
log_path  = os.path.join(LOG_DIR, f"mission_log_{timestamp}.txt")

# ==================== ЛОГГЕР ====================
class MissionLogger:
    def __init__(self, filepath):
        self.filepath  = filepath
        self.start_time = time.time()
        self.entries   = []

        self._write_header()
        print(f"[Logger] Лог-файл: {filepath}")

    def _write_header(self):
        header = (
            "=" * 60 + "\n"
            f"ЛОГ МИССИИ: Посадка дрона на движущуюся платформу\n"
            f"Дата/время: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
            "=" * 60 + "\n"
            "Время(с) | Событие | Данные\n"
            "-" * 60 + "\n"
        )
        with open(self.filepath, "w", encoding="utf-8") as f:
            f.write(header)

    def log(self, event: str, data: str = ""):
        """Записать событие в лог"""
        elapsed = time.time() - self.start_time
        entry = f"[{elapsed:7.2f}s] {event:<25} | {data}"
        self.entries.append(entry)

        # Немедленно пишем в файл (защита от краша)
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(entry + "\n")

        print(f"[Logger] {entry}")

    def log_telemetry(self, drone):
        """Записать телеметрию с дрона"""
        try:
            # Pioneer SDK методы телеметрии (если доступны)
            pos = drone.get_local_position_ned()
            if pos:
                self.log("TELEMETRY",
                    f"x={pos[0]:.2f} y={pos[1]:.2f} z={pos[2]:.2f}")
        except Exception as e:
            self.log("TELEMETRY_ERROR", str(e))

    def finalize(self):
        """Завершить лог"""
        total = time.time() - self.start_time
        footer = (
            "\n" + "-" * 60 + "\n"
            f"Общее время миссии: {total:.1f} секунд\n"
            f"Записей в логе: {len(self.entries)}\n"
            "=" * 60 + "\n"
        )
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(footer)
        print(f"[Logger] Лог завершён. Файл: {self.filepath}")
        print(f"[Logger] Всего событий: {len(self.entries)}")


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    logger = MissionLogger(log_path)
    logger.log("LOGGER_START", "Логгер инициализирован")

    drone = None
    if PIONEER_AVAILABLE:
        try:
            drone = Pioneer()
            logger.log("DRONE_CONNECT", "Подключение к дрону успешно")
        except Exception as e:
            logger.log("DRONE_CONNECT_FAIL", str(e))

    print("\n[Logger] Запущен. Ctrl+C для остановки и сохранения лога.")
    print(f"[Logger] Файл: {log_path}\n")

    # Ключевые события — вводить вручную при необходимости
    logger.log("MISSION_READY", "Команда готова к зачётной попытке")

    try:
        while True:
            if drone:
                logger.log_telemetry(drone)
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.log("MISSION_END", "Завершено оператором")
        logger.finalize()
