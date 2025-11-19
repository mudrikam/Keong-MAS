"""
Configuration management module for Keong-MAS application.
Handles loading, saving, and accessing application settings.
"""
import os
import json
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ConfigManager")

# Default configuration values
DEFAULT_CONFIG = {
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
        },
        "unified_margin": 10,  # Unified margin setting for all operations
        "save_mask": True,  # Default setting for saving mask files
        "jpg_export": {
            "enabled": False,
            "quality": 90  # Default JPG quality (1-100)
        }
    },
    "image_cropping": {
        "enabled": False,
        "detection_threshold": 10  # Value 0-255 determining what is considered transparent
    },
    "solid_background": {
        "enabled": False,
        "color": "#FFFFFF"  # Default white background
    },
    "app": {
        "show_success_stats": True
    }
}

def get_config_path():
    """Get the absolute path to the config file"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config.json')

def load_config():
    """
    Load configuration from file or create with defaults if not exists
    
    Returns:
        dict: Configuration dictionary
    """
    config_path = get_config_path()
    
    try:
        # Check if file exists
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.info(f"Configuration loaded from {config_path}")
                
                # Handle any missing keys by merging with defaults
                merged_config = DEFAULT_CONFIG.copy()
                deep_update(merged_config, config)
                return merged_config
        else:
            # Create default config file
            with open(config_path, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
                logger.info(f"Created default configuration at {config_path}")
            return DEFAULT_CONFIG.copy()
    
    except Exception as e:
        logger.error(f"Error loading configuration: {str(e)}")
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """
    Save configuration to file
    
    Args:
        config (dict): Configuration to save
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    config_path = get_config_path()
    
    try:
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
            logger.info(f"Configuration saved to {config_path}")
        return True
    except Exception as e:
        logger.error(f"Error saving configuration: {str(e)}")
        return False

def deep_update(target, source):
    """
    Recursively update a nested dictionary without overwriting entire sections
    
    Args:
        target (dict): Dictionary to update
        source (dict): Dictionary with updates
    """
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_update(target[key], value)
        else:
            target[key] = value

def get_value(path, default=None):
    """
    Get a configuration value using dot notation path
    
    Args:
        path (str): Path to the value (e.g., 'image_cropping.enabled')
        default: Default value if path not found
        
    Returns:
        Value at the specified path or default
    """
    config = load_config()
    keys = path.split('.')
    
    # Navigate through the path
    current = config
    for key in keys:
        if key in current and current[key] is not None:
            current = current[key]
        else:
            return default
    
    return current

def set_value(path, value):
    """
    Set a configuration value using dot notation path
    
    Args:
        path (str): Path to the value (e.g., 'image_cropping.enabled')
        value: Value to set
        
    Returns:
        bool: True if saved successfully, False otherwise
    """
    config = load_config()
    keys = path.split('.')
    
    # Navigate to the parent of the target key
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    # Set the value
    current[keys[-1]] = value
    
    # Save the updated config
    return save_config(config)

# Specific accessor functions for commonly used settings
def get_auto_crop_enabled():
    """Get whether auto cropping is enabled"""
    return get_value('image_cropping.enabled', False)

def set_auto_crop_enabled(enabled):
    """Set whether auto cropping is enabled"""
    # Convert to boolean and ensure it's a new value
    enabled_bool = bool(enabled)
    current = get_auto_crop_enabled()
    
    # Only save if the value is different
    if current == enabled_bool:
        logger.info(f"Auto crop setting unchanged (already {'enabled' if enabled_bool else 'disabled'})")
        return True
        
    result = set_value('image_cropping.enabled', enabled_bool)
    logger.info(f"Auto crop {'enabled' if enabled_bool else 'disabled'} (saved: {result})")
    return result

def get_crop_detection_threshold():
    """Get the detection threshold value (0-255) for determining transparent areas"""
    return get_value('image_cropping.detection_threshold', 5)

def set_crop_detection_threshold(threshold):
    """Set the detection threshold value for determining transparent areas"""
    return set_value('image_cropping.detection_threshold', int(threshold))

# Unified margin setting
def get_unified_margin():
    """Get the unified margin value used for all operations"""
    margin = get_value('image_processing.unified_margin', 10)
    logger.info(f"Retrieving unified margin: {margin}px")
    return margin

def set_unified_margin(margin):
    """Set the unified margin value"""
    logger.info(f"Setting unified margin to {margin}px")
    return set_value('image_processing.unified_margin', int(margin))

# For backwards compatibility
def get_crop_margin():
    """Get the margin for cropping (using unified margin)"""
    return get_unified_margin()

def set_crop_margin(margin):
    """Set the margin for cropping (using unified margin)"""
    return set_unified_margin(margin)

# Solid background settings functions
def get_solid_bg_enabled():
    """Get whether solid background generation is enabled"""
    return get_value('solid_background.enabled', False)

def set_solid_bg_enabled(enabled):
    """Set whether solid background generation is enabled"""
    # Convert to boolean and ensure it's a new value
    enabled_bool = bool(enabled)
    current = get_solid_bg_enabled()
    
    # Only save if the value is different
    if current == enabled_bool:
        logger.info(f"Solid background setting unchanged (already {'enabled' if enabled_bool else 'disabled'})")
        return True
        
    result = set_value('solid_background.enabled', enabled_bool)
    logger.info(f"Solid background {'enabled' if enabled_bool else 'disabled'} (saved: {result})")
    return result

def get_solid_bg_color():
    """Get the solid background color"""
    return get_value('solid_background.color', '#FFFFFF')

def set_solid_bg_color(color_hex):
    """Set the solid background color"""
    # Ensure color is in proper hex format
    if not color_hex.startswith('#'):
        color_hex = f'#{color_hex}'
    
    # Convert to uppercase for consistency
    color_hex = color_hex.upper()
    
    return set_value('solid_background.color', color_hex)

def get_solid_bg_margin():
    """Get the margin for solid backgrounds (using unified margin)"""
    return get_unified_margin()

def set_solid_bg_margin(margin):
    """Set the margin for solid backgrounds (using unified margin)"""
    return set_unified_margin(margin)

# Backward compatibility - now returns the unified margin value
def get_crop_threshold():
    """Get the threshold value for cropping (for backward compatibility)"""
    margin = get_unified_margin()
    logger.info(f"get_crop_threshold called, returning unified margin: {margin}px")
    return margin

def get_save_mask_enabled():
    """
    Gets whether mask files should be saved
    
    Returns:
        bool: True if mask files should be saved, False otherwise
    """
    try:
        config = load_config()
        # Explicitly check if the value exists, otherwise return the default
        if "image_processing" in config and "save_mask" in config["image_processing"]:
            return config["image_processing"]["save_mask"]
        return False  # Default to False if not specified
    except Exception as e:
        print(f"Error getting save_mask setting: {str(e)}")
        return False  # Default to False on error

def set_save_mask_enabled(enabled):
    """
    Sets whether mask files should be saved
    
    Args:
        enabled (bool): True to save mask files, False to delete them
        
    Returns:
        bool: True if the setting was successfully saved, False otherwise
    """
    try:
        config = load_config()
        
        # Ensure the required structure exists
        if "image_processing" not in config:
            config["image_processing"] = {}
            
        # Update the setting
        config["image_processing"]["save_mask"] = enabled
        
        # Save the updated config
        save_config(config)
        return True
    except Exception as e:
        print(f"Error setting save_mask: {str(e)}")
        return False

# JPG export settings functions
def get_jpg_export_enabled():
    """Get whether JPG export is enabled"""
    return get_value('image_processing.jpg_export.enabled', False)

def set_jpg_export_enabled(enabled):
    """Set whether JPG export is enabled"""
    # Convert to boolean and ensure it's a new value
    enabled_bool = bool(enabled)
    current = get_jpg_export_enabled()
    
    # Only save if the value is different
    if current == enabled_bool:
        logger.info(f"JPG export setting unchanged (already {'enabled' if enabled_bool else 'disabled'})")
        return True
        
    result = set_value('image_processing.jpg_export.enabled', enabled_bool)
    logger.info(f"JPG export {'enabled' if enabled_bool else 'disabled'} (saved: {result})")
    return result

def get_jpg_quality():
    """Get the JPG quality setting (1-100)"""
    quality = get_value('image_processing.jpg_export.quality', 90)
    return max(1, min(100, quality))  # Ensure it's within valid range

def set_jpg_quality(quality):
    """Set the JPG quality setting (1-100)"""
    quality_int = max(1, min(100, int(quality)))
    return set_value('image_processing.jpg_export.quality', quality_int)

def get_output_location():
    """Get the custom output location if set, otherwise None (defaults to PNG folder)"""
    return get_value('app.output_location', None)

def set_output_location(location):
    """Set custom output location (None or empty string = default PNG folder)"""
    if not location or location.strip() == "":
        location = None
    return set_value('app.output_location', location)

def get_levels_black_point():
    """Get the black point for levels adjustment"""
    return get_value('image_processing.levels_adjustment.default.black_point', 20)

def set_levels_black_point(value):
    """Set the black point for levels adjustment"""
    return set_value('image_processing.levels_adjustment.default.black_point', int(value))

def get_levels_mid_point():
    """Get the mid point for levels adjustment"""
    return get_value('image_processing.levels_adjustment.default.mid_point', 70)

def set_levels_mid_point(value):
    """Set the mid point for levels adjustment"""
    return set_value('image_processing.levels_adjustment.default.mid_point', int(value))

def get_levels_white_point():
    """Get the white point for levels adjustment"""
    return get_value('image_processing.levels_adjustment.default.white_point', 200)

def set_levels_white_point(value):
    """Set the white point for levels adjustment"""
    return set_value('image_processing.levels_adjustment.default.white_point', int(value))
