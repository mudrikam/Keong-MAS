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
from APP.helpers.cleanup_manager import intelligent_cleanup_after_all_operations

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

def composite_layers_like_graphics_software(foreground, background):
    """
    Composites two images like professional graphics software would, preserving RGB values
    and using edge refinement to eliminate dark fringing.
    
    Args:
        foreground (PIL.Image): The foreground RGBA image with transparency
        background (PIL.Image): The background RGBA image (usually solid color)
        
    Returns:
        PIL.Image: The composited image with clean edges and no dark fringing
    """
    # Ensure both images are RGBA
    fg = foreground.convert("RGBA")
    bg = background.convert("RGBA")
    
    # Make sure the images are the same size
    if fg.size != bg.size:
        logger.warning("Foreground and background sizes don't match. Resizing background.")
        bg = bg.resize(fg.size, Image.LANCZOS)
    
    # Convert to numpy arrays for pixel-level processing
    fg_array = np.array(fg, dtype=np.float32) / 255.0
    bg_array = np.array(bg, dtype=np.float32) / 255.0
      # Extract the RGB and Alpha channels
    fg_rgb = fg_array[:, :, :3]
    fg_alpha = fg_array[:, :, 3]
    bg_rgb = bg_array[:, :, :3]
    bg_alpha = bg_array[:, :, 3]
    
    # Create a 3D alpha for broadcasting (shape: height, width, 1)
    fg_alpha_3d = fg_alpha[:, :, np.newaxis]
    bg_alpha_3d = bg_alpha[:, :, np.newaxis]
    
    # Apply edge refinement similar to apply_levels_to_mask:
    # This helps eliminate dark fringing by adjusting semi-transparent pixels
    
    # Values from image_utils.py for better edge control
    black_point = 20   # Higher values make more pixels fully transparent (removes dark fringe)
    mid_point = 128    # No change to midtones by default
    white_point = 235  # Lower values make more pixels fully opaque (cleanup light fringe)
    
    # Apply levels adjustment to alpha channel
    refined_alpha = np.clip(fg_alpha, black_point/255.0, white_point/255.0)
    refined_alpha = (refined_alpha - black_point/255.0) / max(0.001, (white_point - black_point)/255.0)
    
    # Apply gamma correction if needed
    if mid_point != 128:
        gamma = 1.0
        if mid_point < 128:
            gamma = 1.0 + (128.0 - mid_point) / 128.0
        else:
            gamma = 128.0 / mid_point
        refined_alpha = np.power(refined_alpha, 1.0/gamma)
    
    # Use the refined alpha for compositing
    refined_alpha_3d = refined_alpha[:, :, np.newaxis]
    
    # Compute the output alpha with refined values
    out_alpha = refined_alpha_3d + bg_alpha_3d * (1.0 - refined_alpha_3d)
    
    # Key step: Layer compositing with straight (non-premultiplied) alpha and refined edges
    # This eliminates dark fringing by properly adjusting the alpha channel
    out_rgb = fg_rgb * refined_alpha_3d + bg_rgb * (1.0 - refined_alpha_3d)
    
    # Combine the RGB and Alpha channels
    out_array = np.zeros((fg_array.shape[0], fg_array.shape[1], 4), dtype=np.float32)
    out_array[:, :, :3] = out_rgb
    out_array[:, :, 3] = np.squeeze(out_alpha)
    
    # Convert back to 8-bit values
    out_array_8bit = (out_array * 255.0).astype(np.uint8)
    
    # Create a PIL Image from the array
    result = Image.fromarray(out_array_8bit, mode="RGBA")
    
    return result

def add_solid_background(image_path, output_path=None, bg_color=None, margin=None):
    """
    Adds a solid background to a transparent image with smart margins.
    Uses a graphics software-like layer composition approach for clean edges.
    
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
        
        # Get the base directory and file name of the input image
        base_dir = os.path.dirname(image_path)
        file_name = os.path.splitext(os.path.basename(image_path))[0]
        
        # Get pure file name without any suffixes
        if "_transparent" in file_name:
            # Extract timestamp ID if present
            import re
            timestamp_match = re.search(r'_transparent_(\d+)', file_name)
            timestamp_id = timestamp_match.group(1) if timestamp_match else None
            file_name = file_name.replace("_transparent", "")
            # Remove timestamp if present
            if timestamp_id:
                file_name = file_name.replace(f"_{timestamp_id}", "")
        
        # Determine PNG directory
        if os.path.basename(base_dir).upper() == 'PNG':
            png_dir = base_dir
        else:
            png_dir = os.path.join(base_dir, 'PNG')
        
        # Create timestamp-based identifier to prevent overwriting previous outputs
        import time
        timestamp_id = int(time.time()) % 10000  # Use last 4 digits of timestamp
        
        # Try to extract timestamp ID from input file if it exists
        if "_transparent_" in image_path:
            import re
            match = re.search(r'_transparent_(\d+)', image_path)
            if match:
                timestamp_id = match.group(1)
        
        # Always use the _transparent.png file from the PNG directory
        transparent_img_path = os.path.join(png_dir, f"{file_name}_transparent_{timestamp_id}.png")
        
        # If exact match with timestamp doesn't exist, try to find any transparent file for this image
        if not os.path.exists(transparent_img_path):
            # Try without the timestamp ID
            basic_transparent_path = os.path.join(png_dir, f"{file_name}_transparent.png")
            if os.path.exists(basic_transparent_path):
                transparent_img_path = basic_transparent_path
            else:
                # Try to find any transparent file with this base name
                import glob
                pattern = os.path.join(png_dir, f"{file_name}_transparent_*.png")
                matches = glob.glob(pattern)
                if matches:
                    transparent_img_path = matches[0]  # Use the first match
        
        # Check if the transparent image exists
        if not os.path.exists(transparent_img_path):
            logger.warning(f"Enhanced transparent image not found at {transparent_img_path}")
            # If we're already using a PNG file, use it as-is
            if image_path.lower().endswith('.png'):
                transparent_img_path = image_path
            else:
                logger.error("No valid transparent image found")
                return None
        
        # Log settings
        logger.info(f"Adding solid background to {os.path.basename(transparent_img_path)}")
        logger.info(f"Background color: {bg_color}, margin: {margin}px")
        
        # Create output path if not provided
        if output_path is None:
            output_path = os.path.join(png_dir, f"{file_name}_solid_background_{timestamp_id}.png")
        
        # Open the transparent image
        orig_img = Image.open(transparent_img_path).convert("RGBA")
        width, height = orig_img.size
        
        # Find the content bounds
        content_bounds = get_content_bounds(orig_img)
        
        # Calculate smart margins
        left_margin, top_margin, right_margin, bottom_margin = calculate_smart_margins(
            content_bounds, orig_img.size, margin
        )
        
        # Convert hex color to RGB
        bg_rgb = hex_to_rgb(bg_color)
        
        # Calculate dimensions with smart margins
        new_width = width + left_margin + right_margin
        new_height = height + top_margin + bottom_margin
          # ----- GRAPHICS SOFTWARE-LIKE LAYER COMPOSITING APPROACH -----
        
        # 1. Create a solid background layer (fully opaque)
        solid_bg = Image.new("RGBA", (new_width, new_height), (*bg_rgb, 255))
        
        # 2. Create a new transparent canvas for the foreground layer
        fg_layer = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))
        
        # 3. Place the transparent image onto the foreground layer at the proper position
        # This ensures we have two completely separate layers
        fg_layer.paste(orig_img, (left_margin, top_margin), orig_img)
        
        # 4. Composite the layers using the graphics software-like function
        # This preserves RGB values and uses straight alpha with edge refinement
        # to eliminate dark fringing that commonly occurs at transparent edges
        logger.info("Applying edge refinement during compositing (levels: 20/128/235) to eliminate dark fringing")
        result = composite_layers_like_graphics_software(fg_layer, solid_bg)
        
        # 5. Save the final composited image
        result.save(output_path)
        logger.info(f"Saved image with solid background to {output_path}")
        
        # INTELLIGENT CLEANUP: Check if this is the final operation and cleanup if needed
        logger.info("SOLID BG: Checking if intelligent cleanup should run after solid background...")
        intelligent_cleanup_after_all_operations(output_path, ["solid_background"])
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error adding solid background: {str(e)}")
        import traceback
        traceback.print_exc()
        return None
