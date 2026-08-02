# core/scheduler.py

import asyncio
import logging
from typing import Dict, List
from core.fsm import InstanceState
from core.package_manager import RobloxInstance
from core.engine import ARSEngine
from android.bridge import AndroidBridge

logger = logging.getLogger("ARS2.Scheduler")

class Watchdog:
    """
    Pemantau utama (Producer). Melakukan bulk-polling ke OS,
    mengevaluasi state dari setiap instance, dan memasukkan instance yang mati ke Engine.
    """
    
    def __init__(self, engine: ARSEngine, poll_interval: int = 5):
        self.engine = engine
        self.instances = engine.instances
        self.target_packages = list(self.instances.keys())
        self.poll_interval = poll_interval
        self._is_running = False

    async def start(self):
        """Memulai loop Watchdog utama."""
        self._is_running = True
        logger.info("Watchdog dimulai...")
        
        while self._is_running:
            try:
                await self._monitor_cycle()
            except Exception as e:
                logger.error(f"Kesalahan fatal pada Watchdog cycle: {str(e)}")
            
            # Non-blocking sleep, menjaga loop tetap stabil
            await asyncio.sleep(self.poll_interval)

    async def _monitor_cycle(self):
        """Satu siklus penuh pemeriksaan PID dan evaluasi state."""
        # 1. Bulk I/O Request (Hanya 1x eksekusi OS shell)
        active_pids = await AndroidBridge.get_active_pids(self.target_packages)
        
        # 2. Evaluasi setiap instance di memory
        for pkg_name, instance in self.instances.items():
            current_pid = active_pids.get(pkg_name)
            
            # --- EVALUASI STATE ---
            
            # Kondisi A: Aplikasi terdeteksi berjalan
            if current_pid:
                if instance.state != InstanceState.RUNNING:
                    instance.update_pid(current_pid)
                    instance.transition_to(InstanceState.RUNNING)
                    logger.info(f"[{pkg_name}] Terdeteksi ONLINE (PID: {current_pid}).")
                
                # Reset dosanya jika sudah stabil lama
                instance.reset_telemetry_if_stable()

            # Kondisi B: Aplikasi hilang / tidak terdeteksi
            else:
                if instance.state == InstanceState.RUNNING:
                    logger.warning(f"[{pkg_name}] Terdeteksi OFFLINE (PID hilang).")
                    instance.transition_to(InstanceState.CRASHED)
                    
                    # Cek batas toleransi crash
                    if instance.crash_count >= instance.max_crashes:
                        instance.apply_cooldown()
                    else:
                        # Kirim ke antrean untuk dipulihkan oleh Engine
                        await self.engine.enqueue_recovery(instance)
                        
                elif instance.state == InstanceState.IDLE:
                    # Peluncuran pertama kali saat aplikasi baru mulai
                    await self.engine.enqueue_recovery(instance)
                    
                elif instance.state == InstanceState.COOLDOWN:
                    # Cek apakah masa hukuman sudah habis
                    if instance.is_cooldown_expired():
                        logger.info(f"[{pkg_name}] Masa COOLDOWN selesai. Bersiap recovery.")
                        instance.cooldown_until = 0.0 # Reset
                        await self.engine.enqueue_recovery(instance)

