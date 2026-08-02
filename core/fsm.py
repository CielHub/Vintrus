# core/fsm.py

from enum import Enum, auto

class InstanceState(Enum):
    """
    Representasi absolut dari siklus hidup (lifecycle) sebuah instance Roblox.
    """
    IDLE = auto()           # Menunggu instruksi awal. Belum pernah diluncurkan.
    STARTING = auto()       # Perintah am start sudah dikirim, menunggu PID muncul.
    RUNNING = auto()        # PID terdeteksi di OS, aplikasi sedang aktif berjalan.
    CRASHED = auto()        # PID tiba-tiba hilang. Aplikasi mati tidak wajar.
    RECOVERY_WAIT = auto()  # Berada dalam antrean penundaan (Exponential Backoff).
    COOLDOWN = auto()       # Crash melebihi batas toleransi. Sistem membekukan instance sementara.

