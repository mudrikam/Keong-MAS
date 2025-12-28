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
os.makedirs(MODEL_DIR, exist_ok=True)  # model storage directory (created if missing)

# Daftar model dan URL unduhan (hanya model default)
DEFAULT_MODEL = "isnet-general-use"
MODELS = {
    # Default general model
    DEFAULT_MODEL: "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx",
    # Other common u2net variants that rembg's releases often provide
    "u2net": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx",
    "u2netp": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx",
    "u2net_human_seg": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx",
    "u2net_cloth_seg": "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_cloth_seg.onnx",
    # Note: URLs may vary by release; add or override entries as needed
}

# Model filename mapping
MODEL_FILENAMES = {
    DEFAULT_MODEL: "isnet-general-use.onnx",
    "u2net": "u2net.onnx",
    "u2netp": "u2netp.onnx",
    "u2net_human_seg": "u2net_human_seg.onnx",
    "u2net_cloth_seg": "u2net_cloth_seg.onnx",
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
                # Throttle callbacks to avoid overwhelming UI thread
                import time
                last_emit_time = 0.0
                last_progress = 0.0

                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Hitung dan panggil callback hanya jika ada perubahan signifikan
                        if callback and total_size:
                            progress = (downloaded / total_size) * 100
                            now = time.monotonic()

                            # Emit when progress increased by >=0.5% OR at least 0.15s passed
                            if (progress - last_progress) >= 0.5 or (now - last_emit_time) >= 0.15 or progress >= 99.9:
                                try:
                                    callback(model_name, progress)
                                except Exception:
                                    pass
                                last_emit_time = now
                                last_progress = progress

            # Rename file jika unduhan selesai
            shutil.move(temp_path, model_path)

            # Emit final callback 100% to ensure UI reaches completion
            try:
                if callback:
                    callback(model_name, 100.0)
            except Exception:
                pass
            
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
    return DEFAULT_MODEL


GITHUB_RELEASE_API_URL = "https://api.github.com/repos/danielgatis/rembg/releases/tags/v0.0.0"


_fetched_once = False
CACHE_PATH = os.path.join(MODEL_DIR, "models_cache.json")


def _save_models_cache():
    """Save current MODELS and MODEL_FILENAMES to a local cache JSON file."""
    try:
        payload = {
            'models': MODELS,
            'filenames': MODEL_FILENAMES
        }
        with open(CACHE_PATH, 'w', encoding='utf-8') as f:
            import json
            json.dump(payload, f, indent=2, ensure_ascii=False)
        # Cache saved (silent)
    except Exception as e:
        print(f"Warning: failed to save models cache: {str(e)}")


def _load_models_cache():
    """Load models and filenames from local cache if present and merge into runtime dicts."""
    try:
        if not os.path.exists(CACHE_PATH):
            return {}
        import json
        with open(CACHE_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        models = payload.get('models', {}) or {}
        filenames = payload.get('filenames', {}) or {}

        if models:
            MODELS.update(models)
        if filenames:
            MODEL_FILENAMES.update(filenames)

        return models
    except Exception as e:
        print(f"Warning: failed to load models cache: {str(e)}")
        return {}


def fetch_models_from_github(force=False):
    """Fetch ONNX asset list from the rembg GitHub release and return mapping name->url.

    Uses a simple in-memory cache to avoid repeated API calls, and falls back to a
    local cache file if GitHub is unreachable.

    Args:
        force (bool): If True, force a re-fetch even if already fetched.

    Returns:
        dict: {model_key: download_url}
    """
    global _fetched_once
    if _fetched_once and not force:
        return {}

    try:
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'Keong-MAS'
        }
        resp = requests.get(GITHUB_RELEASE_API_URL, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        assets = data.get('assets', [])
        found = {}
        for asset in assets:
            name = asset.get('name', '')
            url = asset.get('browser_download_url')
            if name.lower().endswith('.onnx') and url:
                key = os.path.splitext(name)[0]
                found[key] = url
                # update filename mapping so download_model knows the filename
                MODEL_FILENAMES[key] = name

        if found:
            # Merge into MODELS (runtime)
            MODELS.update(found)
            _fetched_once = True
            # Persist cache for offline use
            _save_models_cache()
            # Fetch completed (silent): results merged into MODELS

    except Exception as e:
        print(f"Warning: failed to fetch model list from GitHub: {str(e)}")
        # Attempt to load from local cache when network fails
        cached = _load_models_cache()
        if cached:
            _fetched_once = True
            return cached

    return {}


def get_available_models():
    """Return a list of available model names (keys of MODELS dict).
    Tries to fetch from GitHub release once and caches results in MODELS.
    If fetching fails, attempts to load from local cache to provide offline availability.
    Returns a sorted list for predictable ordering.
    """
    # Attempt to fetch dynamically; if network fails, fetch_models_from_github will try cache
    fetch_models_from_github()

    # As a fallback, if MODELS only contains the DEFAULT_MODEL, try loading cache explicitly
    if len(MODELS) <= 1:
        _load_models_cache()

    # Return a stable sorted list
    return sorted(MODELS.keys(), key=lambda s: s.lower())


def prepare_model(image_path=None, model_name=None, callback=None):
    """
    Mempersiapkan model yang diminta dan mengunduh jika perlu.
    Jika model_name tidak diberikan, gunakan default.
    
    Args:
        image_path (str, optional): Path ke gambar yang akan diproses (tidak digunakan)
        model_name (str, optional): Nama model spesifik
        callback (function, optional): Fungsi callback untuk progress download
        
    Returns:
        str: Nama model yang siap digunakan
    """
    # Gunakan parameter jika diberikan, jika tidak gunakan default
    if model_name is None:
        model_name = DEFAULT_MODEL
        
    # Verifikasi apakah model ada di path
    model_file_path = os.path.join(MODEL_DIR, MODEL_FILENAMES.get(model_name, f"{model_name}.onnx"))
    
    if os.path.exists(model_file_path):
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

    # Ensure model directory exists
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR, exist_ok=True)

    # Minimal status: report model path and availability
    models_found = [f for f in os.listdir(MODEL_DIR) if f.endswith('.onnx')]
    
    return MODEL_DIR

# Set model path saat modul diimpor
set_model_path()
