import os
import sys
import numpy as np
from PIL import Image
import time

# Import model manager to use GPU session
from .model_manager import get_gpu_session, MODEL_DIR, DEFAULT_MODEL

# Make sure we have the environment variable set
os.environ["U2NET_HOME"] = MODEL_DIR

class GPUBackgroundRemover:
    """Class untuk menghapus background foto dengan GPU acceleration"""
    
    def __init__(self):
        """Initialize GPU background remover"""
        # Import rembg here to ensure environment variables are set first
        from rembg import new_session, remove
        self.remove_bg = remove
        
        # Try to create a GPU session
        print("Membuat session untuk background removal...")
        start_time = time.time()
        
        try:
            self.session = get_gpu_session()  # Use the function from model_manager
            if not self.session:
                # If get_gpu_session failed, try creating our own with CPU
                print("Fallback ke CPU session...")
                self.session = new_session(model_name=DEFAULT_MODEL, providers=["CPUExecutionProvider"])
            
            # Verify session is using GPU
            import onnxruntime as ort
            sess_providers = self.session._session.get_providers()
            if 'CUDAExecutionProvider' in sess_providers:
                print("✅ Session menggunakan GPU (CUDAExecutionProvider)")
                self.using_gpu = True
            else:
                print("⚠️ Session menggunakan CPU:", sess_providers)
                self.using_gpu = False
        except Exception as e:
            print(f"Error creating session: {str(e)}")
            print("⚠️ Background removal akan berjalan lambat dengan CPU mode")
            try:
                from rembg import new_session
                self.session = new_session(model_name=DEFAULT_MODEL)
            except:
                self.session = None
            self.using_gpu = False
            
        init_time = time.time() - start_time
        print(f"Session initialization completed in {init_time:.2f} seconds")
        
        # Run initial inference to warm up the model
        try:
            print("Melakukan warm-up untuk model...")
            warm_up_start = time.time()
            # Create a small blank image for warm-up
            dummy_img = np.ones((64, 64, 3), dtype=np.uint8) * 255
            _ = self.remove_bg(dummy_img, session=self.session)
            warm_up_time = time.time() - warm_up_start
            print(f"Model warm-up selesai dalam {warm_up_time:.2f} detik")
            
            if self.using_gpu and warm_up_time > 1.0:
                print("⚠️ Warm-up terlalu lama untuk GPU, mungkin masih menggunakan CPU")
            elif self.using_gpu:
                print("✅ Warm-up cepat, GPU berjalan dengan baik")
        except Exception as e:
            print(f"Warm-up gagal: {str(e)}")
            
    def remove_background(self, input_image, alpha_matting=False, alpha_matting_foreground_threshold=240):
        """
        Remove background from image using GPU acceleration
        
        Args:
            input_image: PIL Image or numpy array
            alpha_matting: Bool, whether to use alpha matting
            alpha_matting_foreground_threshold: Alpha matting threshold
            
        Returns:
            PIL Image with background removed
        """
        start_time = time.time()
        
        if isinstance(input_image, str):
            if os.path.exists(input_image):
                input_image = Image.open(input_image)
            else:
                raise FileNotFoundError(f"Image file not found: {input_image}")
                
        # Ensure image is properly formatted
        if isinstance(input_image, Image.Image):
            img_array = np.array(input_image)
        else:
            img_array = input_image
            
        # Process with explicit GPU session
        try:
            # IMPORTANT: Explicitly pass session to force GPU usage
            result = self.remove_bg(
                img_array,
                session=self.session,  # This is the key to GPU usage
                alpha_matting=alpha_matting,
                alpha_matting_foreground_threshold=alpha_matting_foreground_threshold
            )
            
            # Convert back to PIL image
            output_image = Image.fromarray(result)
            
            # Log processing time
            elapsed = time.time() - start_time
            print(f"Background removal completed in {elapsed:.2f} seconds")
            
            # Check if processing time suggests CPU instead of GPU
            if self.using_gpu and elapsed > 0.5:  # More than 0.5 seconds might indicate CPU usage
                img_size = img_array.shape
                pixels = img_size[0] * img_size[1]
                if pixels > 1000000:  # Large image
                    expected_time = 0.2  # Expected GPU time in seconds per megapixel
                else:
                    expected_time = 0.1
                expected_total = (pixels / 1000000) * expected_time
                
                if elapsed > expected_total * 3:  # 3x slower than expected
                    print(f"⚠️ PERINGATAN: Processing ({elapsed:.2f}s) lebih lambat dari harapan ({expected_total:.2f}s)")
                    print("Mungkin GPU tidak digunakan dengan benar")
                    
            return output_image
            
        except Exception as e:
            print(f"Error removing background: {str(e)}")
            return input_image

# Create singleton instance
gpu_remover = GPUBackgroundRemover()

# Simple function to use the GPU remover
def remove_bg(image, alpha_matting=False):
    """
    Hapus background gambar menggunakan GPU
    
    Args:
        image: PIL Image, numpy array, or file path
        alpha_matting: Bool, whether to use alpha matting
        
    Returns:
        PIL Image with background removed
    """
    return gpu_remover.remove_background(image, alpha_matting=alpha_matting)
