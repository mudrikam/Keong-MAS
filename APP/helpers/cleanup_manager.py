"""
Cleanup Manager module for Keong-MAS application.
Centralized handling of all temporary file cleanup operations.
Ensures adjusted masks are only cleaned up when safe to do so.
"""
import os
import glob
import logging
import threading
import time
from typing import List, Set

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("CleanupManager")

class CleanupManager:
    """
    Centralized manager for handling all cleanup operations.
    Tracks which files are in use and ensures safe cleanup.
    """
    
    def __init__(self):
        self._active_files: Set[str] = set()
        self._pending_cleanup: Set[str] = set()
        self._lock = threading.Lock()
        
    def register_file_in_use(self, file_path: str):
        """
        Register a file as being actively used by a process.
        
        Args:
            file_path (str): Path to the file being used
        """
        with self._lock:
            self._active_files.add(file_path)
            logger.debug(f"Registered file in use: {os.path.basename(file_path)}")
    
    def unregister_file_in_use(self, file_path: str):
        """
        Unregister a file from being actively used.
        
        Args:
            file_path (str): Path to the file no longer being used
        """
        with self._lock:
            if file_path in self._active_files:
                self._active_files.remove(file_path)
                logger.debug(f"Unregistered file from use: {os.path.basename(file_path)}")
    
    def is_file_in_use(self, file_path: str) -> bool:
        """
        Check if a file is currently being used by any process.
        
        Args:
            file_path (str): Path to check
            
        Returns:
            bool: True if file is in use, False otherwise
        """
        with self._lock:
            return file_path in self._active_files
    
    def add_to_pending_cleanup(self, file_path: str):
        """
        Add a file to pending cleanup list.
        
        Args:
            file_path (str): Path to file that should be cleaned up later
        """
        with self._lock:
            self._pending_cleanup.add(file_path)
            logger.debug(f"Added to pending cleanup: {os.path.basename(file_path)}")
    
    def get_save_mask_setting(self) -> bool:
        """
        Get the save_mask setting from config.
        
        Returns:
            bool: True if masks should be saved, False if they should be cleaned up
        """
        try:
            from APP.helpers.config_manager import get_save_mask_enabled
            return get_save_mask_enabled()
        except Exception as e:
            logger.warning(f"Could not get save_mask setting: {e}")
            return False  # Default to cleanup if can't read config
    
    def cleanup_original_temp_files(self, original_transparent_path: str, original_mask_path: str):
        """
        Clean up original temporary files that are no longer needed.
        
        Args:
            original_transparent_path (str): Path to original transparent image
            original_mask_path (str): Path to original mask image
        """
        files_to_clean = [original_transparent_path, original_mask_path]
        
        for file_path in files_to_clean:
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info(f"CLEANUP: Removed original temp file: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.warning(f"Failed to remove original temp file {file_path}: {e}")
    
    def find_related_adjusted_masks(self, image_path: str) -> List[str]:
        """
        Find all adjusted masks related to a given image path.
        Now more precise to avoid cleaning up other files' masks.
        
        Args:
            image_path (str): Path to the image
            
        Returns:
            List[str]: List of paths to related adjusted masks
        """
        adjusted_masks = []
        
        try:
            # Extract base name from image path
            base_dir = os.path.dirname(image_path)
            file_name = os.path.splitext(os.path.basename(image_path))[0]
            
            logger.info(f"CLEANUP: Looking for adjusted masks for: {file_name}")
            
            # Extract timestamp from the current file if it exists
            timestamp_id = None
            import re
            timestamp_match = re.search(r'_(\d{4})$', file_name)
            if timestamp_match:
                timestamp_id = timestamp_match.group(1)
                logger.info(f"CLEANUP: Found timestamp ID: {timestamp_id}")
            
            # Remove our app's suffixes to get base name
            base_name = file_name
            our_suffixes = ['_transparent', '_mask_adjusted', '_mask', '_solid_background']
            for suffix in our_suffixes:
                if suffix in base_name:
                    suffix_pos = base_name.find(suffix)
                    if suffix_pos > 0:
                        base_name = base_name[:suffix_pos]
                        break
            
            # Remove timestamp patterns
            base_name = re.sub(r'_\d{4}$', '', base_name)
            
            logger.info(f"CLEANUP: Extracted base name: {base_name}")
            
            # Search directories
            search_dirs = [base_dir]
            if os.path.basename(base_dir).upper() != 'PNG':
                png_dir = os.path.join(base_dir, 'PNG')
                search_dirs.append(png_dir)
            
            parent_dir = os.path.dirname(base_dir)
            png_dir = os.path.join(parent_dir, 'PNG')
            search_dirs.append(png_dir)
            
            # Find adjusted masks
            for search_dir in search_dirs:
                if not os.path.exists(search_dir):
                    continue
                    
                # If we have a timestamp, look for exact match first
                if timestamp_id:
                    specific_pattern = os.path.join(search_dir, f"{base_name}_mask_adjusted_{timestamp_id}.png")
                    if os.path.exists(specific_pattern):
                        adjusted_masks.append(specific_pattern)
                        logger.info(f"CLEANUP: Found specific adjusted mask: {specific_pattern}")
                else:
                    # Only if no timestamp, look for any related mask
                    adjusted_pattern = os.path.join(search_dir, f"{base_name}_mask_adjusted_*.png")
                    found_masks = glob.glob(adjusted_pattern)
                    
                    logger.info(f"CLEANUP: Searching in {search_dir}")
                    logger.info(f"CLEANUP: Pattern: {adjusted_pattern}")
                    logger.info(f"CLEANUP: Found {len(found_masks)} adjusted masks: {found_masks}")
                    
                    adjusted_masks.extend(found_masks)
            
            # Remove duplicates
            adjusted_masks = list(set(adjusted_masks))
            
        except Exception as e:
            logger.warning(f"Error finding related adjusted masks for {image_path}: {e}")
        
        return adjusted_masks
    
    def cleanup_adjusted_mask_if_safe(self, mask_path: str) -> bool:
        """
        Clean up an adjusted mask if it's safe to do so.
        
        Args:
            mask_path (str): Path to the adjusted mask
            
        Returns:
            bool: True if cleaned up, False if kept or error occurred
        """
        if not mask_path or "_mask_adjusted_" not in mask_path:
            logger.debug(f"Skipping cleanup - not an adjusted mask: {mask_path}")
            return False
        
        if not os.path.exists(mask_path):
            logger.debug(f"Adjusted mask already removed: {mask_path}")
            return True
        
        # Check if file is in use
        if self.is_file_in_use(mask_path):
            logger.info(f"CLEANUP: Mask in use, adding to pending cleanup: {os.path.basename(mask_path)}")
            self.add_to_pending_cleanup(mask_path)
            return False
        
        # Check save_mask setting
        save_mask = self.get_save_mask_setting()
        
        if save_mask:
            logger.info(f"CLEANUP: Keeping adjusted mask: {os.path.basename(mask_path)} (save_mask=True)")
            return False
        
        try:
            os.remove(mask_path)
            logger.info(f"CLEANUP: Removed adjusted mask: {os.path.basename(mask_path)} (save_mask=False)")
            
            # Remove from pending cleanup if it was there
            with self._lock:
                self._pending_cleanup.discard(mask_path)
            
            return True
        except Exception as e:
            logger.warning(f"Failed to cleanup adjusted mask {mask_path}: {e}")
            return False
    
    def process_pending_cleanup(self):
        """
        Process all files in the pending cleanup list.
        Only clean up files that are no longer in use.
        """
        with self._lock:
            pending_copy = self._pending_cleanup.copy()
        
        if not pending_copy:
            return
        
        logger.info(f"CLEANUP: Processing {len(pending_copy)} pending cleanup items")
        
        cleaned_count = 0
        for file_path in pending_copy:
            if not self.is_file_in_use(file_path):
                if self.cleanup_adjusted_mask_if_safe(file_path):
                    cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"CLEANUP: Processed {cleaned_count} pending cleanup items")
    
    def final_cleanup_for_image(self, image_path: str):
        """
        Perform final cleanup for all files related to an image.
        This should only be called at the very end of all processing.
        Now more precise to avoid cleaning up wrong files.
        
        Args:
            image_path (str): Path to the processed image
        """
        logger.info(f"FINAL CLEANUP: Starting for {os.path.basename(image_path)}")
        
        save_mask = self.get_save_mask_setting()
        logger.info(f"FINAL CLEANUP: save_mask setting = {save_mask}")
        
        if save_mask:
            logger.info("FINAL CLEANUP: save_mask=True, keeping all adjusted masks")
            return
        
        # Find and clean up only related adjusted masks (with same timestamp if possible)
        adjusted_masks = self.find_related_adjusted_masks(image_path)
        
        cleaned_count = 0
        for mask_path in adjusted_masks:
            # Unregister from active files first
            self.unregister_file_in_use(mask_path)
            
            if os.path.exists(mask_path):
                try:
                    os.remove(mask_path)
                    logger.info(f"FINAL CLEANUP: Removed {os.path.basename(mask_path)}")
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"FINAL CLEANUP: Failed to remove {mask_path}: {e}")
        
        # Process any remaining pending cleanup
        self.process_pending_cleanup()
        
        if cleaned_count > 0:
            logger.info(f"FINAL CLEANUP: Removed {cleaned_count} adjusted mask(s)")
        else:
            logger.info("FINAL CLEANUP: No adjusted masks found to remove")
    
    def check_remaining_operations(self, image_path: str) -> dict:
        """
        Check which operations are still enabled and might need the adjusted masks.
        
        Args:
            image_path (str): Path to the processed image
            
        Returns:
            dict: Dictionary with operation statuses
        """
        try:
            from APP.helpers.config_manager import (
                get_auto_crop_enabled,
                get_solid_bg_enabled, 
                get_jpg_export_enabled
            )
            
            operations = {
                'crop_enabled': get_auto_crop_enabled(),
                'solid_bg_enabled': get_solid_bg_enabled(),
                'jpg_enabled': get_jpg_export_enabled()
            }
            
            logger.info(f"CLEANUP: Checking operations - Crop: {operations['crop_enabled']}, "
                       f"Solid BG: {operations['solid_bg_enabled']}, JPG: {operations['jpg_enabled']}")
            
            return operations
            
        except Exception as e:
            logger.warning(f"Error checking remaining operations: {e}")
            # If we can't check, assume all operations might be enabled (safer)
            return {
                'crop_enabled': True,
                'solid_bg_enabled': True,
                'jpg_enabled': True
            }
    
    def should_defer_cleanup(self, image_path: str) -> bool:
        """
        Determine if cleanup should be deferred because other operations might need the masks.
        
        Args:
            image_path (str): Path to the processed image
            
        Returns:
            bool: True if cleanup should be deferred, False if safe to cleanup now
        """
        operations = self.check_remaining_operations(image_path)
        
        # Check if any operation that might need masks is still enabled
        needs_masks = (
            operations['crop_enabled'] or 
            operations['solid_bg_enabled'] or 
            operations['jpg_enabled']
        )
        
        if needs_masks:
            logger.info("CLEANUP: Deferring cleanup - other operations might need adjusted masks")
            return True
        else:
            logger.info("CLEANUP: No operations enabled that need masks - safe to cleanup")
            return False
    
    def intelligent_cleanup_after_image_utils(self, image_path: str):
        """
        Intelligent cleanup after image_utils processing.
        Only cleans up if no other operations are enabled that might need the masks.
        
        Args:
            image_path (str): Path to the processed image
        """
        logger.info(f"INTELLIGENT CLEANUP: Checking if cleanup needed after image_utils for {os.path.basename(image_path)}")
        
        save_mask = self.get_save_mask_setting()
        
        if save_mask:
            logger.info("INTELLIGENT CLEANUP: save_mask=True, keeping all adjusted masks")
            return
        
        # Check if other operations are enabled
        if self.should_defer_cleanup(image_path):
            logger.info("INTELLIGENT CLEANUP: Deferring cleanup - other operations are enabled")
            return
        
        # If no other operations are enabled, safe to cleanup now
        logger.info("INTELLIGENT CLEANUP: No other operations enabled, proceeding with cleanup")
        self.final_cleanup_for_image(image_path)
    
    def intelligent_cleanup_after_all_operations(self, image_path: str, completed_operations: list = None):
        """
        Intelligent cleanup after ALL operations are complete.
        This should be called at the very end when all processing is done.
        
        Args:
            image_path (str): Path to the processed image
            completed_operations (list): List of operations that were completed
        """
        logger.info(f"INTELLIGENT CLEANUP: Final cleanup after all operations for {os.path.basename(image_path)}")
        
        if completed_operations:
            logger.info(f"INTELLIGENT CLEANUP: Completed operations: {', '.join(completed_operations)}")
        
        save_mask = self.get_save_mask_setting()
        
        if save_mask:
            logger.info("INTELLIGENT CLEANUP: save_mask=True, keeping all adjusted masks")
            return
        
        # At this point, all operations should be complete, so cleanup is safe
        logger.info("INTELLIGENT CLEANUP: All operations complete, proceeding with final cleanup")
        self.final_cleanup_for_image(image_path)

# Global instance
_cleanup_manager = CleanupManager()

# Public API functions
def register_file_in_use(file_path: str):
    """Register a file as being actively used."""
    _cleanup_manager.register_file_in_use(file_path)

def unregister_file_in_use(file_path: str):
    """Unregister a file from being actively used."""
    _cleanup_manager.unregister_file_in_use(file_path)

def cleanup_original_temp_files(original_transparent_path: str, original_mask_path: str):
    """Clean up original temporary files."""
    _cleanup_manager.cleanup_original_temp_files(original_transparent_path, original_mask_path)

def cleanup_adjusted_mask_if_safe(mask_path: str) -> bool:
    """Clean up an adjusted mask if it's safe to do so."""
    return _cleanup_manager.cleanup_adjusted_mask_if_safe(mask_path)

def add_to_pending_cleanup(file_path: str):
    """Add a file to pending cleanup list."""
    _cleanup_manager.add_to_pending_cleanup(file_path)

def final_cleanup_for_image(image_path: str):
    """Perform final cleanup for all files related to an image."""
    _cleanup_manager.final_cleanup_for_image(image_path)

def process_pending_cleanup():
    """Process all files in the pending cleanup list."""
    _cleanup_manager.process_pending_cleanup()

# Add new public API functions
def intelligent_cleanup_after_image_utils(image_path: str):
    """Intelligent cleanup after image_utils processing."""
    _cleanup_manager.intelligent_cleanup_after_image_utils(image_path)

def intelligent_cleanup_after_all_operations(image_path: str, completed_operations: list = None):
    """Intelligent cleanup after ALL operations are complete."""
    _cleanup_manager.intelligent_cleanup_after_all_operations(image_path, completed_operations)

def check_remaining_operations(image_path: str) -> dict:
    """Check which operations are still enabled."""
    return _cleanup_manager.check_remaining_operations(image_path)
