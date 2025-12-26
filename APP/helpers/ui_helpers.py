# Fungsi progress untuk menampilkan kemajuan unduhan model
# Sekarang menggunakan logging.debug agar tidak mengisi console secara default
import logging
logger = logging.getLogger("ModelDownload")


def download_progress_callback(model_name, progress):
    """
    Callback untuk progress unduhan model. Tidak mencetak ke stdout agar tidak mengganggu UI.

    Args:
        model_name (str): Nama model
        progress (float): Persentase kemajuan (0-100)
    """
    try:
        logger.debug("Unduh model %s: %.1f%%", model_name, progress)
    except Exception:
        pass
