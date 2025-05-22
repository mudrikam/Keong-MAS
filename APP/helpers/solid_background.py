"""
Solid background module for Keong-MAS application.
Provides functions to add a solid background to transparent images.
"""
import os
import logging
import numpy as np
from PIL import Image

from APP.helpers.config_manager import (
    get_solid_bg_enabled,
    get_solid_bg_color,
    get_solid_bg_margin
)

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SolidBackground")

def hex_to_rgb(hex_color):
    """
    Convert hex color string to RGB tuple
    
    Args:
        hex_color (str): Color in hex format (e.g., #FFFFFF)
        
    Returns:
        tuple: RGB values as (r, g, b)
    """
    # Remove # if present
    hex_color = hex_color.lstrip('#')
    
    # Convert to RGB
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def get_content_bounds(image):
    """
    Analyze the alpha channel to find the bounds of the actual content
    
    Args:
        image (PIL.Image): Transparent image with alpha channel
        
    Returns:
        tuple: (left, top, right, bottom) bounds of content
    """
    # Convert to numpy array and extract alpha channel
    img_array = np.array(image)
    if img_array.shape[2] < 4:  # Not RGBA
        logger.warning("Image doesn't have an alpha channel, using full dimensions")
        height, width = img_array.shape[:2]
        return 0, 0, width, height
    
    alpha = img_array[:, :, 3]
    
    # Find the boundaries where content exists (non-zero alpha)
    height, width = alpha.shape
    
    # Use a threshold to determine what counts as "content"
    threshold = 5  # Low threshold to detect almost transparent pixels too
    
    # Find bounds (similar to image_crop logic)
    # Find leftmost non-empty column
    left = 0
    while left < width:
        if np.max(alpha[:, left]) > threshold:
            break
        left += 1
    
    # Find rightmost non-empty column
    right = width - 1
    while right >= 0:
        if np.max(alpha[:, right]) > threshold:
            break
        right -= 1
    
    # Find topmost non-empty row
    top = 0
    while top < height:
        if np.max(alpha[top, :]) > threshold:
            break
        top += 1
    
    # Find bottommost non-empty row
    bottom = height - 1
    while bottom >= 0:
        if np.max(alpha[bottom, :]) > threshold:
            break
        bottom -= 1
    
    # If the entire image is empty, return full dimensions
    if left >= right or top >= bottom:
        logger.warning("No content detected in image, using full dimensions")
        return 0, 0, width, height
    
    # Add 1 to make bounds inclusive
    right += 1
    bottom += 1
    
    logger.info(f"Content bounds: left={left}, top={top}, right={right}, bottom={bottom}")
    return left, top, right, bottom

def calculate_smart_margins(content_bounds, image_size, requested_margin):
    """
    Calculate margins that respect the content position within the image
    
    Args:
        content_bounds (tuple): (left, top, right, bottom) bounds of content
        image_size (tuple): (width, height) of the image
        requested_margin (int): Desired margin
        
    Returns:
        tuple: (left_margin, top_margin, right_margin, bottom_margin)
    """
    width, height = image_size
    left, top, right, bottom = content_bounds
    
    # Calculate the available space on each side
    available_left = left
    available_top = top
    available_right = width - right
    available_bottom = height - bottom
    
    # Apply the requested margin where possible, otherwise use what's available
    left_margin = min(requested_margin, available_left)
    top_margin = min(requested_margin, available_top)
    right_margin = min(requested_margin, available_right)
    bottom_margin = min(requested_margin, available_bottom)
    
    logger.info(f"Smart margins: left={left_margin}, top={top_margin}, right={right_margin}, bottom={bottom_margin} (requested={requested_margin})")
    return left_margin, top_margin, right_margin, bottom_margin

def add_solid_background(image_path, output_path=None, bg_color=None, margin=None):
    """
    Adds a solid background to a transparent image with smart margins
    
    Args:
        image_path (str): Path to the transparent image
        output_path (str, optional): Path to save the new image with background
        bg_color (str, optional): Background color in hex format (#RRGGBB)
        margin (int, optional): Maximum margin to add around the image
        
    Returns:
        str: Path to the new image with background
    """
    try:
        # Check if solid background is enabled
        if not get_solid_bg_enabled():
            logger.info("Solid background generation is disabled in config")
            return None
            
        # Use config values if not provided
        if bg_color is None:
            bg_color = get_solid_bg_color()
        
        if margin is None:
            margin = get_solid_bg_margin()
            
        # Log settings
        logger.info(f"Adding solid background to {os.path.basename(image_path)}")
        logger.info(f"Background color: {bg_color}, margin: {margin}px")
        
        # Create output path if not provided
        if output_path is None:
            base_dir = os.path.dirname(image_path)
            file_name = os.path.splitext(os.path.basename(image_path))[0]
            # Remove any existing suffixes like "_transparent"
            if "_transparent" in file_name:
                file_name = file_name.replace("_transparent", "")
            output_path = os.path.join(base_dir, f"{file_name}_solid_background.png")
        
        # Open the transparent image
        img = Image.open(image_path).convert("RGBA")
        
        # Find the content bounds
        content_bounds = get_content_bounds(img)
        
        # Calculate smart margins
        left_margin, top_margin, right_margin, bottom_margin = calculate_smart_margins(
            content_bounds, img.size, margin
        )
        
        # Convert hex color to RGB
        bg_rgb = hex_to_rgb(bg_color)
        
        # Calculate dimensions with smart margins
        width, height = img.size
        new_width = width + left_margin + right_margin
        new_height = height + top_margin + bottom_margin
        
        # Create a new image with smart margins
        bg_img = Image.new("RGBA", (new_width, new_height), (*bg_rgb, 255))
        
        # Calculate position to place the original image
        pos_x = left_margin
        pos_y = top_margin
        
        # Paste the transparent image onto the background
        # The alpha channel of the original image will control the blending
        bg_img.paste(img, (pos_x, pos_y), img)
        
        # Save the result
        bg_img.save(output_path)
        logger.info(f"Saved image with solid background to {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error adding solid background: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
