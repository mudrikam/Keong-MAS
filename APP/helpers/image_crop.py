"""
Image cropping module for Keong-MAS application.
Provides functions to crop transparent images based on their masks.
"""
import os
import glob  # Add missing import
import logging
import numpy as np
from PIL import Image

from APP.helpers.config_manager import (
    get_auto_crop_enabled, 
    get_crop_detection_threshold,
    get_unified_margin,
    get_save_mask_enabled
)
from APP.helpers.cleanup_manager import register_file_in_use, unregister_file_in_use, cleanup_adjusted_mask_if_safe, intelligent_cleanup_after_all_operations

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
        margin = get_unified_margin()  # Use unified margin instead
        logger.info(f"Using unified margin of {margin}px from config")
    
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

def find_mask_file(mask_path, prefer_adjusted=True):
    """
    Tries to locate a mask file in various possible locations.
    Now prefers adjusted masks over original masks for better crop consistency.
    
    Args:
        mask_path (str): The initial mask path to look for
        prefer_adjusted (bool): If True, looks for adjusted masks first
        
    Returns:
        str: Path to found mask file, or None if not found
    """
    logger.info(f"Looking for mask file: {mask_path}")
    
    if os.path.exists(mask_path):
        logger.info(f"Found exact mask file: {mask_path}")
        return mask_path
        
    # Try to find the mask in different locations
    possible_locations = []
    file_name = os.path.splitext(os.path.basename(mask_path))[0]
    base_dir = os.path.dirname(mask_path)
    parent_dir = os.path.dirname(base_dir)
    
    logger.info(f"Base directory: {base_dir}")
    logger.info(f"Looking for file: {file_name}")
    
    # If prefer_adjusted is True, look for adjusted masks first
    if prefer_adjusted:
        # Extract the original file name from the transparent image path
        # Only remove suffixes that OUR application generates
        
        base_name = file_name
        
        # Remove only OUR application's suffixes (not _upscaled which is from other apps)
        our_suffixes = ['_transparent', '_mask_adjusted', '_mask', '_solid_background']
        for suffix in our_suffixes:
            if suffix in base_name:
                # Find the position and remove everything from that suffix onwards
                suffix_pos = base_name.find(suffix)
                if suffix_pos > 0:  # Make sure we don't remove the entire name
                    base_name = base_name[:suffix_pos]
                    break
        
        # Also remove timestamp patterns that OUR app generates like _5021
        import re
        # Only remove 4-digit timestamps at the end (our app's pattern)
        base_name = re.sub(r'_\d{4}$', '', base_name)
        
        # Don't remove other patterns like _upscaled, _20250522_215926 as they're from other apps
        
        logger.info(f"Original file name: {file_name}")
        logger.info(f"Extracted base name for adjusted mask search: {base_name}")
        
        # Search for adjusted masks in different locations
        search_dirs = [base_dir]
        
        # Add PNG subfolder if not already in PNG folder
        if os.path.basename(base_dir).upper() != 'PNG':
            png_dir = os.path.join(base_dir, 'PNG')
            search_dirs.append(png_dir)
        
        # Add parent's PNG subfolder
        png_dir = os.path.join(parent_dir, 'PNG')
        search_dirs.append(png_dir)
        
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
                
            logger.info(f"Searching in directory: {search_dir}")
            
            # Look for adjusted masks with any timestamp
            adjusted_pattern = os.path.join(search_dir, f"{base_name}_mask_adjusted_*.png")
            adjusted_masks = glob.glob(adjusted_pattern)
            
            logger.info(f"Pattern: {adjusted_pattern}")
            logger.info(f"Found {len(adjusted_masks)} adjusted masks: {adjusted_masks}")
            
            if adjusted_masks:
                # Use the most recent adjusted mask
                adjusted_masks.sort(key=os.path.getmtime, reverse=True)
                logger.info(f"Using most recent adjusted mask: {adjusted_masks[0]}")
                return adjusted_masks[0]
    
    # Fallback to original mask search logic
    logger.info("No adjusted masks found, falling back to original mask search")
    
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
    Now uses centralized cleanup manager for safe mask handling.
    
    Args:
        image_path (str): Path to the transparent image
        mask_path (str): Path to the mask image
        output_path (str, optional): Path to save the cropped image. If None, overwrites the input
        threshold (int, optional): For backward compatibility - used as margin if provided
                        
    Returns:
        str: Path to the cropped image, or original image path if cropping failed
    """
    actual_mask_path = None
    try:
        logger.info(f"=== CROP DEBUG INFO ===")
        logger.info(f"Input image: {os.path.basename(image_path)}")
        logger.info(f"Input mask: {os.path.basename(mask_path)}")
        
        # Check if auto crop is enabled in config
        auto_crop_enabled = get_auto_crop_enabled()
        logger.info(f"Auto crop config setting: {auto_crop_enabled}")
        
        # Find adjusted masks
        actual_mask_path = find_mask_file(mask_path, prefer_adjusted=True)
        
        # Register mask as in use if found
        if actual_mask_path:
            register_file_in_use(actual_mask_path)
        
        if not auto_crop_enabled:
            logger.info(f"SKIPPING CROP: Auto crop is disabled in config")
            # Unregister mask since we're not using it
            if actual_mask_path:
                unregister_file_in_use(actual_mask_path)
            return image_path
            
        # Get detection threshold and margin from config
        detection_threshold = get_crop_detection_threshold()
        
        # Always use unified margin unless explicitly overridden by threshold parameter
        margin = get_unified_margin() if threshold is None else threshold
        
        logger.info(f"Detection threshold: {detection_threshold}, Margin: {margin}px")
        
        if not actual_mask_path:
            logger.warning(f"SKIPPING CROP: Mask file not found for {image_path}")
            return image_path
        
        # Log which type of mask we're using
        if "_mask_adjusted_" in actual_mask_path:
            logger.info(f"Using adjusted mask for consistent cropping: {os.path.basename(actual_mask_path)}")
        else:
            logger.info(f"Using original mask: {os.path.basename(actual_mask_path)}")
        
        # Load images
        image = Image.open(image_path)
        mask = Image.open(actual_mask_path)
        
        logger.info(f"Image size: {image.size}, Mask size: {mask.size}")
        
        # Get crop bounds
        bounds = get_crop_bounds(mask, detection_threshold=detection_threshold, margin=margin)
        
        if not bounds:
            logger.info(f"SKIPPING CROP: No cropping necessary for {os.path.basename(image_path)}")
            # Unregister mask since we're done with it
            unregister_file_in_use(actual_mask_path)
            return image_path
        
        logger.info(f"APPLYING CROP: Bounds = {bounds}")
        
        # Crop the image
        cropped_image = image.crop(bounds)
        
        # Save the cropped image
        if not output_path:
            output_path = image_path
        
        cropped_image.save(output_path)
        logger.info(f"CROP SUCCESS: Cropped image saved to {output_path}")
        
        # Unregister mask since we're done with it
        unregister_file_in_use(actual_mask_path)
        
        # INTELLIGENT CLEANUP: Check if this is the final operation and cleanup if needed
        logger.info("CROP: Checking if intelligent cleanup should run after cropping...")
        intelligent_cleanup_after_all_operations(output_path, ["crop"])
        
        return output_path
    
    except Exception as e:
        logger.error(f"CROP ERROR: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        # Unregister mask on error
        if actual_mask_path:
            unregister_file_in_use(actual_mask_path)
        return image_path  # Return original image path in case of error

# Remove old cleanup functions - they're now handled by cleanup_manager
def cleanup_adjusted_mask_if_needed(mask_path):
    """
    DEPRECATED: Use cleanup_manager instead.
    Kept for backwards compatibility.
    """
    logger.warning("cleanup_adjusted_mask_if_needed is deprecated, use cleanup_manager instead")
    return cleanup_adjusted_mask_if_safe(mask_path)

def cleanup_masks_after_processing(image_path):
    """
    DEPRECATED: Use cleanup_manager.final_cleanup_for_image instead.
    Kept for backwards compatibility.
    """
    logger.warning("cleanup_masks_after_processing is deprecated, use cleanup_manager.final_cleanup_for_image instead")
    from APP.helpers.cleanup_manager import final_cleanup_for_image
    final_cleanup_for_image(image_path)

def final_cleanup_all_masks(image_path):
    """
    DEPRECATED: Use cleanup_manager.final_cleanup_for_image instead.
    Kept for backwards compatibility.
    """
    logger.warning("final_cleanup_all_masks is deprecated, use cleanup_manager.final_cleanup_for_image instead")
    from APP.helpers.cleanup_manager import final_cleanup_for_image
    final_cleanup_for_image(image_path)