from __future__ import annotations
import os
import sys
import traceback
from typing import Dict, Any

# Predictable paths based on standard NVIDIA installer locations
CUDA_BIN = r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8\bin"
CUDNN_BIN = r"C:\Program Files\NVIDIA\CUDNN\v9.5\bin\12.6"

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
        # Add CUDA bin to DLL search path
        if os.path.isdir(CUDA_BIN):
            added_cuda = _add_dll_directory(CUDA_BIN)
            result['messages'].append(f'Added CUDA bin to DLL search path: {added_cuda}')
            if added_cuda:
                result['changed'] = True
            # Set CUDA environment variables
            os.environ['CUDA_PATH'] = CUDA_BIN
            result['messages'].append(f'Set CUDA_PATH to {CUDA_BIN}')
        else:
            result['messages'].append('CUDA bin not found - using CPU')

        # Add cuDNN bin to DLL search path
        if os.path.isdir(CUDNN_BIN):
            added_cudnn = _add_dll_directory(CUDNN_BIN)
            result['messages'].append(f'Added cuDNN bin to DLL search path: {added_cudnn}')
            if added_cudnn:
                result['changed'] = True
            # Set cuDNN environment variables
            os.environ['CUDNN_PATH'] = CUDNN_BIN
            result['messages'].append(f'Set CUDNN_PATH to {CUDNN_BIN}')
        else:
            result['messages'].append('cuDNN bin not found - using CPU')

        # Try to create rembg CUDA session only if both CUDA and cuDNN are available
        if os.path.isdir(CUDA_BIN) and os.path.isdir(CUDNN_BIN):
            ok, info = _try_create_rembg_cuda_session()
            result['ok'] = ok
            result['messages'].append(f'CUDA session check: ok={ok}, info={info}')
        else:
            result['messages'].append('CUDA/cuDNN not fully installed - using CPU')

    except Exception as e:
        result['error'] = traceback.format_exc()
    return result
