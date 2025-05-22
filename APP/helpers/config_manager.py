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
        }
    },
    "image_cropping": {
        "enabled": False,
        "detection_threshold": 5,  # Value 0-255 determining what is considered transparent
        "margin": 10             # Margin in pixels to preserve around content
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

def get_crop_margin():
    """Get the margin in pixels to preserve around content when cropping"""
    return get_value('image_cropping.margin', 10)

def set_crop_margin(margin):
    """Set the margin in pixels to preserve around content when cropping"""
    return set_value('image_cropping.margin', int(margin))

# Backward compatibility - now returns the margin value
def get_crop_threshold():
    """Get the threshold value for cropping (for backward compatibility)"""
    return get_crop_margin()
