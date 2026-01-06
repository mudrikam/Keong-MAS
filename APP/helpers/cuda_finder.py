"""
Smart CUDA and cuDNN Path Finder
Automatically detects CUDA toolkit and cuDNN installation paths on the system.
"""

import os
import sys
from pathlib import Path


def find_cuda_paths():
    """
    Smart detection of CUDA toolkit installation paths.
    
    Returns:
        dict: Dictionary containing 'cuda_bin', 'cuda_version', 'found' status
    """
    cuda_info = {
        'cuda_bin': None,
        'cuda_version': None,
        'found': False
    }
    
    # Strategy 1: Check CUDA_PATH environment variable (set by CUDA installer)
    cuda_path = os.environ.get('CUDA_PATH')
    if cuda_path and os.path.isdir(cuda_path):
        bin_path = os.path.join(cuda_path, 'bin')
        if os.path.isdir(bin_path):
            # Extract version from path (e.g., "v12.8" -> "12.8")
            try:
                version = os.path.basename(cuda_path).replace('v', '')
                cuda_info['cuda_bin'] = bin_path
                cuda_info['cuda_version'] = version
                cuda_info['found'] = True
                return cuda_info
            except:
                pass
    
    # Strategy 2: Check CUDA_PATH_V* environment variables (multiple versions)
    for key in os.environ:
        if key.startswith('CUDA_PATH_V'):
            cuda_path = os.environ[key]
            if os.path.isdir(cuda_path):
                bin_path = os.path.join(cuda_path, 'bin')
                if os.path.isdir(bin_path):
                    try:
                        version = key.replace('CUDA_PATH_V', '').replace('_', '.')
                        cuda_info['cuda_bin'] = bin_path
                        cuda_info['cuda_version'] = version
                        cuda_info['found'] = True
                        return cuda_info
                    except:
                        pass
    
    # Strategy 3: Scan common installation directories
    common_base_paths = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA",
        r"C:\CUDA",
        r"C:\Program Files (x86)\NVIDIA GPU Computing Toolkit\CUDA"
    ]
    
    found_versions = []
    
    for base_path in common_base_paths:
        if not os.path.isdir(base_path):
            continue
        
        try:
            # List all version directories (e.g., v12.8, v12.0, v11.8)
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path):
                    bin_path = os.path.join(item_path, 'bin')
                    if os.path.isdir(bin_path):
                        # Extract version number
                        version = item.replace('v', '')
                        found_versions.append({
                            'bin': bin_path,
                            'version': version,
                            'version_tuple': tuple(map(int, version.split('.'))) if '.' in version else (0,)
                        })
        except Exception as e:
            continue
    
    # Select the highest version found
    if found_versions:
        found_versions.sort(key=lambda x: x['version_tuple'], reverse=True)
        latest = found_versions[0]
        cuda_info['cuda_bin'] = latest['bin']
        cuda_info['cuda_version'] = latest['version']
        cuda_info['found'] = True
    
    return cuda_info


def find_cudnn_paths():
    """
    Smart detection of cuDNN installation paths.
    
    Returns:
        dict: Dictionary containing 'cudnn_bin', 'cudnn_version', 'cuda_version', 'found' status
    """
    cudnn_info = {
        'cudnn_bin': None,
        'cudnn_version': None,
        'cuda_version': None,
        'found': False
    }
    
    # Strategy 1: Check CUDNN_PATH environment variable (if set by user)
    cudnn_path = os.environ.get('CUDNN_PATH')
    if cudnn_path and os.path.isdir(cudnn_path):
        bin_path = os.path.join(cudnn_path, 'bin')
        if os.path.isdir(bin_path):
            cudnn_info['cudnn_bin'] = bin_path
            cudnn_info['found'] = True
            return cudnn_info
    
    # Strategy 2: Scan common installation directories
    common_base_paths = [
        r"C:\Program Files\NVIDIA\CUDNN",
        r"C:\CUDNN",
        r"C:\Program Files (x86)\NVIDIA\CUDNN",
        r"C:\tools\cuda",  # Chocolatey installation path
    ]
    
    found_versions = []
    
    for base_path in common_base_paths:
        if not os.path.isdir(base_path):
            continue
        
        try:
            # Scan for cuDNN version directories (e.g., v9.5, v8.9)
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path):
                    # cuDNN often has structure: v9.5/bin/12.6 or v9.5/bin
                    bin_path = os.path.join(item_path, 'bin')
                    
                    # Check if bin exists directly
                    if os.path.isdir(bin_path):
                        # Check if there are CUDA version subdirectories (e.g., 12.6, 11.8)
                        cuda_subdirs = []
                        try:
                            for subitem in os.listdir(bin_path):
                                subitem_path = os.path.join(bin_path, subitem)
                                if os.path.isdir(subitem_path):
                                    # Check if this looks like a CUDA version (e.g., "12.6")
                                    if '.' in subitem and subitem.replace('.', '').isdigit():
                                        cuda_subdirs.append({
                                            'path': subitem_path,
                                            'cuda_version': subitem,
                                            'version_tuple': tuple(map(int, subitem.split('.')))
                                        })
                        except:
                            pass
                        
                        if cuda_subdirs:
                            # Use the highest CUDA version subdirectory
                            cuda_subdirs.sort(key=lambda x: x['version_tuple'], reverse=True)
                            latest_cuda = cuda_subdirs[0]
                            
                            cudnn_version = item.replace('v', '')
                            found_versions.append({
                                'bin': latest_cuda['path'],
                                'cudnn_version': cudnn_version,
                                'cuda_version': latest_cuda['cuda_version'],
                                'cudnn_tuple': tuple(map(int, cudnn_version.split('.'))) if '.' in cudnn_version else (0,),
                                'cuda_tuple': latest_cuda['version_tuple']
                            })
                        else:
                            # No CUDA subdirectories, use bin directly
                            cudnn_version = item.replace('v', '')
                            found_versions.append({
                                'bin': bin_path,
                                'cudnn_version': cudnn_version,
                                'cuda_version': None,
                                'cudnn_tuple': tuple(map(int, cudnn_version.split('.'))) if '.' in cudnn_version else (0,),
                                'cuda_tuple': (0,)
                            })
        except Exception as e:
            continue
    
    # Select the highest cuDNN version found
    if found_versions:
        # Sort by cuDNN version first, then CUDA version
        found_versions.sort(key=lambda x: (x['cudnn_tuple'], x['cuda_tuple']), reverse=True)
        latest = found_versions[0]
        cudnn_info['cudnn_bin'] = latest['bin']
        cudnn_info['cudnn_version'] = latest['cudnn_version']
        cudnn_info['cuda_version'] = latest['cuda_version']
        cudnn_info['found'] = True
    
    return cudnn_info


def setup_cuda_environment():
    """
    Smart setup of CUDA and cuDNN environment.
    Automatically detects and configures paths.
    
    Returns:
        dict: Summary of detected paths and setup status
    """
    summary = {
        'cuda': find_cuda_paths(),
        'cudnn': find_cudnn_paths(),
        'configured': False
    }
    
    paths_to_add = []
    
    # Add CUDA bin to PATH if found
    if summary['cuda']['found']:
        cuda_bin = summary['cuda']['cuda_bin']
        paths_to_add.append(cuda_bin)
        
        # Also add to DLL directory if supported (Windows 10+)
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(cuda_bin)
            except:
                pass
    
    # Add cuDNN bin to PATH if found
    if summary['cudnn']['found']:
        cudnn_bin = summary['cudnn']['cudnn_bin']
        paths_to_add.append(cudnn_bin)
        
        # Also add to DLL directory if supported
        if hasattr(os, 'add_dll_directory'):
            try:
                os.add_dll_directory(cudnn_bin)
            except:
                pass
    
    # Prepend to PATH
    if paths_to_add:
        current_path = os.environ.get('PATH', '')
        new_path = os.pathsep.join(paths_to_add + [current_path])
        os.environ['PATH'] = new_path
        summary['configured'] = True
    
    return summary


def print_cuda_summary(summary=None):
    """
    Print a user-friendly summary of CUDA/cuDNN detection.
    
    Args:
        summary (dict, optional): Summary from setup_cuda_environment()
    """
    if summary is None:
        summary = {
            'cuda': find_cuda_paths(),
            'cudnn': find_cudnn_paths(),
            'configured': False
        }
    
    print("=" * 60)
    print("CUDA/cuDNN Detection Summary")
    print("=" * 60)
    
    # CUDA Status
    if summary['cuda']['found']:
        print(f"✓ CUDA Toolkit: Found v{summary['cuda']['cuda_version']}")
        print(f"  Path: {summary['cuda']['cuda_bin']}")
    else:
        print("✗ CUDA Toolkit: Not found")
        print("  GPU acceleration will not be available.")
    
    # cuDNN Status
    if summary['cudnn']['found']:
        cudnn_ver = summary['cudnn']['cudnn_version']
        cuda_ver = summary['cudnn']['cuda_version']
        if cuda_ver:
            print(f"✓ cuDNN: Found v{cudnn_ver} (for CUDA {cuda_ver})")
        else:
            print(f"✓ cuDNN: Found v{cudnn_ver}")
        print(f"  Path: {summary['cudnn']['cudnn_bin']}")
    else:
        print("✗ cuDNN: Not found")
        print("  Some GPU operations may be slower or unavailable.")
    
    # Overall Status
    print()
    if summary['cuda']['found'] and summary['cudnn']['found']:
        print("✓ GPU acceleration fully available!")
    elif summary['cuda']['found']:
        print("⚠ GPU acceleration partially available (cuDNN missing)")
    else:
        print("ℹ No GPU acceleration (will use CPU)")
    
    print("=" * 60)


if __name__ == "__main__":
    # Test the detection
    summary = setup_cuda_environment()
    print_cuda_summary(summary)
