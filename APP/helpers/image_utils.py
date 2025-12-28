import os
import json
import numpy as np
from PIL import Image

# Load config from JSON file
def load_config():
    """
    Loads the configuration from config.json file
    
    Returns:
        dict: Configuration values or default values if file not found
    """
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
        with open(config_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Warning: Could not load config.json: {e}")
        # Return default config structure if file not found or invalid
        return {
            "image_processing": {
                "levels_adjustment": {
                    "default": {
                        "black_point": 0,
                        "mid_point": 80,
                        "white_point": 230
                    },
                    "recommended": {
                        "black_point": 20,
                        "mid_point": 128,
                        "white_point": 235
                    }
                }
            }
        }

# Load config values
config = load_config()
levels_config = config.get("image_processing", {}).get("levels_adjustment", {})

# Default values for levels adjustment - loaded from config.json
DEFAULT_BLACK_POINT = levels_config.get("default", {}).get("black_point", 0)     # Higher values make more pixels transparent (0-255)
DEFAULT_MID_POINT = levels_config.get("default", {}).get("mid_point", 80)     # Controls gamma/midtone curve (0-255)
DEFAULT_WHITE_POINT = levels_config.get("default", {}).get("white_point", 230)   # Lower values make more pixels opaque (0-255)

# Recommended values for edge control - loaded from config.json 
RECOMMENDED_BLACK_POINT = levels_config.get("recommended", {}).get("black_point", 20)     # Better edge control in dark areas
RECOMMENDED_MID_POINT = levels_config.get("recommended", {}).get("mid_point", 128)      # No change to midtones by default
RECOMMENDED_WHITE_POINT = levels_config.get("recommended", {}).get("white_point", 235)    # Better edge control in light areas

def get_levels_config(use_recommended=True):
    """
    Returns the current levels configuration values.
    
    Args:
        use_recommended (bool): If True, returns recommended values for edge control.
                               If False, returns the default values (no adjustment).
    
    Returns:
        tuple: (black_point, mid_point, white_point) values to use
    """
    if use_recommended:
        return (RECOMMENDED_BLACK_POINT, RECOMMENDED_MID_POINT, RECOMMENDED_WHITE_POINT)
    else:
        return (DEFAULT_BLACK_POINT, DEFAULT_MID_POINT, DEFAULT_WHITE_POINT)

def create_binary_mask(mask_image, threshold=128):
    """
    Creates a binary mask (only pure black or pure white) for extreme edge control.
    This is an alternative to the levels adjustment for cases where you want 
    a hard cutoff with no gray pixels.
    
    Args:
        mask_image (PIL.Image): The mask image to binarize
        threshold (int): The threshold value (0-255) - pixels below become black (0),
                        pixels above become white (255)
        
    Returns:
        PIL.Image: The binary mask image
    """
      # Ensure mask is in grayscale mode
    mask = mask_image.convert("L")
    
    # Convert to numpy array for faster processing
    mask_array = np.array(mask, dtype=np.uint8)
    
    # Original min/max (kept for potential debugging, printing removed)
    
    # Create binary mask - all values below threshold become 0, all above become 255
    binary_mask = np.zeros_like(mask_array)
    binary_mask[mask_array > threshold] = 255
    
    # Convert back to PIL Image
    binary_mask_img = Image.fromarray(binary_mask)
    
    return binary_mask_img

def combine_with_mask(image_path, mask_path, output_suffix="_transparent"):
    """
    Combines a transparent PNG image with its mask to create an improved transparent image.
    
    Args:
        image_path (str): Path to the main transparent PNG image
        mask_path (str): Path to the mask image (should be grayscale where white=100% opacity)
        output_suffix (str): Suffix to add to the output filename
        
    Returns:
        str: Path to the generated transparent image
    """
    try:        # Load the main image and the mask
        main_image = Image.open(image_path)
        mask_image = Image.open(mask_path)
        
        # Debug ukuran gambar
        main_size = main_image.size
        mask_size = mask_image.size
        print(f"Ukuran gambar utama: {main_size[0]}x{main_size[1]}")
        print(f"Ukuran mask: {mask_size[0]}x{mask_size[1]}")
        
        # Pastikan mask dan gambar utama memiliki ukuran yang sama
        if main_size != mask_size:
            print(f"PERINGATAN: Ukuran gambar dan mask berbeda! Menyesuaikan mask...")
            mask_image = mask_image.resize(main_size, Image.LANCZOS)
        
        # Convert mask to grayscale if it's not already
        mask = mask_image.convert("L")
        
        # Create a new RGBA image
        result = Image.new("RGBA", main_image.size, (0, 0, 0, 0))
        
        # Copy the RGB data from the main image
        result.paste(main_image.convert("RGB"), (0, 0))
        
        # Use the mask as the alpha channel (where white in the mask = 100% opacity)
        # This will override the alpha channel from the main image
        result.putalpha(mask)
        
        # Create output path
        output_dir = os.path.dirname(image_path)
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        output_path = os.path.join(output_dir, f"{file_name}{output_suffix}.png")
        
        # Save the resulting image
        result.save(output_path)
        
        return output_path
        
    except Exception as e:
        print(f"Error combining image with mask: {str(e)}")
        return None


def enhance_transparency(image_path, mask_path, output_suffix="_enhanced"):
    """
    Takes a transparent PNG image and refines its alpha channel using the mask.
    Instead of completely replacing the alpha, this will subtract from the existing alpha.
    
    Args:
        image_path (str): Path to the main transparent PNG image
        mask_path (str): Path to the mask image (black = transparent, white = opaque)
        output_suffix (str): Suffix to add to the output filename
        
    Returns:
        str: Path to the generated enhanced transparent image
    """

    
    try:
        # Verify files exist
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"Mask file not found: {mask_path}")
              # Load the main image and the mask
        main_image = Image.open(image_path)
        mask_image = Image.open(mask_path)
        
        # Debug ukuran gambar
        main_size = main_image.size
        mask_size = mask_image.size
        print(f"Ukuran gambar utama: {main_size[0]}x{main_size[1]}")
        print(f"Ukuran mask: {mask_size[0]}x{mask_size[1]}")
        
        # Pastikan mask dan gambar utama memiliki ukuran yang sama
        if main_size != mask_size:
            print(f"PERINGATAN: Ukuran gambar dan mask berbeda! Menyesuaikan mask...")
            mask_image = mask_image.resize(main_size, Image.LANCZOS)
        
        # Convert mask to grayscale if it's not already
        mask = mask_image.convert("L")
        
        # Import numpy untuk operasi array
        import numpy as np
        
        # Mask min/max debug printing removed
        
        # Pastikan mask tidak terbalik: 255 (putih) harus mewakili area yang ingin dipertahankan
        # rembg mask: putih = objek, hitam = background, ini sudah benar
        
        # Ambil komponen RGB dari gambar asli
        rgb = main_image.convert("RGB")
        r, g, b = rgb.split()
        
        # Gunakan mask langsung sebagai alpha channel
        new_alpha = mask
        
        # Alpha min/max debug printing removed
        
        # Merge the channels back together
        result = Image.merge("RGBA", (r, g, b, new_alpha))
        
        # Create output path
        output_dir = os.path.dirname(image_path)
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        output_path = os.path.join(output_dir, f"{file_name}{output_suffix}.png")
        
        # Save the resulting image
        result.save(output_path)
        
        return output_path
        
    except Exception as e:
        print(f"Error enhancing transparency: {str(e)}")
        return None


def apply_levels_to_mask(mask_image, black_point=DEFAULT_BLACK_POINT, mid_point=DEFAULT_MID_POINT, white_point=DEFAULT_WHITE_POINT):
    """Public wrapper for levels adjustment. Delegates to the internal implementation so
    preview and real processing share identical math.
    """
    return _apply_levels_to_mask_impl(mask_image, black_point, mid_point, white_point)


def cleanup_original_temp_files(original_transparent_path, original_mask_path):
    """
    Removes only the original temporary files that are no longer needed after processing.
    Now uses centralized cleanup manager.
    
    Args:
        original_transparent_path (str): Path to the original transparent image to remove
        original_mask_path (str): Path to the original mask image to remove
    """
    from APP.helpers.cleanup_manager import cleanup_original_temp_files as cleanup_mgr_original
    cleanup_mgr_original(original_transparent_path, original_mask_path)

def cleanup_temp_files(original_transparent_path, original_mask_path, adjusted_mask_path=None, save_mask=False):
    """
    DEPRECATED: Use cleanup_manager instead.
    Kept for backwards compatibility.
    """
    print("Warning: cleanup_temp_files is deprecated, use cleanup_manager instead")
    from APP.helpers.cleanup_manager import cleanup_original_temp_files as cleanup_mgr_original, cleanup_adjusted_mask_if_safe
    
    # Clean up original files
    cleanup_mgr_original(original_transparent_path, original_mask_path)
    
    # Handle adjusted mask
    if adjusted_mask_path:
        cleanup_adjusted_mask_if_safe(adjusted_mask_path)

import math

def _apply_levels_to_mask_impl(mask_image, black_point, mid_point, white_point):
    """Internal implementation of levels adjustment used by public wrapper.

    Uses the original Photoshop-like approach (clip, normalize to 0-1, apply simple gamma mapping
    using a piecewise formula where midpoint <128 increases gamma and midpoint>128 reduces gamma).
    This matches the original function that was present before and preserves expected behavior.
    """
    import numpy as np
    from PIL import Image, ImageOps

    # Ensure mask is in grayscale mode and convert to float array
    if isinstance(mask_image, str):
        if not os.path.exists(mask_image):
            raise FileNotFoundError(f"Mask file not found: {mask_image}")
        mask = Image.open(mask_image).convert('L')
    else:
        mask = mask_image.convert('L')

    mask_array = np.array(mask, dtype=np.float32)

    # Original range computation kept for internal use (printing removed)
    try:
        original_min = np.min(mask_array)
        original_max = np.max(mask_array)
    except Exception:
        original_min = 0.0
        original_max = 255.0

    input_black = float(black_point)
    input_white = float(white_point)



    # Clip and normalize
    mask_array = np.clip(mask_array, input_black, input_white)
    mask_array = (mask_array - input_black) / max(1.0, (input_white - input_black))

    # Apply simple piecewise gamma mapping based on midpoint
    if mid_point != 128:
        gamma = 1.0
        if mid_point < 128:
            gamma = 1.0 + (128.0 - mid_point) / 128.0
        else:
            gamma = 128.0 / float(mid_point)
        mask_array = np.power(mask_array, gamma)

    # Scale back to 0-255 and clip
    mask_array = mask_array * 255.0
    mask_array = np.clip(mask_array, 0, 255).astype(np.uint8)

    try:
        new_min = np.min(mask_array)
        new_max = np.max(mask_array)
    except Exception:
        new_min = 0
        new_max = 255

    return Image.fromarray(mask_array)


def enhance_transparency_with_levels(image_path, mask_path, output_suffix="_transparent", 
                                   black_point=DEFAULT_BLACK_POINT, mid_point=DEFAULT_MID_POINT, white_point=DEFAULT_WHITE_POINT, 
                                   save_adjusted_mask=True, cleanup_temp_files_after=True, save_mask=False):
    """
    Takes a transparent PNG image and refines its alpha channel using the mask
    with levels adjustment to control feathering.
    Now uses centralized cleanup manager.
    
    Args:
        image_path (str): Path to the main transparent PNG image
        mask_path (str): Path to the mask image (black = transparent, white = opaque)
        output_suffix (str): Suffix to add to the output filename
        black_point (int): The black point slider (0-255) - higher values make more pixels transparent
                          Default 0 = no change to shadows
        mid_point (int): The gamma/midtone slider (0-255) - adjusts the midtones curve
                        Default 128 = no change to midtones
        white_point (int): The white point slider (0-255) - lower values make more pixels opaque
                          Default 255 = no change to highlights
        save_adjusted_mask (bool): Whether to save the adjusted mask as a separate file
        cleanup_temp_files_after (bool): Whether to remove temporary files after processing
        save_mask (bool): Whether to keep the adjusted mask file after processing (deprecated - now handled by cleanup manager)
        
    Returns:
        str: Path to the generated enhanced transparent image
    """
    print(f"Memproses enhance_transparency_with_levels:")
    print(f"- Image path: {image_path}")
    print(f"- Mask path: {mask_path}")
    print(f"- Levels: Black={black_point}, Mid={mid_point}, White={white_point}")
    print(f"- Save adjusted mask: {save_adjusted_mask}")
    
    # Import cleanup manager
    from APP.helpers.cleanup_manager import cleanup_original_temp_files, register_file_in_use, intelligent_cleanup_after_image_utils
    
    adjusted_mask_path = None
    try:
        # Verify files exist
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"Mask file not found: {mask_path}")
            
        # Load the main image and the mask
        main_image = Image.open(image_path)
        mask_image = Image.open(mask_path)
        
        # Debug ukuran gambar
        main_size = main_image.size
        mask_size = mask_image.size
        print(f"Ukuran gambar utama: {main_size[0]}x{main_size[1]}")
        print(f"Ukuran mask: {mask_size[0]}x{mask_size[1]}")
        
        # Pastikan mask dan gambar utama memiliki ukuran yang sama
        if main_size != mask_size:
            print(f"PERINGATAN: Ukuran gambar dan mask berbeda! Menyesuaikan mask...")
            mask_image = mask_image.resize(main_size, Image.LANCZOS)
            
        # Detect if extreme settings are being used
        using_extreme_settings = (white_point < 10) or (black_point > 240) or (mid_point < 10)
        
        if using_extreme_settings:
            print("Detecting extreme levels settings, using binary mask...")
            # For extreme settings, create a binary mask instead
            threshold = 127  # Default threshold
            
            # Adjust threshold based on provided settings - this is a simplified approach
            if white_point < 10:  # Very low white point = more white pixels
                threshold = max(10, white_point * 10)
            elif black_point > 240:  # Very high black point = more black pixels
                threshold = min(240, black_point)
            
            adjusted_mask = create_binary_mask(mask_image, threshold=threshold)
            print(f"Created binary mask with threshold: {threshold}")
        else:
            # Normal settings, use regular levels adjustment
            adjusted_mask = apply_levels_to_mask(
                mask_image, 
                black_point=black_point,
                mid_point=mid_point, 
                white_point=white_point
            )
        
        # Create a timestamp-based identifier to prevent overwriting previous outputs
        import time
        timestamp_id = int(time.time()) % 10000  # Use last 4 digits of timestamp
        
        # Setup output paths properly to avoid nested PNG folders
        base_dir = os.path.dirname(image_path)
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Check if the image is already in a PNG folder
        if os.path.basename(base_dir).upper() == 'PNG':
            # Image is already in a PNG folder, use that directory
            png_dir = base_dir
        else:
            # Create a PNG folder if it doesn't exist
            png_dir = os.path.join(base_dir, 'PNG')
            os.makedirs(png_dir, exist_ok=True)
        
        # Create paths for both files in the PNG directory with timestamp
        adjusted_mask_path = os.path.join(png_dir, f"{file_name}_mask_adjusted_{timestamp_id}.png")
        output_path = os.path.join(png_dir, f"{file_name}{output_suffix}_{timestamp_id}.png")
        
        # Save adjusted mask if requested - ensure it gets saved to PNG folder
        if save_adjusted_mask:
            try:
                adjusted_mask.save(adjusted_mask_path)
                print(f"Adjusted mask disimpan ke {adjusted_mask_path}")
                
                # Register the adjusted mask as in use for future operations
                register_file_in_use(adjusted_mask_path)
                
            except Exception as mask_error:
                print(f"Error saving adjusted mask: {str(mask_error)}")
        
        # Ambil komponen RGB dari gambar asli
        rgb = main_image.convert("RGB")
        r, g, b = rgb.split()
        
        # Use adjusted mask as alpha channel
        new_alpha = adjusted_mask
        
        # Merge the channels back together
        result = Image.merge("RGBA", (r, g, b, new_alpha))
        
        # Save the resulting image
        result.save(output_path)
        
        # Clean up original temporary files if requested
        if cleanup_temp_files_after:
            cleanup_original_temp_files(image_path, mask_path)
        
        print(f"File yang disimpan:")
        print(f"1. Gambar transparan final: {output_path}")
        if save_adjusted_mask:
            print(f"2. Mask yang diatur levels: {adjusted_mask_path}")
            print(f"Note: Adjusted mask cleanup will be handled by cleanup manager based on config")
        
        # INTELLIGENT CLEANUP: Only cleanup if no other operations are enabled
        print("Checking if intelligent cleanup should run...")
        intelligent_cleanup_after_image_utils(output_path)
        
        return output_path
        
    except Exception as e:
        print(f"Error enhancing transparency with levels: {str(e)}")
        return None

# Add this new function to help understand and handle rembg alpha matting errors
def explain_alpha_matting_error(error_message):
    """
    Parses and explains alpha matting errors from rembg.
    
    Args:
        error_message (str): The error message from rembg
        
    Returns:
        str: A human-readable explanation of the error
    """
    explanation = "Error during alpha matting: "
    
    if "Cholesky decomposition failed" in error_message:
        explanation += (
            "The alpha matting algorithm failed due to numerical instability. "
            "This usually happens with images that have very low contrast between "
            "foreground and background, or with very complex edges.\n\n"
            "Technical details: The alpha matting process builds a matrix of pixel "
            "relationships, and when this matrix isn't 'positive-definite' (a mathematical "
            "property), the Cholesky decomposition used to solve the equations fails.\n\n"
            "This error comes from the PyMatting library used by rembg."
        )
    elif "discard_threshold" in error_message:
        explanation += (
            "The alpha matting parameters need adjustment. The 'discard_threshold' is too high "
            "or the 'shift' value is too low for this particular image.\n\n"
            "These parameters control the numerical stability of the matrix operations. "
            "Try using alpha matting with adjusted parameters or disable alpha matting."
        )
    else:
        explanation += f"Unknown alpha matting error: {error_message}"
    
    return explanation

# Add a function to recommend alpha matting parameters based on image characteristics
def recommend_alpha_matting_params(image):
    """
    Analyzes an image and recommends suitable alpha matting parameters
    to reduce the chance of Cholesky decomposition errors.
    
    Args:
        image (PIL.Image): The input image
        
    Returns:
        dict: Recommended alpha matting parameters
    """
    # Convert to grayscale for analysis
    grayscale = image.convert("L")
    np_img = np.array(grayscale)
    
    # Get image statistics
    img_min = np.min(np_img)
    img_max = np.max(np_img)
    img_mean = np.mean(np_img)
    img_std = np.std(np_img)
    
    # Calculate contrast ratio
    contrast_ratio = (img_max - img_min) / 255
    
    print(f"Image statistics: min={img_min}, max={img_max}, mean={img_mean:.1f}, std={img_std:.1f}")
    print(f"Image contrast ratio: {contrast_ratio:.2f}")
    
    # Low contrast images need more conservative alpha matting parameters
    if contrast_ratio < 0.4 or img_std < 30:
        print("Low contrast image detected, using conservative alpha matting parameters")
        return {
            "alpha_matting": True,
            "alpha_matting_foreground_threshold": 220,  # Less aggressive threshold
            "alpha_matting_background_threshold": 20,
            "alpha_matting_erode_size": 15,
            "alpha_matting_discard_threshold": 0.0001,  # Default value
            "alpha_matting_shift": 0.02  # Add a small shift for stability
        }
    # Medium contrast images
    elif contrast_ratio < 0.7:
        print("Medium contrast image detected, using standard alpha matting parameters")
        return {
            "alpha_matting": True,
            "alpha_matting_foreground_threshold": 240,
            "alpha_matting_background_threshold": 10,
            "alpha_matting_erode_size": 10,
            "alpha_matting_discard_threshold": 0.0001,
            "alpha_matting_shift": 0.01
        }
    # High contrast images can use more aggressive parameters
    else:
        print("High contrast image detected, using aggressive alpha matting parameters")
        return {
            "alpha_matting": True,
            "alpha_matting_foreground_threshold": 250,
            "alpha_matting_background_threshold": 5,
            "alpha_matting_erode_size": 5,
            "alpha_matting_discard_threshold": 0.0001,
            "alpha_matting_shift": 0.001
        }