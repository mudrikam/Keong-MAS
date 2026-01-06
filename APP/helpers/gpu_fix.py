from __future__ import annotations
import os
import sys
import traceback
from typing import Dict, Any


def _ensure_path_entry(path: str) -> bool:
    """Ensure the path is present in the process PATH (idempotent).

    Returns True if PATH was modified.
    """
    p = os.environ.get('PATH', '')
    if path in p:
        return False
    os.environ['PATH'] = path + os.pathsep + p
    return True

def get_cuda_paths():
    """Get CUDA and cuDNN paths using smart detection.
    
    Returns:
        tuple: (cuda_bin, cudnn_bin) or (None, None) if not found
    """
    try:
        from APP.helpers.cuda_finder import find_cuda_paths, find_cudnn_paths
        cuda_info = find_cuda_paths()
        cudnn_info = find_cudnn_paths()
        
        cuda_bin = cuda_info['cuda_bin'] if cuda_info['found'] else None
        cudnn_bin = cudnn_info['cudnn_bin'] if cudnn_info['found'] else None
        
        return cuda_bin, cudnn_bin
    except Exception:
        # Fallback to None if detection fails
        return None, None

def is_cuda_available():
    """Check if CUDA with cuDNN is available using smart detection."""
    cuda_bin, cudnn_bin = get_cuda_paths()
    
    if not cuda_bin or not cudnn_bin:
        return False
    
    # Check if paths actually exist
    cuda_exists = os.path.isdir(cuda_bin)
    cudnn_exists = os.path.isdir(cudnn_bin)
    
    if not cuda_exists or not cudnn_exists:
        return False
    
    # Try to find and load cuDNN DLL
    try:
        # Common cuDNN DLL names
        cudnn_dll_names = ['cudnn64_9.dll', 'cudnn64_8.dll', 'cudnn_ops_infer64_9.dll', 'cudnn_ops_infer64_8.dll']
        
        for dll_name in cudnn_dll_names:
            cudnn_dll = os.path.join(cudnn_bin, dll_name)
            if os.path.exists(cudnn_dll):
                try:
                    import ctypes
                    ctypes.windll.LoadLibrary(cudnn_dll)
                    return True
                except:
                    continue
    except:
        pass
    
    # If DLL loading failed, still return True if paths exist
    # (ONNX Runtime might handle DLL loading differently)
    return cuda_exists and cudnn_exists

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
    """Set up CUDA and cuDNN access using smart detection.

    Returns a dict with keys:
      - ok: bool (True if CUDA provider usable)
      - changed: bool (True if we modified PATH or env vars)
      - messages: list[str]
      - error: optional error string
    """
    result: Dict[str, Any] = {'ok': False, 'changed': False, 'messages': [], 'error': None}
    
    try:
        # Get CUDA and cuDNN paths using smart detection
        cuda_bin, cudnn_bin = get_cuda_paths()
        
        if not cuda_bin and not cudnn_bin:
            result['messages'].append('No CUDA/cuDNN found via smart detection - will use CPU')
            result['ok'] = False
            return result
        
        # Setup CUDA bin if found
        if cuda_bin and os.path.isdir(cuda_bin):
            try:
                added_cuda = _add_dll_directory(cuda_bin)
                path_added = _ensure_path_entry(cuda_bin) if not added_cuda else False
                if added_cuda or path_added:
                    result['changed'] = True
                result['messages'].append(f'Ensured CUDA bin: {cuda_bin} (add_dll={added_cuda}, path={path_added})')
                os.environ.setdefault('CUDA_PATH', os.path.dirname(cuda_bin))  # Set to parent dir
            except Exception as e:
                result['messages'].append(f'Failed to ensure CUDA bin: {e}')
        else:
            result['messages'].append('CUDA not found - skipping CUDA setup')
        
        # Setup cuDNN bin if found
        if cudnn_bin and os.path.isdir(cudnn_bin):
            try:
                added_cudnn = _add_dll_directory(cudnn_bin)
                cudnn_path_added = _ensure_path_entry(cudnn_bin) if not added_cudnn else False
                if added_cudnn or cudnn_path_added:
                    result['changed'] = True
                result['messages'].append(f'Ensured cuDNN bin: {cudnn_bin} (add_dll={added_cudnn}, path={cudnn_path_added})')
                os.environ.setdefault('CUDNN_PATH', os.path.dirname(cudnn_bin))  # Set to parent dir
            except Exception as e:
                result['messages'].append(f'Failed to ensure cuDNN bin: {e}')
        else:
            result['messages'].append('cuDNN not found - some GPU operations may be slower')

        # Attempt to create a rembg session to verify provider availability
        ok, info = _try_create_rembg_cuda_session()
        result['ok'] = ok
        result['messages'].append(f'GPU session check: ok={ok}, info={info}')
        
        if not cuda_bin or not cudnn_bin:
            result['messages'].append('Note: Not all GPU components found - will fallback to CPU if needed')

    except Exception as e:
        result['error'] = traceback.format_exc()
        result['messages'].append(f'Exception during setup: {e}')
    
    return result
