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
    
    # Improved GPU detection with multiple methods
    gpu_detected = False
    gpu_info = "Unknown"
    cuda_missing_dlls = []
    
    # Check if CUDA DLLs are available before attempting to use GPU
    required_cuda_dlls = [
        'cublas64_12.dll',
        'cublasLt64_12.dll',
        'cudart64_12.dll',
        'cudnn64_8.dll',
        'cudnn_ops_infer64_8.dll',
        'cudnn_cnn_infer64_8.dll'
    ]
    
    # Function to check if a DLL can be found in system path
    def check_dll(dll_name):
        # Check in common locations
        for path_dir in os.environ["PATH"].split(os.pathsep):
            dll_path = os.path.join(path_dir, dll_name)
            if os.path.exists(dll_path):
                return True
        return False
    
    # Check each required DLL
    for dll in required_cuda_dlls:
        if not check_dll(dll):
            cuda_missing_dlls.append(dll)
    
    if cuda_missing_dlls:
        print(f"\n⚠️ PERINGATAN: CUDA DLL berikut tidak ditemukan: {', '.join(cuda_missing_dlls)}")
        print("GPU mungkin tidak bisa digunakan tanpa file-file ini.")
        print("Solusi: Install NVIDIA CUDA 12.x dan cuDNN 8.x")
    
    # Method 1: Using PyTorch
    try:
        import torch
        has_gpu = torch.cuda.is_available()
        
        if has_gpu:
            gpu_detected = True
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0)
            gpu_info = f"{gpu_name} (Total: {gpu_count})"
            print(f"GPU terdeteksi via PyTorch: {gpu_info}")
        else:
            print("PyTorch tidak mendeteksi GPU")
    except ImportError:
        print("PyTorch tidak terinstall, mencoba metode deteksi lain")
    
    # Method 2: Using NVIDIA SMI if available
    if not gpu_detected:
        try:
            nvidia_smi_output = os.popen('nvidia-smi -L').read()
            if nvidia_smi_output and "GPU" in nvidia_smi_output:
                gpu_info = nvidia_smi_output.strip()
                print(f"GPU terdeteksi via nvidia-smi: {gpu_info}")
                gpu_detected = True
        except:
            print("nvidia-smi tidak tersedia atau error")
    
    # Method 3: Check ONNX Runtime providers
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        print(f"ONNX Runtime providers tersedia: {providers}")
        
        if 'CUDAExecutionProvider' in providers:
            print("CUDA execution provider tersedia untuk ONNX")
            
            # Try to actually initialize a CUDA provider to verify DLL loading works
            try:
                # Create a very small test model
                import numpy as np
                from onnxruntime import InferenceSession, SessionOptions
                
                # Create a minimal ONNX model in memory
                import io
                from onnx import helper, TensorProto, numpy_helper
                import onnx
                
                # Create a simple identity model
                X = helper.make_tensor_value_info('X', TensorProto.FLOAT, [1])
                Y = helper.make_tensor_value_info('Y', TensorProto.FLOAT, [1])
                node = helper.make_node('Identity', ['X'], ['Y'])
                graph = helper.make_graph([node], 'test', [X], [Y])
                model = helper.make_model(graph)
                
                model_bytes = io.BytesIO()
                onnx.save_model(model, model_bytes)
                model_bytes.seek(0)
                
                # Try to load with CUDA provider
                options = SessionOptions()
                try:
                    sess = InferenceSession(model_bytes.read(), options, providers=['CUDAExecutionProvider'])
                    # Test run
                    test_input = np.array([1.0], dtype=np.float32)
                    outputs = sess.run(None, {'X': test_input})
                    print("✅ CUDA provider test successful!")
                    gpu_detected = True
                except Exception as e:
                    print(f"❌ CUDA provider test failed: {str(e)}")
                    print("Akan menggunakan CPU sebagai fallback")
                    if "cublas" in str(e).lower() or "cudnn" in str(e).lower():
                        print("\n⚠️ ERROR: CUDA DLL dependencies tidak terpenuhi")
                        print("Pastikan CUDA Toolkit 12.x dan cuDNN 8.x terinstall dengan benar")
                        print("Anda dapat mengunduhnya dari: https://developer.nvidia.com/cuda-downloads")
                        print("Dan: https://developer.nvidia.com/cudnn")
            except Exception as e:
                print(f"Error saat test CUDA provider: {str(e)}")
        else:
            print("CUDA execution provider tidak tersedia untuk ONNX")
            
    except ImportError:
        print("Tidak bisa mengimport onnxruntime")
    
    # Set environment based on detection results
    if gpu_detected and not cuda_missing_dlls:  # Only use GPU if all DLLs are found
        print("\n=== STATUS GPU: TERDETEKSI DAN AKTIF ===")
        print(f"GPU anda ({gpu_info}) akan digunakan")
        os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Use first GPU
        
        # Optimize GPU configuration
        os.environ["ORT_TENSORRT_FP16_ENABLE"] = "1"  # Enable FP16 for faster processing
        os.environ["ORT_TENSORRT_ENGINE_CACHE_ENABLE"] = "1"  # Enable engine caching
        os.environ["ONNX_BACKEND"] = "CUDAExecutionProvider"
        os.environ["OMP_NUM_THREADS"] = "1"  # Limit CPU threads to reduce resource competition
        
        # Explicitly set provider order to ensure GPU is tried first
        if 'ort' in locals():
            try:
                # Create a config file for ONNX Runtime to force GPU usage
                config_path = os.path.join(BASE_DIR, "onnxruntime_gpu.json")
                with open(config_path, "w") as f:
                    f.write('{"session_options": {"execution_mode": 1, "graph_optimization_level": 99, "intra_op_num_threads": 1, "inter_op_num_threads": 1, "execution_provider": "CUDAExecutionProvider"}}')
                
                os.environ["ORT_CONFIG_PATH"] = config_path
                print(f"ONNX Runtime config created at: {config_path}")
            except Exception as e:
                print(f"Warning: Failed to create ONNX config: {str(e)}")
    else:
        print("\n⚠️ STATUS GPU: TIDAK TERDETEKSI ATAU ADA MASALAH DEPENDENCY")
        print("Menggunakan CPU sebagai fallback")
        os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Force CPU usage
        print("Provider diset ke CPU untuk rembg")
    
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

# Define a function to force GPU usage for rembg
def get_gpu_session():
    """
    Returns a session object explicitly configured to use GPU if possible,
    otherwise falls back to CPU.
    
    Returns:
        session: A pre-configured session object for rembg
    """
    try:
        from rembg import new_session
        
        # Check if CUDA DLLs are available
        try:
            import ctypes
            cublas_present = False
            try:
                ctypes.cdll.LoadLibrary("cublasLt64_12.dll")
                cublas_present = True
            except:
                print("⚠️ cublasLt64_12.dll tidak ditemukan - GPU tidak akan digunakan")
                print("Solusi: Install NVIDIA CUDA 12.x")
                return new_session(model_name=DEFAULT_MODEL, providers=["CPUExecutionProvider"])
            
            if not cublas_present:
                return new_session(model_name=DEFAULT_MODEL, providers=["CPUExecutionProvider"])
        except:
            pass
        
        # Get available providers
        import onnxruntime as ort
        available_providers = ort.get_available_providers()
        print(f"Available ONNX providers: {available_providers}")
        
        # Create provider options for better performance
        provider_options = {
            'CUDAExecutionProvider': {
                'device_id': 0,
                'arena_extend_strategy': 'kNextPowerOfTwo',
                'gpu_mem_limit': 2 * 1024 * 1024 * 1024,  # 2GB limit
                'cudnn_conv_algo_search': 'EXHAUSTIVE',
                'do_copy_in_default_stream': True,
            }
        }
        
        # Try to create a session with CUDA provider
        if 'CUDAExecutionProvider' in available_providers:
            try:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
                session = new_session(
                    model_name=DEFAULT_MODEL, 
                    providers=providers,
                    provider_options=[provider_options['CUDAExecutionProvider'], {}]
                )
                print("Created session with CUDA provider")
                
                # Verify session is actually using CUDA
                if hasattr(session, '_session'):
                    actual_providers = session._session.get_providers()
                    print(f"Session providers: {actual_providers}")
                    if 'CUDAExecutionProvider' in actual_providers:
                        print("✅ CONFIRMED: Session is using CUDA provider")
                        return session
                    else:
                        print("⚠️ WARNING: Session not using CUDA despite being available")
                        # Fall back to CPU
            except Exception as e:
                print(f"Error creating GPU session: {str(e)}")
                print("Falling back to CPU provider")
                
        # If we get here, use CPU
        session = new_session(model_name=DEFAULT_MODEL, providers=['CPUExecutionProvider'])
        print("Created session with CPU provider (CUDA failed or unavailable)")
        return session
    
    except Exception as e:
        print(f"Error creating any session: {str(e)}")
        try:
            # Last resort fallback
            from rembg import new_session
            return new_session(model_name=DEFAULT_MODEL)
        except:
            return None

# Set model path saat modul diimpor
set_model_path()