"""
Image cropping module for Keong-MAS application.
Provides functions to crop transparent images based on their masks.
"""
import os
import logging
import numpy as np
from PIL import Image

from APP.helpers.config_manager import (
    get_auto_crop_enabled, 
    get_crop_detection_threshold,
    get_crop_margin
)

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ImageCrop")

def get_crop_bounds(mask_image, detection_threshold=None, margin=None):
    """
    Analyzes a mask to find crop boundaries.
    
    Args:
        mask_image (PIL.Image): The mask image (grayscale)
        detection_threshold (int): Pixel values below this threshold are considered transparent (0-255)
        margin (int): Margin in pixels to preserve around detected content
                        
    Returns:
        tuple: (left, top, right, bottom) crop coordinates, or None if no crop needed
    """
    # Use configured values if none provided
    if detection_threshold is None:
        detection_threshold = get_crop_detection_threshold()
        logger.info(f"Using detection threshold {detection_threshold} from config")
    
    if margin is None:
        margin = get_crop_margin()
        logger.info(f"Using margin of {margin}px from config")
    
    # Ensure mask is in grayscale mode
    mask = mask_image.convert("L")
    
    # Convert to numpy array for faster processing
    mask_array = np.array(mask, dtype=np.uint8)
    
    # Original size
    height, width = mask_array.shape
    logger.info(f"Original mask size: {width}x{height}")
    
    # Find the boundaries where the mask is not fully transparent
    # Using the detection threshold to find content edges
    
    # Find leftmost non-empty column
    left = 0
    while left < width:
        if np.max(mask_array[:, left]) > detection_threshold:
            break
        left += 1
    
    # Find rightmost non-empty column
    right = width - 1
    while right >= 0:
        if np.max(mask_array[:, right]) > detection_threshold:
            break
        right -= 1
    
    # Find topmost non-empty row
    top = 0
    while top < height:
        if np.max(mask_array[top, :]) > detection_threshold:
            break
        top += 1
    
    # Find bottommost non-empty row
    bottom = height - 1
    while bottom >= 0:
        if np.max(mask_array[bottom, :]) > detection_threshold:
            break
        bottom -= 1
    
    # If the entire image is empty or no significant crop possible, return None
    if left >= right or top >= bottom:
        logger.info("No significant crop possible - entire image is empty or crop area too small")
        return None
        
    # Apply the margin, ensuring we don't go out of bounds
    left = max(0, left - margin)
    top = max(0, top - margin)
    right = min(width, right + 1 + margin)  # Add 1 because PIL's crop is exclusive on right/bottom
    bottom = min(height, bottom + 1 + margin)
    
    # Calculate how much we're cropping
    crop_width = right - left
    crop_height = bottom - top
    width_reduction = width - crop_width
    height_reduction = height - crop_height
    width_percent = (width_reduction / width) * 100
    height_percent = (height_reduction / height) * 100
    
    logger.info(f"Detection threshold: {detection_threshold}, Margin: {margin}px")
    logger.info(f"Crop bounds: left={left}, top={top}, right={right}, bottom={bottom}")
    logger.info(f"Original: {width}x{height}, Cropped: {crop_width}x{crop_height}")
    logger.info(f"Reduced by: {width_reduction}px ({width_percent:.1f}%) width, {height_reduction}px ({height_percent:.1f}%) height")
    
    return (left, top, right, bottom)

def find_mask_file(mask_path):
    """
    Tries to locate a mask file in various possible locations
    
    Args:
        mask_path (str): The initial mask path to look for
        
    Returns:
        str: Path to found mask file, or None if not found
    """
    if os.path.exists(mask_path):
        return mask_path
        
    # Try to find the mask in different locations
    possible_locations = []
    file_name = os.path.splitext(os.path.basename(mask_path))[0]
    base_dir = os.path.dirname(mask_path)
    parent_dir = os.path.dirname(base_dir)
    
    # Try in a PNG subfolder
    if os.path.basename(base_dir).upper() != 'PNG':
        png_dir = os.path.join(base_dir, 'PNG')
        possible_locations.append(os.path.join(png_dir, os.path.basename(mask_path)))
    
    # Try in parent directory
    possible_locations.append(os.path.join(parent_dir, os.path.basename(mask_path)))
    
    # Try in parent's PNG subfolder
    png_dir = os.path.join(parent_dir, 'PNG')
    possible_locations.append(os.path.join(png_dir, os.path.basename(mask_path)))
    
    # Check all locations
    for loc in possible_locations:
        logger.debug(f"Checking alternative location: {loc}")
        if os.path.exists(loc):
            logger.info(f"Found mask at alternative location: {loc}")
            return loc
            
    logger.warning(f"Mask not found at any expected location: {mask_path}")
    return None

def crop_transparent_image(image_path, mask_path, output_path=None, threshold=None):
    """
    Crops a transparent image based on its mask.
    
    Args:
        image_path (str): Path to the transparent image
        mask_path (str): Path to the mask image
        output_path (str, optional): Path to save the cropped image. If None, overwrites the input
        threshold (int, optional): For backward compatibility - used as margin if provided
                        
    Returns:
        str: Path to the cropped image, or original image path if cropping failed
    """
    try:
        # Get detection threshold and margin from config
        detection_threshold = get_crop_detection_threshold()
        margin = get_crop_margin() if threshold is None else threshold
        
        logger.info(f"Cropping image: {os.path.basename(image_path)}")
        logger.info(f"Detection threshold: {detection_threshold}, Margin: {margin}px")
        
        # Check if auto crop is enabled in config
        auto_crop_enabled = get_auto_crop_enabled()
        logger.info(f"Auto crop is {'enabled' if auto_crop_enabled else 'disabled'} in config.json")
        
        if not auto_crop_enabled:
            logger.info(f"Skipping crop as auto crop is disabled in config")
            return image_path
            
        # Find the mask file
        actual_mask_path = find_mask_file(mask_path)
        if not actual_mask_path:
            logger.warning(f"Mask file not found for {image_path}")
            return image_path
        
        # Load images
        image = Image.open(image_path)
        mask = Image.open(actual_mask_path)
        
        # Get crop bounds
        bounds = get_crop_bounds(mask, detection_threshold=detection_threshold, margin=margin)
        
        if not bounds:
            logger.info(f"No cropping necessary for {os.path.basename(image_path)}")
            return image_path
        
        # Crop the image
        cropped_image = image.crop(bounds)
        
        # Save the cropped image
        if not output_path:
            output_path = image_path
        
        cropped_image.save(output_path)
        logger.info(f"Cropped image saved to {output_path}")
        
        return output_path
    
    except Exception as e:
        logger.error(f"Error cropping image: {str(e)}")
        return image_path  # Return original image path in case of error