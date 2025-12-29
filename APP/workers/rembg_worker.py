import os
import time
import queue
import threading
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QObject, Signal
# import rembg  # Moved to inside functions to avoid early loading

from APP.helpers import model_manager
from APP.helpers.config_manager import (
    get_save_mask_enabled, get_auto_crop_enabled, get_unified_margin, get_solid_bg_enabled,
    get_selected_model, get_levels_black_point, get_levels_mid_point, get_levels_white_point
)

from APP.helpers.image_utils import enhance_transparency_with_levels, cleanup_original_temp_files
from APP.helpers.image_crop import crop_transparent_image
from APP.helpers.solid_background import add_solid_background
from APP.helpers.jpg_converter import process_jpg_conversion


class RemBgWorker(QObject):
    """Worker for processing background removal in a separate thread."""
    
    progress = Signal(int, str, str)
    finished = Signal(float, int)
    file_completed = Signal(str)
    status_update = Signal(str)
    # Signal for model download progress: (model_name, progress_percent)
    download_progress = Signal(str, float)

    SUPPORTED_EXTENSIONS = {
        '.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif', 
        '.gif', '.ico', '.ppm', '.pgm', '.pbm', '.pnm', '.pfm',
        '.sgi', '.tga', '.xbm', '.xpm', '.avif', '.heif', '.heic'
    }
    PROCESSING_TIMEOUT = 300
    
    def __init__(self, file_paths, output_dir=None):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.abort = False
        self.start_time = 0
        self.processed_files_count = 0
        self.temp_files_to_cleanup = []  # Track temporary PNG files for cleanup
        
        # Ensure CUDA/cuDNN paths are available for this worker thread using the shared helper
        try:
            from APP.helpers.gpu_fix import ensure_cuda_accessible, get_gpu_names
            res = ensure_cuda_accessible()
            try:
                gpu_list = get_gpu_names()
            except Exception:
                gpu_list = []
            if res.get('ok'):
                print(f"GPU environment check passed (providers detected). GPUs: {', '.join(gpu_list) if gpu_list else 'Unknown'}")
            else:
                print(f"GPU environment check did not confirm usable GPU. Messages: {res.get('messages', [])[:2]}; GPUs: {', '.join(gpu_list) if gpu_list else 'None'}")
        except Exception as e:
            print(f"Warning: failed to run ensure_cuda_accessible in worker init: {e}")

    def _get_providers(self):
        """Get providers list based on available ONNX Runtime providers.

        Prioritizes: CUDA > DML > ROCm > CPU.
        """
        try:
            from APP.helpers.gpu_fix import get_provider_list
            return get_provider_list()
        except Exception:
            return []

    def process_files(self):
        """Process all files in the queue."""
        self.start_time = time.time()
        self.processed_files_count = 0
        total_files = len(self.file_paths)
        processed = 0
        
        for file_path in self.file_paths:
            if self.abort:
                break
                
            try:
                path_obj = Path(file_path)
                
                if path_obj.is_file() and path_obj.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    self.process_image(file_path)
                    processed += 1
                    self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}", None)
                    
                elif path_obj.is_dir():
                    image_files = self._get_image_files_in_dir(file_path)
                    for img_path in image_files:
                        if self.abort:
                            break
                        self.process_image(img_path)
                        processed += 1
                        self.progress.emit(int(processed / total_files * 100), f"File {processed}/{total_files}", None)
                else:
                    processed += 1
                    self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}", None)
                    
            except Exception as e:
                print(f"Error processing {file_path}: {str(e)}")
                processed += 1
                self.progress.emit(int(processed / total_files * 100), f"Selesai: {processed}/{total_files}", None)
        
        processing_time = time.time() - self.start_time
        self.finished.emit(processing_time, self.processed_files_count)
        
    def _get_image_files_in_dir(self, directory):
        """Recursively get all image files in directory, skipping PNG output folders."""
        image_files = []
        for root, dirs, files in os.walk(directory):
            if os.path.basename(root).upper() == "PNG":
                print(f"Skipping PNG output directory: {root}")
                continue
                
            dirs[:] = [d for d in dirs if d.upper() != "PNG"]
            
            for file in files:
                if Path(file).suffix.lower() in self.SUPPORTED_EXTENSIONS:
                    image_files.append(os.path.join(root, file))
        return image_files

    def _convert_to_png_if_needed(self, image_path):
        """
        Convert image to PNG format if it's not already PNG.
        This ensures lossless processing and compatibility with rembg.
        
        Args:
            image_path (str): Path to the input image
            
        Returns:
            tuple: (processed_image_path, needs_cleanup) where processed_image_path is the path to use for processing,
                   and needs_cleanup indicates if the file should be deleted after processing
        """
        input_path = Path(image_path)
        extension = input_path.suffix.lower()
        
        # If already PNG, use as-is
        if extension == '.png':
            return image_path, False
        
        # Check if Pillow can handle this format
        try:
            # Try to open the image to verify it's a valid image format
            with Image.open(image_path) as test_img:
                # If we get here, Pillow can handle it
                pass
        except Exception as e:
            raise ValueError(f"Unsupported or corrupted image format: {image_path} - {str(e)}")
        
        # Create temporary PNG file in the same directory as the original
        temp_dir = os.path.dirname(image_path)
        file_name = input_path.stem
        temp_png_path = os.path.join(temp_dir, f"{file_name}_temp_processing.png")
        
        try:
            # Convert and save as PNG
            with Image.open(image_path) as img:
                # Do NOT apply EXIF transpose here: we want to preserve raw pixel orientation
                # Convert to RGB if necessary (remove alpha channel for non-PNG formats)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # For formats that might have transparency, convert to RGB
                    # This is safe because rembg will add transparency back
                    img = img.convert('RGB')
                
                # Save as PNG with high quality (PNG will not carry EXIF orientation tags)
                img.save(temp_png_path, 'PNG', optimize=False)
            
            # Track for cleanup
            self.temp_files_to_cleanup.append(temp_png_path)
            
            return temp_png_path, True
            
        except Exception as e:
            # If conversion fails, try to clean up any partial file
            if os.path.exists(temp_png_path):
                try:
                    os.remove(temp_png_path)
                except:
                    pass
            raise Exception(f"Failed to convert {image_path} to PNG: {str(e)}")

    def process_image(self, image_path):
        """Process a single image through the background removal pipeline."""
        temp_file_path = None
        try:
            base_output_dir = self.output_dir or os.path.join(os.path.dirname(image_path), 'PNG')
            os.makedirs(base_output_dir, exist_ok=True)
            
            input_path = Path(image_path)
            file_name = input_path.stem
            
            self.progress.emit(5, f"Menyiapkan: {file_name}", image_path)
            
            # Convert to PNG if needed for consistent processing
            try:
                processing_path, is_temp_file = self._convert_to_png_if_needed(image_path)
                if is_temp_file:
                    temp_file_path = processing_path
                    self.progress.emit(8, f"Konversi ke PNG: {os.path.basename(image_path)}", image_path)
            except Exception as e:
                raise Exception(f"Gagal mengkonversi gambar ke PNG: {str(e)}")
            
            self.progress.emit(10, f"Menyiapkan model: {os.path.basename(image_path)}", image_path)
            # Use configured selected model
            try:
                selected_model = get_selected_model()
                self.progress.emit(11, f"Menyiapkan model: {selected_model}", image_path)
                model_name = model_manager.prepare_model(model_name=selected_model, callback=self._download_progress_callback)
            except Exception as e:
                model_name = model_manager.prepare_model(callback=self._download_progress_callback)
            
            self.progress.emit(20, f"Memuat gambar: {os.path.basename(image_path)}", image_path)
            
            # Open image for processing (preserve raw pixel orientation)
            try:
                with Image.open(processing_path) as _img:
                    input_img = _img.copy()
            except Exception as e:
                raise Exception(f"Gagal memuat gambar untuk diproses: {str(e)}")

            output_path, mask_path = self._process_with_rembg(input_img, base_output_dir, file_name, model_name, image_path)
            
            if not output_path:
                return
            
            self.progress.emit(50, f"Menyimpan gambar transparan...", image_path)
            
            enhanced_path = self._enhance_transparency(output_path, mask_path, file_name, base_output_dir, image_path)
            
            if enhanced_path:
                enhanced_path = self._apply_auto_crop(enhanced_path, file_name, base_output_dir, image_path)
                self._apply_solid_background(enhanced_path, image_path)
            
            # Emit completion with ORIGINAL input path, not output path
            self.file_completed.emit(image_path)
            self.processed_files_count += 1
            
        except Exception as e:
            import traceback
            selected_model = locals().get('model_name', None)
            print(f"Error removing background from {image_path} using model {selected_model}: {str(e)}")
            traceback.print_exc()
        
        finally:
            # Clean up temporary PNG file if it was created
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    if temp_file_path in self.temp_files_to_cleanup:
                        self.temp_files_to_cleanup.remove(temp_file_path)
                except Exception as cleanup_error:
                    print(f"Warning: Failed to cleanup temporary file {temp_file_path}: {str(cleanup_error)}")

    def _process_with_rembg(self, input_img, output_dir, file_name, model_name, image_path):
        """Process image with rembg to remove background."""
        try:
            import rembg  # Import here to ensure GPU paths are set up first
        except Exception as e:
            print(f"Failed to import rembg: {e}")
            return None, None  # Can't proceed without rembg
        output_path = os.path.join(output_dir, f"{file_name}.png")
        mask_path = os.path.join(output_dir, f"{file_name}_mask.png")
        
        try:
            result_queue = queue.Queue()
            processing_complete = threading.Event()
            
            def process_with_timeout():
                try:
                    # Prefer creating session using the actual ONNX file path if available
                    model_file = None
                    try:
                        model_file = os.path.join(model_manager.MODEL_DIR, model_manager.MODEL_FILENAMES.get(model_name, f"{model_name}.onnx"))
                    except Exception:
                        model_file = None

                    # Use a local variable inside this nested function to avoid UnboundLocalError
                    selected_model_name = model_name
                    
                    # Check if CUDA/other GPU providers are available and report details
                    gpu_available = False
                    providers = []
                    try:
                        providers = self._get_providers()
                        try:
                            from APP.helpers.gpu_fix import get_gpu_names
                            gpu_names = get_gpu_names()
                        except Exception:
                            gpu_names = []

                        if providers:
                            try:
                                # Use already-imported rembg from outer scope to create a test session
                                test_session = rembg.new_session('isnet-general-use', providers=providers)

                                # Inspect providers from the test session safely (different rembg versions expose providers differently)
                                session_provs = None
                                if hasattr(test_session, 'get_providers'):
                                    try:
                                        session_provs = test_session.get_providers()
                                    except Exception:
                                        session_provs = None
                                elif hasattr(test_session, '_sess') and hasattr(test_session._sess, 'get_providers'):
                                    try:
                                        session_provs = test_session._sess.get_providers()
                                    except Exception:
                                        session_provs = None
                                elif hasattr(test_session, 'session') and hasattr(test_session.session, 'get_providers'):
                                    try:
                                        session_provs = test_session.session.get_providers()
                                    except Exception:
                                        session_provs = None
                                else:
                                    try:
                                        print(f"Test session object: {type(test_session)}, some attrs: {sorted([a for a in dir(test_session) if not a.startswith('__')])[:12]}")
                                    except Exception:
                                        pass

                                print(f"GPU terdeteksi: {', '.join(gpu_names) if gpu_names else 'Tidak diketahui'}; ONNX providers: {providers}; test session providers: {session_provs if session_provs is not None else 'unknown'}. Akan mencoba menggunakan {providers[0]} untuk inference.")

                                # Consider CUDA available only if the session actually reports using CUDA
                                if session_provs and 'CUDAExecutionProvider' in session_provs:
                                    gpu_available = True
                                else:
                                    gpu_available = False

                            except Exception as e:
                                print(f"Provider ONNX {providers} terdeteksi tetapi pembuatan sesi uji gagal: {type(e).__name__}: {e}. Akan fallback ke CPU.")
                                gpu_available = False
                        else:
                            print(f"Tidak ditemukan provider ONNX GPU. GPU sistem: {', '.join(gpu_names) if gpu_names else 'Tidak ada'}. Menggunakan CPU.")
                    except Exception as e:
                        print(f"Pemeriksaan GPU gagal: {e}. Menggunakan CPU.")
                    
                    try:
                        # First try creating session by model name (preferred)
                        providers = self._get_providers()
                        print(f"Mencoba membuat session dengan model name: {selected_model_name} (providers={providers})...")
                        session = rembg.new_session(selected_model_name, providers=providers) if providers else rembg.new_session(selected_model_name)
                    except Exception as e_name:
                        print(f"Session by name failed for {selected_model_name}: {str(e_name)}")

                        # If model file exists, try creating session from file path
                        file_attempted = False
                        if model_file and os.path.exists(model_file):
                            try:
                                print(f"Mencoba membuat session dengan model file: {model_file}...")
                                providers = self._get_providers()
                                session = rembg.new_session(model_file, providers=providers) if providers else rembg.new_session(model_file)
                                file_attempted = True
                            except Exception as e_file:
                                print(f"Session by file failed for {model_file}: {str(e_file)}")

                        # If still no session, try safe candidate families for all models
                        tried_family = None
                        if not file_attempted:
                            # Candidate fallbacks chosen conservatively
                            candidates = ['isnet-general-use', 'u2net', 'u2netp', 'u2net_human_seg', 'u2net_cloth_seg']
                            name_lower = selected_model_name.lower()
                            # Try name substring matches first
                            for cand in candidates:
                                if cand in name_lower or (cand.replace('-', '_') in name_lower):
                                    try:
                                        print(f"Mencoba family {cand} untuk model {selected_model_name}...")
                                        providers = self._get_providers()
                                        session = rembg.new_session(cand, providers=providers) if providers else rembg.new_session(cand)
                                        tried_family = cand
                                        break
                                    except Exception as e_fam:
                                        print(f"Family {cand} failed: {str(e_fam)}")
                                        continue
                            # If no substring match, fall back to trying candidates in order
                            if tried_family is None:
                                for cand in candidates:
                                    try:
                                        print(f"Mencoba family {cand} untuk model {selected_model_name}...")
                                        providers = self._get_providers()
                                        session = rembg.new_session(cand, providers=providers) if providers else rembg.new_session(cand)
                                        tried_family = cand
                                        break
                                    except Exception as e_fam:
                                        print(f"Family {cand} failed: {str(e_fam)}")
                                        continue

                        if 'session' not in locals():
                            print(f"Gagal membuat session untuk {selected_model_name} (name/file/family). Aborting this file")
                            try:
                                result_queue.put((None, None, False))
                            except Exception:
                                pass
                            processing_complete.set()
                            return

                        # If we used a fallback family, notify UI
                        if tried_family:
                            try:
                                self.status_update.emit(f"Model {selected_model_name} not supported directly; using {tried_family}")
                            except Exception:
                                pass

                    # If we reach here, session was created successfully — inspect which provider(s) are actually used
                    session_provs = None
                    try:
                        # Try several attribute paths to query providers to support different rembg/ort versions
                        if hasattr(session, 'get_providers'):
                            try:
                                session_provs = session.get_providers()
                            except Exception:
                                session_provs = None
                        elif hasattr(session, '_sess') and hasattr(session._sess, 'get_providers'):
                            try:
                                session_provs = session._sess.get_providers()
                            except Exception:
                                session_provs = None
                        elif hasattr(session, 'session') and hasattr(session.session, 'get_providers'):
                            try:
                                session_provs = session.session.get_providers()
                            except Exception:
                                session_provs = None
                        else:
                            print(f"Created session object type: {type(session)}, attrs: {sorted([a for a in dir(session) if not a.startswith('__')])[:12]}")
                    except Exception:
                        pass

                    print(f"Session dibuat untuk model {selected_model_name}; session providers: {session_provs if session_provs is not None else 'unknown'}")

                    # Decide which provider to use and print a clear success/fallback message
                    used_provider = None
                    fallback_reason = None
                    try:
                        if session_provs:
                            # Prioritize common GPU providers
                            if 'CUDAExecutionProvider' in session_provs:
                                used_provider = 'CUDAExecutionProvider'
                            elif 'DmlExecutionProvider' in session_provs:
                                used_provider = 'DmlExecutionProvider'
                            elif 'ROCMExecutionProvider' in session_provs:
                                used_provider = 'ROCMExecutionProvider'
                            elif 'CPUExecutionProvider' in session_provs:
                                used_provider = 'CPUExecutionProvider'
                            else:
                                # Fall back to the first reported provider if unknown
                                used_provider = session_provs[0] if isinstance(session_provs, (list, tuple)) and session_provs else 'unknown'
                        else:
                            # Session did not expose providers — inspect global onnxruntime providers
                            try:
                                import onnxruntime as ort
                                global_provs = ort.get_available_providers()
                            except Exception:
                                global_provs = []

                            # Helper: verify session can perform a tiny inference (runs in background with short timeout)
                            def _verify_session_inference(sess, timeout=5.0):
                                import threading
                                import queue
                                q = queue.Queue()
                                def _job():
                                    try:
                                        from PIL import Image
                                        test_img = Image.new('RGB', (8, 8), (0, 0, 0))
                                        rembg.remove(test_img, only_mask=True, session=sess)
                                        q.put((True, None))
                                    except Exception as ex:
                                        q.put((False, f"{type(ex).__name__}: {ex}"))
                                th = threading.Thread(target=_job, daemon=True)
                                th.start()
                                th.join(timeout)
                                if not q.empty():
                                    return q.get()
                                return False, f"timeout after {timeout}s"

                            # If CUDA exists globally, attempt an automatic verification test before falling back
                            try:
                                if global_provs and 'CUDAExecutionProvider' in global_provs:
                                    ok, info = _verify_session_inference(session)
                                    if ok:
                                        used_provider = 'CUDAExecutionProvider'
                                        fallback_reason = None
                                        print(f"AUTO GPU VERIFY: small inference succeeded — selecting CUDAExecutionProvider (info={info})")
                                    else:
                                        used_provider = 'CPUExecutionProvider'
                                        fallback_reason = f"AUTO GPU VERIFY failed: {info} — falling back to CPU"
                                        print(f"AUTO GPU VERIFY: failed ({info}); falling back to CPU")
                                else:
                                    used_provider = 'CPUExecutionProvider'
                                    fallback_reason = 'No CUDA provider reported by runtime'
                            except Exception as e:
                                used_provider = 'CPUExecutionProvider'
                                fallback_reason = f'AUTO GPU VERIFY infrastructure failure: {type(e).__name__}: {e} — falling back to CPU'
                                print(f'AUTO GPU VERIFY infrastructure error: {type(e).__name__}: {e}; falling back to CPU')

                        # Clear, explicit logging
                        if used_provider and used_provider != 'CPUExecutionProvider':
                            print(f"PROVIDER SELECTED: {used_provider} — SUCCESS: using GPU for inference.")
                        else:
                            msg = f"PROVIDER SELECTED: CPUExecutionProvider — FALLBACK TO CPU"
                            if fallback_reason:
                                msg += f": {fallback_reason}"
                            print(msg)

                        # Emit a UI-friendly short status update
                        try:
                            self.status_update.emit(f"Provider in use: {used_provider}")
                        except Exception:
                            pass

                    except Exception as e:
                        print(f"Error while determining provider: {type(e).__name__}: {e}")

                    self.progress.emit(30, f"Memproses: Menghapus latar belakang...", image_path)
                    print(f"Menghapus latar belakang gambar dengan model: {selected_model_name}...")
                    input_size = input_img.size
                    
                    # Analyze image for optimal alpha matting parameters
                    from APP.helpers.image_utils import recommend_alpha_matting_params
                    alpha_params = recommend_alpha_matting_params(input_img)
                    
                    self.progress.emit(40, f"Memproses: Menerapkan alpha matting...", image_path)
                    
                    # Try alpha matting with progressive parameter adjustment
                    alpha_matting_success = False
                    output_img = None
                    
                    # Define progressive parameter attempts
                    attempts = [
                        # Start with recommended parameters
                        {
                            "alpha_matting_foreground_threshold": alpha_params["alpha_matting_foreground_threshold"],
                            "alpha_matting_background_threshold": alpha_params["alpha_matting_background_threshold"],
                            "alpha_matting_erode_size": alpha_params["alpha_matting_erode_size"],
                            "alpha_matting_discard_threshold": alpha_params.get("alpha_matting_discard_threshold", 1e-4),
                            "alpha_matting_shift": alpha_params.get("alpha_matting_shift", 0.01)
                        },
                        # Increase shift slightly
                        {
                            "alpha_matting_foreground_threshold": alpha_params["alpha_matting_foreground_threshold"],
                            "alpha_matting_background_threshold": alpha_params["alpha_matting_background_threshold"],
                            "alpha_matting_erode_size": alpha_params["alpha_matting_erode_size"],
                            "alpha_matting_discard_threshold": 1e-4,
                            "alpha_matting_shift": 0.02
                        },
                        # Increase shift more
                        {
                            "alpha_matting_foreground_threshold": alpha_params["alpha_matting_foreground_threshold"],
                            "alpha_matting_background_threshold": alpha_params["alpha_matting_background_threshold"],
                            "alpha_matting_erode_size": alpha_params["alpha_matting_erode_size"],
                            "alpha_matting_discard_threshold": 1e-4,
                            "alpha_matting_shift": 0.05
                        },
                        # Decrease discard_threshold
                        {
                            "alpha_matting_foreground_threshold": alpha_params["alpha_matting_foreground_threshold"],
                            "alpha_matting_background_threshold": alpha_params["alpha_matting_background_threshold"],
                            "alpha_matting_erode_size": alpha_params["alpha_matting_erode_size"],
                            "alpha_matting_discard_threshold": 1e-5,
                            "alpha_matting_shift": 0.01
                        },
                        # More aggressive: lower discard_threshold and higher shift
                        {
                            "alpha_matting_foreground_threshold": alpha_params["alpha_matting_foreground_threshold"],
                            "alpha_matting_background_threshold": alpha_params["alpha_matting_background_threshold"],
                            "alpha_matting_erode_size": alpha_params["alpha_matting_erode_size"],
                            "alpha_matting_discard_threshold": 1e-6,
                            "alpha_matting_shift": 0.1
                        }
                    ]
                    
                    for attempt_idx, params in enumerate(attempts):
                        try:
                            print(f"Mencoba alpha matting attempt {attempt_idx + 1}: discard_threshold={params['alpha_matting_discard_threshold']}, shift={params['alpha_matting_shift']}")
                            output_img = rembg.remove(
                                input_img,
                                alpha_matting=True,
                                alpha_matting_foreground_threshold=params["alpha_matting_foreground_threshold"],
                                alpha_matting_background_threshold=params["alpha_matting_background_threshold"],
                                alpha_matting_erode_size=params["alpha_matting_erode_size"],
                                alpha_matting_discard_threshold=params["alpha_matting_discard_threshold"],
                                alpha_matting_shift=params["alpha_matting_shift"],
                                session=session
                            )
                            alpha_matting_success = True
                            print(f"Alpha matting berhasil pada attempt {attempt_idx + 1}")
                            break
                        except Exception as attempt_error:
                            print(f"Attempt {attempt_idx + 1} gagal: {str(attempt_error)}")
                            continue
                    
                    if not alpha_matting_success:
                        print("Semua attempt alpha matting gagal, melanjutkan tanpa alpha matting untuk hasil, tapi tetap dapatkan mask.")
                        # Last resort: disable alpha matting but still get mask
                        output_img = rembg.remove(input_img, session=session)  # No alpha matting
                    
                    output_size = output_img.size
                    print(f"Ukuran input: {input_size[0]}x{input_size[1]}, ukuran output: {output_size[0]}x{output_size[1]}")
                    
                    if output_size[0] > input_size[0] * 2 or output_size[1] > input_size[1] * 2:
                        print(f"PERINGATAN: Ukuran output tidak normal! Menyesuaikan ukuran...")
                        output_img = output_img.resize(input_size, Image.LANCZOS)
                    
                    output_img.save(output_path)
                    
                    # Always get mask separately as required
                    output_mask = rembg.remove(input_img, only_mask=True, session=session)
                    
                    if output_mask.size != input_size:
                        print(f"PERINGATAN: Ukuran mask tidak sama dengan input! Menyesuaikan ukuran...")
                        output_mask = output_mask.resize(input_size, Image.LANCZOS)
                    
                    output_mask.save(mask_path)
                    result_queue.put((output_img, output_mask, True))
                    
                except Exception as e:
                    print(f"Error in timeout thread: {str(e)}")
                    result_queue.put((None, None, False))
                finally:
                    processing_complete.set()
            
            processing_thread = threading.Thread(target=process_with_timeout)
            processing_thread.daemon = True
            processing_thread.start()
            
            processing_succeeded = processing_complete.wait(timeout=self.PROCESSING_TIMEOUT)
            
            # Local helper to forward download progress (if used)
            # Note: prepare_model called earlier will call back to self._download_progress_callback
            
            if not processing_succeeded:
                print(f"WARNING: Processing timeout ({self.PROCESSING_TIMEOUT}s) reached for {image_path}")
                return None, None
            
            if not result_queue.empty():
                output_img, output_mask, success = result_queue.get()
                if success:
                    return output_path, mask_path
            
            return None, None
            
        except Exception as e:
            import traceback
            print(f"Error saat memproses dengan rembg: {str(e)}")
            traceback.print_exc()
            return None, None

    def _download_progress_callback(self, model_name, progress):
        """Forward download progress via Qt signal (safe across threads)."""
        try:
            # Emit float progress
            self.download_progress.emit(model_name, float(progress))
        except Exception as e:
            print(f"Error emitting download progress: {str(e)}")

    def _enhance_transparency(self, output_path, mask_path, file_name, output_dir, image_path):
        """Enhance transparency using levels adjustment."""
        try:
            self.progress.emit(70, f"Menghasilkan gambar transparan yang disempurnakan...", image_path)
            
            save_mask = get_save_mask_enabled()
            # Use current runtime values saved by the sliders (so processing matches preview)
            black_point = get_levels_black_point()
            mid_point = get_levels_mid_point()
            white_point = get_levels_white_point()
            
            self.progress.emit(65, f"Menghasilkan mask yang diatur levels-nya...", image_path)
            print(f"Langkah 1: Menerapkan levels adjustment pada mask...")
            
            self.progress.emit(80, f"Membuat gambar transparan dengan mask yang diatur levels...", image_path)
            print(f"Langkah 2: Membuat gambar transparan dengan mask yang sudah diatur levels-nya...")
            
            enhanced_path = enhance_transparency_with_levels(
                output_path, mask_path,
                output_suffix="_transparent",
                black_point=black_point,
                mid_point=mid_point,
                white_point=white_point,
                save_adjusted_mask=True,
                cleanup_temp_files_after=False,
                save_mask=save_mask
            )
            
            if enhanced_path:
                print(f"Berhasil membuat gambar dengan levels adjustment: {enhanced_path}")
                
                if not save_mask:
                    import re
                    timestamp_match = re.search(r'_transparent_(\d+)', enhanced_path)
                    timestamp_suffix = f"_{timestamp_match.group(1)}" if timestamp_match else ""
                    mask_path_adjusted = os.path.join(output_dir, f"{file_name}_mask_adjusted{timestamp_suffix}.png")
                    
                    if os.path.exists(mask_path_adjusted):
                        try:
                            os.remove(mask_path_adjusted)
                            print(f"Removed mask file: {mask_path_adjusted}")
                        except Exception as e:
                            print(f"Error removing mask: {str(e)}")
                
                cleanup_original_temp_files(output_path, mask_path)
                return enhanced_path
            
            return None
            
        except Exception as e:
            print(f"Error saat membuat gambar transparan: {str(e)}")
            return None

    def _apply_auto_crop(self, enhanced_path, file_name, output_dir, image_path):
        """Apply auto-cropping if enabled."""
        try:
            if not get_auto_crop_enabled():
                print(f"Auto crop disabled, skipping crop step")
                return enhanced_path
            
            self.progress.emit(90, f"Melakukan auto crop...", image_path)
            print(f"Auto crop enabled, cropping image...")
            
            mask_to_use = os.path.join(output_dir, f'{file_name}_mask_adjusted.png')
            unified_margin = get_unified_margin()
            print(f"Using unified margin: {unified_margin}px")
            
            cropped_path = crop_transparent_image(
                enhanced_path,
                mask_to_use,
                output_path=None,
                threshold=unified_margin
            )
            
            if cropped_path:
                print(f"Auto-cropped image saved at: {cropped_path}")
                return cropped_path
                
        except Exception as e:
            print(f"Warning: Auto crop error: {str(e)}")
        
        return enhanced_path

    def _apply_solid_background(self, enhanced_path, image_path):
        """Apply solid background and JPG export if enabled."""
        try:
            unified_margin = get_unified_margin()
            solid_bg_path = None
            
            if get_solid_bg_enabled():
                solid_bg_path = add_solid_background(enhanced_path, margin=unified_margin)
                if solid_bg_path:
                    print(f"Image with solid background saved at: {solid_bg_path} (margin: {unified_margin}px)")
            
            try:
                jpg_path = process_jpg_conversion(solid_bg_path if solid_bg_path else enhanced_path)
                if jpg_path:
                    print(f"JPG version saved at: {jpg_path}")
            except Exception as e:
                print(f"Warning: JPG conversion error: {str(e)}")
                
        except Exception as e:
            print(f"Warning: Solid background error: {str(e)}")
