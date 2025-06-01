"""
JPG converter module for Keong-MAS application.
Provides functions to convert PNG images with solid backgrounds to JPG format.
"""
import os
import logging
import time
import re
from PIL import Image

from APP.helpers.config_manager import get_jpg_export_enabled, get_jpg_quality, get_solid_bg_enabled
from APP.helpers.cleanup_manager import intelligent_cleanup_after_all_operations

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JPGConverter")

def convert_to_jpg(image_path, output_path=None, quality=None):
    """
    Converts a PNG image with solid background to JPG format.
    
    Args:
        image_path (str): Path to the PNG image with solid background
        output_path (str, optional): Path to save the JPG image
        quality (int, optional): JPG quality (1-100, default from config)
        
    Returns:
        str: Path to the JPG image if successful, None otherwise
    """
    try:
        # Check if JPG export is enabled
        if not get_jpg_export_enabled():
            logger.info("JPG export is disabled in config")
            return None
            
        # Import config functions we need
        from APP.helpers.config_manager import get_auto_crop_enabled
        
        # Use config value if quality not provided
        if quality is None:
            quality = get_jpg_quality()
        
        # Ensure quality is within valid range
        quality = max(1, min(100, quality))
        
        # Get the base directory and file name of the input image
        base_dir = os.path.dirname(image_path)
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Create timestamp-based identifier to prevent overwriting previous outputs
        timestamp_id = int(time.time()) % 10000  # Use last 4 digits of timestamp
        
        # Try to extract timestamp ID from input file if it exists
        if "_transparent_" in image_path or "_solid_background_" in image_path:
            match = re.search(r'_(transparent|solid_background)_(\d+)', image_path)
            if match:
                timestamp_id = match.group(2)
        
        # Remove any suffixes from the filename to get the original name
        if "_solid_background" in file_name:
            file_name = file_name.replace("_solid_background", "")
            # Remove timestamp if present
            if "_" in file_name and file_name.split("_")[-1].isdigit():
                file_name = "_".join(file_name.split("_")[:-1])
        elif "_transparent" in file_name:
            file_name = file_name.replace("_transparent", "")
            # Remove timestamp if present
            if "_" in file_name and file_name.split("_")[-1].isdigit():
                file_name = "_".join(file_name.split("_")[:-1])
        
        # Determine PNG directory and prepare JPG directory
        original_dir = base_dir
        if os.path.basename(base_dir).upper() == 'PNG':
            png_dir = base_dir
            parent_dir = os.path.dirname(base_dir)
            jpg_dir = os.path.join(parent_dir, 'JPG')  # Create JPG folder adjacent to PNG
        else:
            png_dir = os.path.join(base_dir, 'PNG')
            jpg_dir = os.path.join(base_dir, 'JPG')  # Create JPG folder adjacent to PNG
        
        # Create JPG directory if it doesn't exist
        os.makedirs(jpg_dir, exist_ok=True)
        logger.info(f"JPG output directory: {jpg_dir}")
        
        # Determine input path based on config settings
        solid_bg_enabled = get_solid_bg_enabled()
        crop_enabled = get_auto_crop_enabled()
        
        input_path = None
        
        # Priority order based on enabled features:
        # 1. If both solid BG and crop are enabled: use solid background version (it should be cropped already)
        # 2. If only solid BG enabled: use solid background version  
        # 3. If only crop enabled: use transparent version (it should be cropped already)
        # 4. If neither enabled: use transparent version
        
        if solid_bg_enabled:
            # Look for solid background version with or without timestamp
            patterns_to_try = [
                os.path.join(png_dir, f"{file_name}_solid_background_{timestamp_id}.png"),
                os.path.join(png_dir, f"{file_name}_solid_background.png")
            ]
            
            for pattern in patterns_to_try:
                if os.path.exists(pattern):
                    input_path = pattern
                    logger.info(f"Using solid background image: {os.path.basename(input_path)}")
                    break
        
        # If no solid background found or solid BG disabled, look for transparent version
        if not input_path:
            patterns_to_try = [
                os.path.join(png_dir, f"{file_name}_transparent_{timestamp_id}.png"),
                os.path.join(png_dir, f"{file_name}_transparent.png")
            ]
            
            for pattern in patterns_to_try:
                if os.path.exists(pattern):
                    input_path = pattern
                    if crop_enabled:
                        logger.info(f"Using transparent image (should be cropped): {os.path.basename(input_path)}")
                    else:
                        logger.info(f"Using transparent image (not cropped): {os.path.basename(input_path)}")
                    break
        
        # Final fallback to provided path
        if not input_path:
            input_path = image_path
            logger.info(f"Using provided image path as fallback: {os.path.basename(input_path)}")
        
        # Create output path in JPG directory if not provided
        if output_path is None:
            output_path = os.path.join(jpg_dir, f"{file_name}_{timestamp_id}.jpg")
        
        # Open the input image 
        img = Image.open(input_path)
        
        # If image has alpha channel, composite it over white background
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            logger.info(f"Image has transparency, compositing over white background")
            # Create a white background image
            background = Image.new('RGB', img.size, (255, 255, 255))
            # Paste the image on the background using alpha as mask
            if img.mode == 'RGBA':
                background.paste(img, mask=img.split()[3])  # Use alpha channel as mask
            else:
                background.paste(img, mask=img)  # PIL handles transparency automatically
            img = background
        elif img.mode != 'RGB':
            # Convert other non-RGB modes to RGB
            img = img.convert('RGB')
        
        # Save as JPG with specified quality
        img.save(output_path, "JPEG", quality=quality, optimize=True)
        
        logger.info(f"Saved JPG: {output_path} (quality={quality})")
        logger.info(f"Config: crop_enabled={crop_enabled}, solid_bg_enabled={solid_bg_enabled}")
        
        # INTELLIGENT CLEANUP: Check if this is the final operation and cleanup if needed
        logger.info("JPG: Checking if intelligent cleanup should run after JPG conversion...")
        intelligent_cleanup_after_all_operations(output_path, ["jpg_export"])
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error converting to JPG: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def process_jpg_conversion(image_path):
    """
    Process JPG conversion for any PNG image (solid or transparent).
    This is a convenience function to be called after image processing.
    
    Args:
        image_path (str): Path to any PNG image (solid or transparent)
        
    Returns:
        str: Path to the JPG image if successful, None otherwise
    """
    if not image_path or not os.path.exists(image_path):
        logger.warning("No valid image path provided for JPG conversion")
        return None
        
    if not get_jpg_export_enabled():
        logger.info("JPG export is disabled in config")
        return None
    
    result = convert_to_jpg(image_path)
    
    # If this is being called directly (not from convert_to_jpg), also check for cleanup
    if result:
        logger.info("JPG PROCESS: Checking if intelligent cleanup should run after JPG processing...")
        intelligent_cleanup_after_all_operations(result, ["jpg_export"])
    
    return result
