# core/engine.py

import asyncio
import logging
from typing import Dict
from core.fsm import InstanceState
from core.package_manager import RobloxInstance
from android.bridge import AndroidBridge
from utils.exceptions import ARSBaseException

logger = logging.getLogger("ARS2.Engine")

class ARSEngine:
    """
    Worker asinkron yang menangani peluncuran dan pemulihan instance.
    Menggunakan antrean (Queue) untuk mencegah Thundering Herd Problem.
    """
    
    def __init__(self, instances: Dict[str, RobloxInstance]):
        self.instances = instances
        # Queue membatasi jumlah eksekusi bersamaan (Concurrency Control)
        self.recovery_queue: asyncio.Queue[RobloxInstance] = asyncio.Queue()
        self._is_running = False

    async def _recovery_worker(self):
        """
        Background task (Consumer) yang mengambil tugas dari queue.
        Menjamin bahwa peluncuran aplikasi dilakukan secara bergiliran (staggered).
        """
        while self._is_running:
            try:
                # Mengambil instance dari antrean (akan memblokir asinkron jika antrean kosong)
                instance = await self.recovery_queue.get()
                
                # Double-check state sebelum eksekusi
                if instance.state == InstanceState.COOLDOWN:
                    logger.warning(f"[{instance.package_name}] Dibatalkan dari antrean, sedang masa COOLDOWN.")
                    self.recovery_queue.task_done()
                    continue

                await self._process_launch(instance)
                
                # Staggered Launch: Jeda wajib antar peluncuran (mencegah lonjakan CPU/RAM)
                await asyncio.sleep(4) 
                
                self.recovery_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker Error tidak terduga: {str(e)}")

    async def _process_launch(self, instance: RobloxInstance):
        """Logika eksekusi launch beserta kalkulasi penundaan (Backoff)."""
        backoff_time = instance.get_backoff_time()
        
        if backoff_time > 0:
            logger.info(f"[{instance.package_name}] Menerapkan penundaan (Backoff): {backoff_time} detik.")
            instance.transition_to(InstanceState.RECOVERY_WAIT)
            await asyncio.sleep(backoff_time)
            
        try:
            if instance.transition_to(InstanceState.STARTING):
                # Memaksa aplikasi mati sebelum di-launch (mencegah memory leak / sisa proses)
                await AndroidBridge.force_stop(instance.package_name)
                
                # Eksekusi launch OS
                await AndroidBridge.launch_package(
                    package=instance.package_name,
                    activity=instance.activity_name,
                    intent_url=instance.intent_url
                )
                logger.info(f"[{instance.package_name}] Perintah Launch terkirim.")
                
        except ARSBaseException as e:
            logger.error(f"[{instance.package_name}] Gagal launch: {str(e)}")
            instance.transition_to(InstanceState.CRASHED) # Kembalikan ke state mati

    def start_worker(self):
        """Memulai task worker di event loop."""
        self._is_running = True
        return asyncio.create_task(self._recovery_worker())

    async def enqueue_recovery(self, instance: RobloxInstance):
        """Fungsi Producer untuk memasukkan instance ke antrean pemulihan."""
        # Cegah duplikasi dalam antrean
        if instance.state not in [InstanceState.STARTING, InstanceState.RECOVERY_WAIT]:
            await self.recovery_queue.put(instance)
  
