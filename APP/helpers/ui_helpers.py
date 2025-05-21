# Fungsi progress untuk menampilkan kemajuan unduhan model
import sys
import os

def download_progress_callback(model_name, progress):
    """
    Callback untuk menampilkan kemajuan unduhan model
    
    Args:
        model_name (str): Nama model
        progress (float): Persentase kemajuan (0-100)
    """
    sys.stdout.write(f"\rMengunduh model {model_name}: {progress:.1f}% selesai")
    sys.stdout.flush()
    if progress >= 100:
        sys.stdout.write("\n")
