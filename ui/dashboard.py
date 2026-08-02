# ui/dashboard.py

import asyncio
import time
from typing import Dict
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box
from core.fsm import InstanceState
from core.package_manager import RobloxInstance

class DashboardUI:
    """
    UI berbasis CLI yang murni bertindak sebagai pengamat (Read-Only).
    Tidak melakukan I/O ke OS, hanya membaca state dari memory (Dictionary Instances).
    """
    def __init__(self, instances: Dict[str, RobloxInstance]):
        self.instances = instances
        self._is_running = False

    def _generate_table(self) -> Table:
        """Membuat tabel status berdasarkan snapshot data di memori."""
        table = Table(
            box=box.ROUNDED, 
            expand=True,
            header_style="bold cyan",
            border_style="bright_black"
        )
        
        table.add_column("Package ID", justify="left")
        table.add_column("State", justify="center")
        table.add_column("PID", justify="right")
        table.add_column("Uptime / Wait", justify="right")
        table.add_column("Crash", justify="center")

        current_time = time.time()

        for pkg, instance in self.instances.items():
            # Formatting warna berdasarkan state FSM
            state_str = instance.state.name
            if instance.state == InstanceState.RUNNING:
                state_formatted = f"[bold green]{state_str}[/bold green]"
                # Hitung uptime
                time_val = f"{int(current_time - instance.last_running_time)}s"
            elif instance.state in (InstanceState.CRASHED, InstanceState.COOLDOWN):
                state_formatted = f"[bold red]{state_str}[/bold red]"
                # Tampilkan sisa cooldown jika ada
                if instance.cooldown_until > 0:
                    time_val = f"{max(0, int(instance.cooldown_until - current_time))}s left"
                else:
                    time_val = "-"
            elif instance.state == InstanceState.RECOVERY_WAIT:
                state_formatted = f"[bold yellow]{state_str}[/bold yellow]"
                time_val = "-"
            else:
                state_formatted = f"[bold cyan]{state_str}[/bold cyan]"
                time_val = "-"

            pid_str = str(instance.pid) if instance.pid else "-"
            
            # Formatting crash count
            crash_color = "red" if instance.crash_count > 0 else "green"
            crash_str = f"[{crash_color}]{instance.crash_count}/{instance.max_crashes}[/{crash_color}]"

            # Nama package disingkat (misal com.roblox.client1 -> ...client1)
            short_pkg = pkg.split(".")[-1]

            table.add_row(short_pkg, state_formatted, pid_str, time_val, crash_str)

        return table

    async def render_loop(self, refresh_rate_hz: int = 2):
        """
        Background task untuk memperbarui layar secara berkala.
        Refresh rate 2 Hz (0.5 detik) sudah sangat cukup dan hemat CPU.
        """
        self._is_running = True
        
        # rich.Live secara otomatis menangani redraw terminal dengan bersih
        with Live(self._generate_table(), refresh_per_second=refresh_rate_hz) as live:
            while self._is_running:
                try:
                    # Update tabel tanpa memblokir asyncio event loop
                    live.update(self._generate_table())
                    await asyncio.sleep(1.0 / refresh_rate_hz)
                except asyncio.CancelledError:
                    break
                  
