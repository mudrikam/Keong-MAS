"""Worker class for background removal processing."""

import os
import time
import queue
import threading
from pathlib import Path
from PIL import Image
from PySide6.QtCore import QObject, Signal
import rembg

from APP.helpers import model_manager
from APP.helpers.config_manager import get_save_mask_enabled, get_auto_crop_enabled, get_unified_margin, get_solid_bg_enabled
from APP.helpers.ui_helpers import download_progress_callback
from APP.helpers.image_utils import enhance_transparency_with_levels, get_levels_config, cleanup_original_temp_files
from APP.helpers.image_crop import crop_transparent_image
from APP.helpers.solid_background import add_solid_background
from APP.helpers.jpg_converter import process_jpg_conversion


class RemBgWorker(QObject):
    """Worker for processing background removal in a separate thread."""
    
    progress = Signal(int, str, str)
    finished = Signal(float, int)
    file_completed = Signal(str)
    status_update = Signal(str)

    SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp'}
    PROCESSING_TIMEOUT = 300
    
    def __init__(self, file_paths, output_dir=None):
        super().__init__()
        self.file_paths = file_paths
        self.output_dir = output_dir
        self.abort = False
        self.start_time = 0
        self.processed_files_count = 0

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

    def process_image(self, image_path):
        """Process a single image through the background removal pipeline."""
        try:
            base_output_dir = self.output_dir or os.path.join(os.path.dirname(image_path), 'PNG')
            os.makedirs(base_output_dir, exist_ok=True)
            
            input_path = Path(image_path)
            file_name = input_path.stem
            
            self.progress.emit(5, f"Menyiapkan: {file_name}", image_path)
            
            self.progress.emit(10, f"Menyiapkan model: {os.path.basename(image_path)}", image_path)
            print(f"Menyiapkan model default...")
            model_name = model_manager.prepare_model(callback=download_progress_callback)
            print(f"Menggunakan model {model_name}")
            
            self.progress.emit(20, f"Memuat gambar: {os.path.basename(image_path)}", image_path)
            
            input_img = Image.open(image_path)
            output_path, mask_path = self._process_with_rembg(input_img, base_output_dir, file_name, model_name, image_path)
            
            if not output_path:
                return
            
            self.progress.emit(50, f"Menyimpan gambar transparan...", image_path)
            print(f"Gambar transparan disimpan ke {output_path}")
            
            enhanced_path = self._enhance_transparency(output_path, mask_path, file_name, base_output_dir, image_path)
            
            if enhanced_path:
                enhanced_path = self._apply_auto_crop(enhanced_path, file_name, base_output_dir, image_path)
                self._apply_solid_background(enhanced_path, image_path)
            
            # Emit completion with ORIGINAL input path, not output path
            self.file_completed.emit(image_path)
            self.processed_files_count += 1
            
        except Exception as e:
            print(f"Error removing background from {image_path}: {str(e)}")

    def _process_with_rembg(self, input_img, output_dir, file_name, model_name, image_path):
        """Process image with rembg to remove background."""
        output_path = os.path.join(output_dir, f"{file_name}.png")
        mask_path = os.path.join(output_dir, f"{file_name}_mask.png")
        
        try:
            result_queue = queue.Queue()
            processing_complete = threading.Event()
            
            def process_with_timeout():
                try:
                    print(f"Membuat session dengan model {model_name}...")
                    session = rembg.new_session(model_name)
                    
                    self.progress.emit(30, f"Memproses: Menghapus latar belakang...", image_path)
                    print(f"Menghapus latar belakang gambar...")
                    input_size = input_img.size
                    
                    self.progress.emit(40, f"Memproses: Menerapkan alpha matting...", image_path)
                    output_img = rembg.remove(
                        input_img,
                        alpha_matting=True,
                        alpha_matting_foreground_threshold=240,
                        alpha_matting_background_threshold=10,
                        alpha_matting_erode_size=10,
                        session=session
                    )
                    
                    output_size = output_img.size
                    print(f"Ukuran input: {input_size[0]}x{input_size[1]}, ukuran output: {output_size[0]}x{output_size[1]}")
                    
                    if output_size[0] > input_size[0] * 2 or output_size[1] > input_size[1] * 2:
                        print(f"PERINGATAN: Ukuran output tidak normal! Menyesuaikan ukuran...")
                        output_img = output_img.resize(input_size, Image.LANCZOS)
                    
                    output_img.save(output_path)
                    
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
            
            if not processing_succeeded:
                print(f"WARNING: Processing timeout ({self.PROCESSING_TIMEOUT}s) reached for {image_path}")
                return None, None
            
            if not result_queue.empty():
                output_img, output_mask, success = result_queue.get()
                if success:
                    return output_path, mask_path
            
            return None, None
            
        except Exception as e:
            print(f"Error saat memproses dengan rembg: {str(e)}")
            return None, None

    def _enhance_transparency(self, output_path, mask_path, file_name, output_dir, image_path):
        """Enhance transparency using levels adjustment."""
        try:
            self.progress.emit(70, f"Menghasilkan gambar transparan yang disempurnakan...", image_path)
            
            save_mask = get_save_mask_enabled()
            black_point, mid_point, white_point = get_levels_config(use_recommended=False)
            
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
