# android/bridge.py

import asyncio
import shlex
import logging
import re
from typing import Dict, List
from utils.exceptions import AndroidShellError, ShellTimeoutError

logger = logging.getLogger("ARS2.Bridge")

class AndroidBridge:
    """
    Abstraksi Asynchronous untuk interaksi dengan Shell Android.
    Selalu menggunakan akses Root (su) untuk setiap eksekusi.
    """

    @staticmethod
    async def _execute_su(command: str, timeout: int = 10) -> str:
        """
        Fungsi internal untuk mengeksekusi perintah shell asinkron dengan Root.
        Menerapkan mekanisme timeout untuk mencegah Zombie Process.
        """
        # Sanitasi command string jika diperlukan (menghindari injeksi)
        su_command = f"su -c {shlex.quote(command)}"
        
        try:
            process = await asyncio.create_subprocess_shell(
                su_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            
            if process.returncode != 0:
                # Mengabaikan error grep jika tidak ada hasil yang cocok (exit code 1)
                if process.returncode == 1 and "grep" in command:
                    return ""
                raise AndroidShellError(command, process.returncode, stderr.decode())
                
            return stdout.decode('utf-8').strip()

        except asyncio.TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass # Proses sudah mati
            raise ShellTimeoutError(command, timeout)

    @staticmethod
    async def get_active_pids(target_packages: List[str]) -> Dict[str, int]:
        """
        (Optimasi Kritis) Mengambil semua PID target dalam 1 siklus shell.
        Jauh lebih efisien dari `pidof` berulang.
        Mengembalikan dictionary: {'com.roblox.client': 12345}
        """
        if not target_packages:
            return {}

        active_pids: Dict[str, int] = {}
        # Membaca seluruh proses. Regex akan menangani variasi format output dari `ps`.
        output = await AndroidBridge._execute_su("ps -A")
        lines = output.splitlines()

        for line in lines:
            for pkg in target_packages:
                if pkg in line:
                    # Parsing standar: ambil elemen pertama/kedua yang berupa angka (PID)
                    # Contoh baris: u0_a123   4567  890  1234  5678 S com.roblox.client
                    match = re.search(r'\b(\d+)\b', line)
                    if match:
                        active_pids[pkg] = int(match.group(1))
                        break # Pindah ke baris berikutnya setelah ketemu
                        
        return active_pids

    @staticmethod
    async def launch_package(package: str, activity: str, intent_url: str) -> None:
        """
        Meluncurkan aplikasi ke dalam Floating/Freeform Window (Mode 5).
        Dilengkapi dengan flag pembersihan instance memori.
        """
        # Flag 0x10008000 = FLAG_ACTIVITY_NEW_TASK | FLAG_ACTIVITY_CLEAR_TASK
        url_safe = shlex.quote(intent_url)
        cmd = (
            f"am start -n {package}/{activity} "
            f"-a android.intent.action.VIEW -d {url_safe} "
            f"-f 0x10008000 --windowingMode 5"
        )
        logger.debug(f"Launching {package} in Floating Window mode...")
        await AndroidBridge._execute_su(cmd)

    @staticmethod
    async def force_stop(package: str) -> None:
        """
        Membunuh proses secara paksa tanpa menunggu graceful exit (sangat dianjurkan untuk recovery).
        """
        logger.debug(f"Force stopping {package}...")
        await AndroidBridge._execute_su(f"am force-stop {package}")

    @staticmethod
    async def clear_cache(package: str) -> None:
        """
        Membersihkan cache menggunakan internal command Android, bukan rm -rf.
        Ini menjaga integritas filesystem OS.
        """
        logger.debug(f"Clearing cache for {package}...")
        # Perintah ini aman dari memblokir disk I/O dan didukung natif oleh package manager (pm)
        await AndroidBridge._execute_su(f"pm clear --cache-only {package}")
                  
