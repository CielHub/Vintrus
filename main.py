# main.py

import os
import sys
import asyncio
import logging
import signal

# Import built-in TOML parser (Python 3.11+)
try:
    import tomllib
except ImportError:
    print("FATAL: Membutuhkan Python 3.11+ (tomllib tidak ditemukan).")
    sys.exit(1)

from core.package_manager import RobloxInstance
from core.engine import ARSEngine
from core.scheduler import Watchdog
from ui.dashboard import DashboardUI
from utils.logger import setup_logger
from android.bridge import AndroidBridge

logger = setup_logger("logs")

async def check_root_access():
    """Memverifikasi bahwa lingkungan eksekusi memiliki akses Magisk/KernelSU."""
    try:
        output = await AndroidBridge._execute_su("id -u")
        if output != "0":
            raise PermissionError("Akses Root ditolak.")
    except Exception as e:
        logger.critical(f"Sistem gagal mendapatkan akses Root: {e}")
        print("\n[!] FATAL ERROR: Membutuhkan akses Root (su). Pastikan Termux diberi izin Magisk.")
        sys.exit(1)

def load_configuration(config_path: str = "config.toml") -> dict:
    """Membaca spesifikasi instansiasi dari config.toml."""
    if not os.path.exists(config_path):
        logger.critical(f"File config {config_path} tidak ditemukan.")
        sys.exit(1)
        
    with open(config_path, "rb") as f:
        return tomllib.load(f)

async def main():
    # 1. Pre-flight Check
    await check_root_access()
    config = load_configuration()
    
    logger.info("Memulai Inisialisasi ARS-2...")

    # 2. Merakit Model Data (Instances)
    instances = {}
    global_intent = config["roblox_global"]["base_intent_url"]
    max_crashes = config["system"]["max_crashes_before_cooldown"]

    for pkg_name, pkg_data in config.get("packages", {}).items():
        if pkg_data.get("enabled", False):
            # Gunakan URL spesifik jika ada, fallback ke global jika tidak
            intent_url = pkg_data.get("intent_url", global_intent)
            instances[pkg_name] = RobloxInstance(
                package_name=pkg_name, 
                intent_url=intent_url,
                max_crashes=max_crashes
            )

    if not instances:
        logger.error("Tidak ada package yang diaktifkan dalam config.")
        sys.exit(1)

    # 3. Dependency Injection & Assembly
    engine = ARSEngine(instances)
    watchdog = Watchdog(engine, poll_interval=config["system"]["poll_interval_seconds"])
    dashboard = DashboardUI(instances)

    # 4. Mendaftarkan Task Asinkron (Concurrent Execution)
    # Ini memastikan Engine, Watchdog, dan UI berjalan bersamaan tanpa saling blokir.
    tasks = [
        engine.start_worker(),
        asyncio.create_task(watchdog.start()),
        asyncio.create_task(dashboard.render_loop(refresh_rate_hz=2))
    ]

    logger.info("Seluruh subsistem beroperasi.")

    # 5. Menjaga Loop Tetap Hidup & Menangani Terminasi
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Menerima sinyal terminasi. Mematikan sistem...")
    finally:
        # Graceful Shutdown
        logger.info("Membersihkan resource dan mematikan task asinkron...")
        engine._is_running = False
        watchdog._is_running = False
        dashboard._is_running = False
        
        # Opsi: matikan semua package yang sedang dipantau saat ARS dimatikan
        # for pkg in instances.keys():
        #     await AndroidBridge.force_stop(pkg)
            
        logger.info("ARS-2 Daemon berhenti secara sempurna (Graceful Exit).")

if __name__ == "__main__":
    # Menangani KeyboardInterrupt secara aman di asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass # Ditangkap oleh asyncio.CancelledError di dalam main()

