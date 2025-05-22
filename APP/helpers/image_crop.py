import os
import json
import numpy as np
from PIL import Image

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
            "image_cropping": {
                "enable": True,
                "crop_treshold": 10
            }
        }

def save_config(config):
    """
    Saves the configuration to config.json file
    
    Args:
        config (dict): Configuration values to save
    """
    try:
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        print(f"Warning: Could not save config.json: {e}")
        return False

def get_crop_bounds(mask_image, threshold=10):
    """
    Analyzes a mask to find crop boundaries.
    Areas with alpha/grayscale value less than the threshold are considered "empty".
    
    Args:
        mask_image (PIL.Image): The mask image (grayscale)
        threshold (int): Pixel values below this threshold are considered transparent/empty
                        
    Returns:
        tuple: (left, top, right, bottom) crop coordinates, or None if no crop needed
    """
    # Ensure mask is in grayscale mode
    mask = mask_image.convert("L")
    
    # Convert to numpy array for faster processing
    mask_array = np.array(mask, dtype=np.uint8)
    
    # Original size
    height, width = mask_array.shape
    print(f"Original mask size: {width}x{height}")
    
    # Find the boundaries where the mask is not fully transparent
    # Find leftmost non-empty column
    left = 0
    while left < width:
        if np.max(mask_array[:, left]) > threshold:
            break
        left += 1
    
    # Find rightmost non-empty column
    right = width - 1
    while right >= 0:
        if np.max(mask_array[:, right]) > threshold:
            break
        right -= 1
    
    # Find topmost non-empty row
    top = 0
    while top < height:
        if np.max(mask_array[top, :]) > threshold:
            break
        top += 1
    
    # Find bottommost non-empty row
    bottom = height - 1
    while bottom >= 0:
        if np.max(mask_array[bottom, :]) > threshold:
            break
        bottom -= 1
    
    # If the entire image is empty or no significant crop possible, return None
    if left >= right or top >= bottom:
        print("No significant crop possible - entire image is empty or crop area too small")
        return None
    
    # Add 1 to right and bottom to make them inclusive (PIL crop takes exclusive coordinates)
    right += 1
    bottom += 1
    
    # Calculate how much we're cropping
    crop_width = right - left
    crop_height = bottom - top
    width_reduction = width - crop_width
    height_reduction = height - crop_height
    width_percent = (width_reduction / width) * 100
    height_percent = (height_reduction / height) * 100
    
    print(f"Crop bounds: left={left}, top={top}, right={right}, bottom={bottom}")
    print(f"Original: {width}x{height}, Cropped: {crop_width}x{crop_height}")
    print(f"Reduced by: {width_reduction}px ({width_percent:.1f}%) width, {height_reduction}px ({height_percent:.1f}%) height")
    
    return (left, top, right, bottom)

def crop_transparent_image(image_path, mask_path, output_path=None, threshold=10):
    """
    Crops a transparent image based on its mask.
    
    Args:
        image_path (str): Path to the transparent image
        mask_path (str): Path to the mask image
        output_path (str, optional): Path to save the cropped image. If None, overwrites the input
        threshold (int): Pixel values below this are considered transparent
                        
    Returns:
        str: Path to the cropped image, or None if cropping failed
    """
    try:
        # Verify the mask file exists
        if not os.path.exists(mask_path):
            print(f"Error: Mask file not found at {mask_path}")
            # Try to find the mask in different locations
            possible_locations = []
            file_name = os.path.splitext(os.path.basename(mask_path))[0]
            base_dir = os.path.dirname(mask_path)
            parent_dir = os.path.dirname(base_dir)
            
            # Try in the same directory
            possible_locations.append(mask_path)
            
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
                print(f"Checking alternative location: {loc}")
                if os.path.exists(loc):
                    print(f"Found mask at alternative location: {loc}")
                    mask_path = loc
                    break
            else:
                # If not found in any location
                return image_path
        
        # Load images
        image = Image.open(image_path)
        mask = Image.open(mask_path)
        
        # Get crop bounds
        bounds = get_crop_bounds(mask, threshold)
        
        if not bounds:
            print(f"No cropping necessary for {os.path.basename(image_path)}")
            return image_path
        
        # Crop the image
        cropped_image = image.crop(bounds)
        
        # Save the cropped image
        if not output_path:
            output_path = image_path
        
        cropped_image.save(output_path)
        print(f"Cropped image saved to {output_path}")
        
        return output_path
    
    except Exception as e:
        print(f"Error cropping image: {str(e)}")
        return None

def update_auto_crop_setting(enabled):
    """
    Updates the auto crop setting in the config file
    
    Args:
        enabled (bool): Whether auto cropping should be enabled
    
    Returns:
        bool: True if the setting was successfully updated, False otherwise
    """
    try:
        # Load current config
        config = load_config()
        
        # Make sure the necessary structure exists
        if "image_cropping" not in config:
            config["image_cropping"] = {}
        
        # Update the setting
        config["image_cropping"]["enable"] = enabled
        
        # Save the updated config
        return save_config(config)
    
    except Exception as e:
        print(f"Error updating auto crop setting: {str(e)}")
        return False

def get_auto_crop_setting():
    """
    Gets the current auto crop setting from the config file
    
    Returns:
        bool: Whether auto cropping is enabled
    """
    config = load_config()
    return config.get("image_cropping", {}).get("enable", True)

def get_crop_threshold():
    """
    Gets the crop threshold from the config file
    
    Returns:
        int: The threshold value for cropping
    """
    config = load_config()
    return config.get("image_cropping", {}).get("crop_treshold", 10)