# core/package_manager.py

import time
import logging
from typing import Optional
from core.fsm import InstanceState

logger = logging.getLogger("ARS2.PackageManager")

class RobloxInstance:
    """
    Representasi stateful dari satu package Roblox Delta Lite.
    Mengelola transisi FSM, penghitungan crash, dan kalkulasi Exponential Backoff.
    """
    
    def __init__(self, package_name: str, intent_url: str, max_crashes: int = 3):
        # Identitas & Konfigurasi
        self.package_name = package_name
        self.activity_name = "com.roblox.client.Activity" # Default Roblox activity
        self.intent_url = intent_url
        self.max_crashes = max_crashes
        
        # State & OS Reference
        self._state: InstanceState = InstanceState.IDLE
        self.pid: Optional[int] = None
        
        # Telemetry & Timestamp
        self.crash_count = 0
        self.last_launch_time: float = 0.0
        self.last_running_time: float = 0.0
        self.cooldown_until: float = 0.0
        
        # Base config untuk Exponential Backoff (dalam detik)
        self._base_backoff_seconds = 5 

    @property
    def state(self) -> InstanceState:
        """Read-only access ke state saat ini."""
        return self._state

    def transition_to(self, new_state: InstanceState) -> bool:
        """
        Fungsi gerbang (Guard Rail) untuk mengubah state.
        Mencegah transisi ilegal yang berpotensi memicu race condition.
        """
        # Guard: Tidak boleh STARTING jika masih dalam masa COOLDOWN
        if new_state == InstanceState.STARTING:
            if time.time() < self.cooldown_until:
                logger.warning(f"[{self.package_name}] Ditolak: Transisi ke STARTING saat masih COOLDOWN.")
                return False
            self.last_launch_time = time.time()
            self.pid = None # Reset PID setiap kali mau start
            
        elif new_state == InstanceState.RUNNING:
            self.last_running_time = time.time()
            
        elif new_state == InstanceState.CRASHED:
            self.crash_count += 1
            self.pid = None
            
        # Logging transisi untuk kemudahan debugging UI
        if self._state != new_state:
            logger.debug(f"[{self.package_name}] STATE CHANGE: {self._state.name} -> {new_state.name}")
            
        self._state = new_state
        return True

    def update_pid(self, new_pid: Optional[int]):
        """Pembaruan PID eksternal dari Watchdog."""
        self.pid = new_pid

    def get_backoff_time(self) -> int:
        """
        Kalkulasi jeda pemulihan (Exponential Backoff).
        Algoritma: Base * (Multiplier ^ (CrashCount - 1))
        Contoh: Crash 1 = 5s | Crash 2 = 15s | Crash 3 = 45s
        """
        if self.crash_count == 0:
            return 0
            
        multiplier = 3
        # Pangkat matematika untuk kurva penundaan eksponensial
        calculated_backoff = self._base_backoff_seconds * (multiplier ** (self.crash_count - 1))
        
        # Hard limit maksimal penundaan 5 menit (300 detik)
        return min(calculated_backoff, 300)

    def is_cooldown_expired(self) -> bool:
        """Cek apakah masa hukuman (cooldown) sudah selesai."""
        return time.time() >= self.cooldown_until

    def apply_cooldown(self, cooldown_seconds: int = 600):
        """Menerapkan status COOLDOWN (misal: 10 menit)."""
        self.cooldown_until = time.time() + cooldown_seconds
        self.transition_to(InstanceState.COOLDOWN)
        logger.warning(f"[{self.package_name}] Memasuki masa COOLDOWN selama {cooldown_seconds} detik.")

    def reset_telemetry_if_stable(self, stable_threshold_seconds: int = 600):
        """
        Dipanggil oleh Watchdog saat instance dalam state RUNNING.
        Jika sudah RUNNING tanpa putus selama threshold (misal 10 menit), reset crash count.
        Ini krusial untuk umur panjang (longevity) daemon 24/7.
        """
        if self._state == InstanceState.RUNNING and self.last_running_time > 0:
            uptime = time.time() - self.last_running_time
            if uptime > stable_threshold_seconds and self.crash_count > 0:
                logger.info(f"[{self.package_name}] Uptime stabil ({int(uptime)}s). Mereset crash count.")
                self.crash_count = 0
                self.cooldown_until = 0.0

