import os
import sys
import requests
import shutil
from pathlib import Path
from PIL import Image
import threading

# Tentukan lokasi penyimpanan model 
# (di dalam folder proyek untuk self-contained)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODEL_DIR = os.path.join(BASE_DIR, ".u2net")
os.makedirs(MODEL_DIR, exist_ok=True)
print(f"Model rembg akan disimpan di: {MODEL_DIR}")

# Daftar model dan URL unduhan (hanya model default)
DEFAULT_MODEL = "isnet-general-use"
MODELS = {
    DEFAULT_MODEL: "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx"
}

# Model filename mapping
MODEL_FILENAMES = {
    DEFAULT_MODEL: "isnet-general-use.onnx"
}

# Variabel untuk melacak unduhan yang sedang berjalan
current_downloads = {}
download_lock = threading.Lock()

def download_model(model_name, callback=None):
    """
    Mengunduh model jika belum ada.
    
    Args:
        model_name (str): Nama model yang akan diunduh
        callback (function, optional): Fungsi callback untuk progress download
        
    Returns:
        bool: True jika berhasil, False jika gagal
    """
    if model_name not in MODELS:
        print(f"Model {model_name} tidak ditemukan")
        return False
        
    model_path = os.path.join(MODEL_DIR, MODEL_FILENAMES[model_name])
    
    # Cek apakah model sudah ada
    if os.path.exists(model_path):
        print(f"Model {model_name} sudah ada di {model_path}")
        return True
        
    # Cek apakah model sedang diunduh
    with download_lock:
        if model_name in current_downloads:
            print(f"Model {model_name} sedang diunduh...")
            return False
        else:
            current_downloads[model_name] = True
    
    # Mulai proses unduhan
    url = MODELS[model_name]
    try:
        print(f"Mengunduh model {model_name} dari {url}...")
        
        # Buat direktori temporary untuk unduhan
        temp_path = model_path + ".download"
        
        # Unduh file
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            downloaded = 0
            
            with open(temp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Hitung dan panggil callback
                        if callback and total_size:
                            progress = (downloaded / total_size) * 100
                            callback(model_name, progress)
            
            # Rename file jika unduhan selesai
            shutil.move(temp_path, model_path)
            
            print(f"Model {model_name} berhasil diunduh ke {model_path}")
            
            with download_lock:
                if model_name in current_downloads:
                    del current_downloads[model_name]
                    
            return True
            
    except Exception as e:
        print(f"Gagal mengunduh model {model_name}: {str(e)}")
        
        # Hapus file unduhan yang tidak lengkap
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
        with download_lock:
            if model_name in current_downloads:
                del current_downloads[model_name]
                
        return False

# Fungsi deteksi wajah dihapus karena tidak lagi diperlukan dengan satu model default

def identify_best_model(image_path):
    """
    Selalu mengembalikan model default.
    
    Args:
        image_path (str): Path ke gambar yang akan diproses (tidak digunakan)
        
    Returns:
        str: Nama model default
    """
    print(f"Menggunakan model default: {DEFAULT_MODEL}")
    return DEFAULT_MODEL

def prepare_model(image_path=None, model_name=None, callback=None):
    """
    Mempersiapkan model default dan mengunduh jika perlu.
    Versi sederhana yang hanya menggunakan satu model default.
    
    Args:
        image_path (str, optional): Path ke gambar yang akan diproses (tidak digunakan)
        model_name (str, optional): Nama model spesifik (diabaikan, selalu menggunakan default)
        callback (function, optional): Fungsi callback untuk progress download
        
    Returns:
        str: Nama model default yang siap digunakan
    """
    # Selalu gunakan model default
    model_name = DEFAULT_MODEL
        
    # Verifikasi apakah model ada di path
    model_file_path = os.path.join(MODEL_DIR, MODEL_FILENAMES.get(model_name, f"{model_name}.onnx"))
    print(f"Mencari model di: {model_file_path}")
    
    if os.path.exists(model_file_path):
        print(f"Model {model_name} sudah ada di {model_file_path}")
        return model_name
        
    # Download model jika belum ada
    print(f"Model {model_name} tidak ditemukan, mengunduh...")
    success = download_model(model_name, callback)
    
    if not success:
        print(f"PERINGATAN: Gagal mengunduh model {model_name}")
            
    return model_name

def set_model_path():
    """
    Set environment variable untuk lokasi model rembg.
    
    Returns:
        str: Path direktori model
    """
    os.environ["U2NET_HOME"] = MODEL_DIR
    
    # Tambahkan debugging untuk verifikasi folder model
    print(f"Path model set ke: {MODEL_DIR}")
    print(f"U2NET_HOME environment variable: {os.environ.get('U2NET_HOME')}")
    
    # Verifikasi apakah folder model ada
    if not os.path.exists(MODEL_DIR):
        print(f"Membuat direktori model: {MODEL_DIR}")
        os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Periksa apakah sudah ada model di folder
    models_found = [f for f in os.listdir(MODEL_DIR) if f.endswith('.onnx')]
    if models_found:
        print(f"Model yang ditemukan: {', '.join(models_found)}")
    else:
        print("Tidak ada model yang ditemukan di folder model")
        print(f"Model default akan diunduh otomatis: {DEFAULT_MODEL}")
    
    return MODEL_DIR

# Set model path saat modul diimpor
set_model_path()
