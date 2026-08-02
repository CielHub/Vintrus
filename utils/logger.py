# utils/logger.py

import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(log_dir: str = "logs") -> logging.Logger:
    """
    Mengonfigurasi sistem logging skala production.
    Menerapkan rotasi file (maksimal 5 MB per file, simpan 3 backup)
    untuk mencegah Memory/Storage Exhaustion di Android Termux.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger("ARS2")
    logger.setLevel(logging.DEBUG) # Tangkap semua level

    # Mencegah duplikasi handler jika fungsi dipanggil ulang
    if not logger.handlers:
        log_file = os.path.join(log_dir, "ars_daemon.log")
        
        # Rotating file handler: 5MB max, simpan 3 file lama
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setLevel(logging.DEBUG)
        
        # Format log terstruktur untuk memudahkan audit/debugging
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

