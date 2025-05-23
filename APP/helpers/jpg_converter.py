"""
JPG converter module for Keong-MAS application.
Provides functions to convert PNG images with solid backgrounds to JPG format.
"""
import os
import logging
from PIL import Image

from APP.helpers.config_manager import get_jpg_export_enabled, get_jpg_quality, get_solid_bg_enabled

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
            
        # Use config value if quality not provided
        if quality is None:
            quality = get_jpg_quality()
        
        # Ensure quality is within valid range
        quality = max(1, min(100, quality))
        
        # Get the base directory and file name of the input image
        base_dir = os.path.dirname(image_path)
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Remove any suffixes from the filename to get the original name
        if "_solid_background" in file_name:
            file_name = file_name.replace("_solid_background", "")
        elif "_transparent" in file_name:
            file_name = file_name.replace("_transparent", "")
        
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
        
        # Determine input path based on whether solid background is enabled
        solid_bg_enabled = get_solid_bg_enabled()
        
        if solid_bg_enabled:
            # Try to use solid background version first
            solid_bg_path = os.path.join(png_dir, f"{file_name}_solid_background.png")
            if os.path.exists(solid_bg_path):
                input_path = solid_bg_path
                logger.info(f"Using solid background image: {os.path.basename(input_path)}")
            else:
                # Fallback to transparent version with white background
                transparent_path = os.path.join(png_dir, f"{file_name}_transparent.png") 
                if os.path.exists(transparent_path):
                    input_path = transparent_path
                    logger.info(f"Solid background not found, using transparent with white background: {os.path.basename(input_path)}")
                else:
                    # Final fallback to provided path
                    input_path = image_path
                    logger.info(f"Using provided image path: {os.path.basename(input_path)}")
        else:
            # When solid background is disabled, use transparent version
            transparent_path = os.path.join(png_dir, f"{file_name}_transparent.png")
            if os.path.exists(transparent_path):
                input_path = transparent_path
                logger.info(f"Solid background disabled, using transparent with white background: {os.path.basename(input_path)}")
            else:
                # Fallback to provided path
                input_path = image_path
                logger.info(f"Using provided image path: {os.path.basename(input_path)}")
        
        # Create output path in JPG directory if not provided
        if output_path is None:
            output_path = os.path.join(jpg_dir, f"{file_name}.jpg")
        
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
    
    return convert_to_jpg(image_path)
