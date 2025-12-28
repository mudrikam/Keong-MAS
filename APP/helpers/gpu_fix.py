from __future__ import annotations
import os
import sys
import traceback
from typing import Dict, Any

# Predictable paths based on standard NVIDIA installer locations
CUDA_BIN = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin"
# cuDNN is normally placed in the 'bin' directory; previous value included an extra subfolder ('12.6') which may be incorrect.
CUDNN_BIN = r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin"


def _ensure_path_entry(path: str) -> bool:
    """Ensure the path is present in the process PATH (idempotent).

    Returns True if PATH was modified.
    """
    p = os.environ.get('PATH', '')
    if path in p:
        return False
    os.environ['PATH'] = path + os.pathsep + p
    return True

def is_cuda_available():
    """Check if CUDA with cuDNN is available at predictable locations."""
    # First check if CUDA and cuDNN are installed in expected locations
    cuda_exists = os.path.isdir(CUDA_BIN)
    cudnn_exists = os.path.isdir(CUDNN_BIN)
    
    if not cuda_exists or not cudnn_exists:
        return False
    
    # If both exist, try to load cuDNN DLL
    cudnn_dll = os.path.join(CUDNN_BIN, 'cudnn64_9.dll')
    if os.path.exists(cudnn_dll):
        try:
            import ctypes
            ctypes.windll.LoadLibrary(cudnn_dll)
            return True
        except:
            pass
    return False

def has_nvidia_gpu():
    """Check if system has NVIDIA GPU."""
    gpu_names = get_gpu_names()
    return any('nvidia' in name.lower() or 'rtx' in name.lower() or 'gtx' in name.lower() or 'quadro' in name.lower() for name in gpu_names)

def get_gpu_names():
    """Get list of GPU names in the system."""
    gpu_names = []
    
    try:
        # Method 1: Use WMIC to get GPU names
        import subprocess
        result = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 'name'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # Skip header
                name = line.strip()
                if name:
                    gpu_names.append(name)
    except:
        pass
    
    try:
        # Method 2: Use PowerShell to get GPU names
        import subprocess
        result = subprocess.run(['powershell', '-Command', 'Get-WmiObject Win32_VideoController | Select-Object -ExpandProperty Name'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                name = line.strip()
                if name and name not in gpu_names:
                    gpu_names.append(name)
    except:
        pass
    
    return gpu_names

def _add_dll_directory(path: str) -> bool:
    try:
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(path)
            return True
    except Exception:
        pass
    # As a fallback, prepend to PATH for this process only
    try:
        os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
        return True
    except Exception:
        return False

def get_available_ort_providers() -> list:
    """Return list of providers available according to ONNX Runtime."""
    try:
        import onnxruntime as ort
        return ort.get_available_providers()
    except Exception:
        return []


def detect_best_provider() -> str:
    """Detect the best available hardware provider.

    Priority: CUDAExecutionProvider > DmlExecutionProvider > ROCmExecutionProvider > CPUExecutionProvider
    """
    providers = get_available_ort_providers()
    priority = ['CUDAExecutionProvider', 'DmlExecutionProvider', 'ROCMExecutionProvider']
    for p in priority:
        if p in providers:
            return p
    return 'CPUExecutionProvider'


def get_provider_list() -> list:
    """Return a providers list suitable to pass to ONNX Runtime session creation.

    Returns empty list for CPU (i.e., let rembg pick default CPU provider).
    """
    best = detect_best_provider()
    if best == 'CPUExecutionProvider':
        return []
    return [best]


def _try_create_rembg_cuda_session() -> tuple[bool, str]:
    try:
        # Try to create a session using the best available provider (if any)
        providers = get_provider_list()
        import rembg
        try:
            sess = rembg.new_session('isnet-general-use', providers=providers) if providers else rembg.new_session('isnet-general-use')
        except TypeError:
            sess = rembg.new_session('isnet-general-use')
        try:
            provs = getattr(sess._sess, 'get_providers', lambda: None)()
            return ((providers == [] and 'CPUExecutionProvider' in (provs or [])) or (providers and providers[0] in (provs or [])), f'providers={provs}')
        except Exception:
            return True, 'session created (could not inspect providers)'
    except Exception as e:
        return False, traceback.format_exc()

def ensure_cuda_accessible() -> Dict[str, Any]:
    """Set up CUDA and cuDNN access using predictable installation paths.

    Returns a dict with keys:
      - ok: bool (True if CUDA provider usable)
      - changed: bool (True if we modified PATH or env vars)
      - messages: list[str]
      - error: optional error string
    """
    result: Dict[str, Any] = {'ok': False, 'changed': False, 'messages': [], 'error': None}
    try:
        # Force-ensure CUDA bin on DLL search path and PATH so the process has a chance to find required DLLs
        try:
            added_cuda = _add_dll_directory(CUDA_BIN)
            # _add_dll_directory returns False if it fell back to PATH or failed; ensure PATH contains it explicitly
            path_added = _ensure_path_entry(CUDA_BIN) if not added_cuda else False
            if added_cuda or path_added:
                result['changed'] = True
            result['messages'].append(f'Ensured CUDA bin on DLL search path / PATH: add_dll={added_cuda}, path_added={path_added}')
            os.environ.setdefault('CUDA_PATH', CUDA_BIN)
            result['messages'].append(f'Set CUDA_PATH to {CUDA_BIN}')
        except Exception as e:
            result['messages'].append(f'Failed to ensure CUDA bin: {e}')

        # Force-ensure cuDNN bin on DLL search path and PATH
        try:
            added_cudnn = _add_dll_directory(CUDNN_BIN)
            cudnn_path_added = _ensure_path_entry(CUDNN_BIN) if not added_cudnn else False
            if added_cudnn or cudnn_path_added:
                result['changed'] = True
            result['messages'].append(f'Ensured cuDNN bin on DLL search path / PATH: add_dll={added_cudnn}, path_added={cudnn_path_added}')
            os.environ.setdefault('CUDNN_PATH', CUDNN_BIN)
            result['messages'].append(f'Set CUDNN_PATH to {CUDNN_BIN}')
        except Exception as e:
            result['messages'].append(f'Failed to ensure cuDNN bin: {e}')

        # Attempt to create a rembg session regardless of whether the predicted directories physically exist.
        # This lets us detect provider availability even if the DLLs are found via other mechanisms or the PATH we just added.
        ok, info = _try_create_rembg_cuda_session()
        result['ok'] = ok
        result['messages'].append(f'CUDA session check: ok={ok}, info={info}')
        if not os.path.isdir(CUDA_BIN) or not os.path.isdir(CUDNN_BIN):
            result['messages'].append('Note: one or both predicted CUDA/cuDNN directories do not exist on disk; we forced them into the process PATH to help discovery.')

    except Exception as e:
        result['error'] = traceback.format_exc()
    return result
