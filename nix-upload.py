import os
import random
import time
import json
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import traceback
import re
import logging
import tempfile
import atexit
import shutil
from PIL import Image, ImageDraw, ImageFont
from PIL.ExifTags import TAGS, GPSTAGS

from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# Initialize logger with a basic configuration
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
# Set an initial level - this will be overridden by config if available
logger.setLevel(logging.INFO)

# Global variable to store log file path
log_file_path = None

# Global variable to store debug directory
debug_directory = 'debug'

def setup_file_logging(debug_dir='debug'):
    """Set up file logging with a timestamped log file."""
    global log_file_path, debug_directory
    debug_directory = debug_dir
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(debug_directory, exist_ok=True)
    log_file_path = os.path.join(debug_directory, f"{timestamp}_nix_upload.log")
    
    file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.info(f"Logging to file: {log_file_path}")

# Global variable to keep track of temporary directories
temp_directories = []

def cleanup_temp_files():
    """Clean up all temporary directories and files created by the program."""
    global temp_directories
    for temp_dir in temp_directories:
        try:
            if os.path.exists(temp_dir):
                logger.debug(f"Cleaning up temporary directory: {temp_dir}")
                shutil.rmtree(temp_dir)
        except Exception as e:
            logger.error(f"Failed to clean up temporary directory {temp_dir}: {str(e)}")
    
    # Clear the list after cleanup
    # temp_directories = []

# Register the cleanup function to be called when the program exits
atexit.register(cleanup_temp_files)


def save_debug_snapshot(driver, label):
    """Save screenshot and page source for debugging."""
    global debug_directory
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_label = label.replace(" ", "_").lower()
    os.makedirs(debug_directory, exist_ok=True)
    
    screenshot_path = os.path.join(debug_directory, f"{timestamp}_{safe_label}.png")
    html_path = os.path.join(debug_directory, f"{timestamp}_{safe_label}.html")
    
    try:
        driver.save_screenshot(screenshot_path)
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        logger.debug(f"Saved debug snapshot: {screenshot_path}, {html_path}")
    except Exception as e:
        logger.error(f"Failed to save debug snapshot for '{label}': {e}")


def load_config(config_file='config.json'):
    """Load configuration from JSON file with default values."""
    
    DEFAULT_CONFIG = {
        'base_url': 'https://app.nixplay.com',
        'playlist_name': 'nix-upload',
        'delete_my_uploads': True,
        'max_photos': 500,
        'max_file_size_mb': 3,
        'batch_size': 100,
        'image_width': 1280,
        'image_height': 800,
        'log_level': 'INFO',
        'headless': True,
        'caption': True,
        'caption_position': 'bottom',
        'date_format': '%Y-%m-%d %H:%M',
        'font_size': 50,
        'font_path': None,
        'debug_directory': 'debug'
    }
    
    REQUIRED_KEYS = ['username', 'password', 'photos_directory']

    try:
        # Get absolute path and filename for logging
        config_path = os.path.abspath(config_file)
        config_name = os.path.basename(config_path)
        logger.info(f"Loading config file: {config_name} (path: {config_path})")
        
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Check for required keys
        for key in REQUIRED_KEYS:
            if key not in config:
                raise KeyError(f"Missing required key '{key}' in config file.")

        # Merge defaults with loaded config
        merged_config = DEFAULT_CONFIG.copy()
        merged_config.update(config)

        # Apply transformations
        if 'base_url' in merged_config:
            merged_config['base_url'] = merged_config['base_url'].rstrip('/')

        # Validate headless is boolean
        if not isinstance(merged_config['headless'], bool):
            raise ValueError(f"The 'headless' parameter must be a boolean (True or False).")

        # Configure logger
        log_level = merged_config['log_level'].upper()
        numeric_level = getattr(logging, log_level, None)
        if not isinstance(numeric_level, int):
            logger.warning(f"Invalid log level: {log_level}. Defaulting to INFO.")
            numeric_level = logging.INFO
        logger.setLevel(numeric_level)
        logger.info(f"Log level set to {log_level}")

        return merged_config

    except FileNotFoundError:
        logger.error(f"Config file '{config_file}' not found.")
        exit(1)
    except json.JSONDecodeError:
        logger.error(f"Failure parsing config file '{config_file}'. Please ensure it's valid JSON.")
        exit(1)
    except KeyError as e:
        logger.error(f"Config file error: {str(e)}")
        exit(1)
    except ValueError as e:
        logger.error(f"Config file error: {str(e)}")
        exit(1)
    except Exception as e:
        logger.error(f"Failure loading config: {str(e)}")
        exit(1)
        

logger = logging.getLogger(__name__)

def display_progress_bar(prefix, start_time, timeout, current, total, suffix="", bar_width=50):
    """Displays a dot-based progress bar in the console."""
    
   # Make sure current doesn't go negative (shouldn't happen but just in case)
    current = max(0, current)
    progress_ratio = min(current / total, 1.0)
    dots = int(progress_ratio * bar_width)
    spaces = bar_width - dots
    progress_bar = "." * dots + " " * spaces
    if(timeout <= 0):
        print(f"\r{prefix}: [{progress_bar}] ({current}/{total}) {round(time.time() - start_time)}s {suffix}", end="", flush=True)
    else:
        print(f"\r{prefix}: [{progress_bar}] ({current}/{total}) {round(time.time() - start_time)}s/{timeout}s {suffix}", end="", flush=True)
    
def end_progress_bar():
    print()
    
def get_image_files(directory, max_file_size_mb, max_photos, target_width, target_height, date_format="%Y-%m-%d %H:%M", caption_position="bottom", font_size=40, font_path=None, caption=True):
    """Recursively get all image files from a directory, skipping folders with a .nonixplay file."""
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp']
    image_files = []
    try:
        for root, dirs, files in os.walk(directory):
            # Skip this directory if it contains a .nonixplay file
            if '.nonixplay' in files:
                logger.debug(f"Skipping directory: {root} (contains .nonixplay)")
                dirs[:] = []  # Prevent descending into subdirectories
                continue
            for file in files:
                if any(file.lower().endswith(ext) for ext in valid_extensions):
                    image_files.append(os.path.join(root, file))
        
        # Randomly select max_photos number of photos (from all images, not filtering by size first)
        if len(image_files) > max_photos:
            selected_images = random.sample(image_files, max_photos)
            logger.info(f"Randomly selected {len(selected_images)} photos for upload.")
        else:
            selected_images = image_files
            logger.info(f"Selected all {len(selected_images)} photos for upload (fewer than max_photos).")
        
        # Create temporary directory for processed images
        temp_dir = tempfile.mkdtemp(prefix="nix_upload_temp_")
        # Add to the global list for cleanup
        global temp_directories
        temp_directories.append(temp_dir)
        logger.info(f"Resizing files in: {temp_dir}")
        
        # Process selected images and check size after conversion
        max_file_size = max_file_size_mb * 1024 * 1024
        final_images = []
        start_time = time.time()
        for i, img_path in enumerate(selected_images):
            processed_path = image_resize_and_add_caption(
                img_path, 
                temp_dir, 
                target_width, 
                target_height, 
                max_file_size,
                date_format=date_format,
                caption_position=caption_position,
                font_size=font_size,
                font_path=font_path,
                caption=caption
            )
            if processed_path:
                final_images.append(processed_path)
            display_progress_bar("Resizing", start_time, 0, i+1, max_photos)
        end_progress_bar()

        logger.debug(f"Resized {len(final_images)} of {len(selected_images)} selected images.")
        return final_images
        
    except FileNotFoundError:
        logger.error(f"Directory '{directory}' not found.")
        exit(1)
    except Exception as e:
        logger.error(f"Error getting image files: {str(e)}")
        exit(1)

def _convert_to_degrees(value):
    """Convert decimal coordinates into degrees, minutes and seconds."""
    d = float(value[0])
    m = float(value[1])
    s = float(value[2])
    return d + (m / 60.0) + (s / 3600.0)

def _get_gps_coordinates(img):
    """Extract GPS coordinates from image EXIF data."""
    try:
        exif = img._getexif()
        if not exif:
            return None

        # GPS tags
        gps_lat = None
        gps_lat_ref = None
        gps_lon = None
        gps_lon_ref = None

        for tag_id in exif:
            tag = TAGS.get(tag_id, tag_id)
            data = exif.get(tag_id)
            
            if tag == 'GPSInfo':
                for key in data.keys():
                    sub_tag = GPSTAGS.get(key, key)
                    if sub_tag == 'GPSLatitude':
                        gps_lat = data[key]
                    elif sub_tag == 'GPSLatitudeRef':
                        gps_lat_ref = data[key]
                    elif sub_tag == 'GPSLongitude':
                        gps_lon = data[key]
                    elif sub_tag == 'GPSLongitudeRef':
                        gps_lon_ref = data[key]

        if gps_lat and gps_lon:
            lat = _convert_to_degrees(gps_lat)
            lon = _convert_to_degrees(gps_lon)
            
            if gps_lat_ref != 'N':
                lat = -lat
            if gps_lon_ref != 'E':
                lon = -lon
                
            return (lat, lon)
    except Exception as e:
        logger.debug(f"Failed to extract GPS coordinates: {str(e)}")
    return None

def _get_location_name(coordinates):
    """Convert GPS coordinates to location name using reverse geocoding."""
    try:
        from geopy.geocoders import Nominatim
        from geopy.exc import GeocoderTimedOut, GeocoderUnavailable
        from requests.exceptions import RequestException
        
        # Initialize geocoder with a longer timeout and custom user agent
        geolocator = Nominatim(
            user_agent="nix-upload/1.0",
            timeout=10  # Increase timeout to 10 seconds
        )
        
        try:
            location = geolocator.reverse(coordinates, language='en')
            
            if location and location.raw.get('address'):
                # Try to get city name, fall back to other location components
                address = location.raw['address']
                city = address.get('city') or address.get('town') or address.get('village')
                if city:
                    return city
                return location.address.split(',')[0]  # Return first part of address if no city found
        except GeocoderTimedOut as e:
            logger.warning(f"Geocoding timed out: {str(e)}")
            # Fallback to coordinates if geocoding fails
            lat, lon = coordinates
            return f"{lat:.4f}, {lon:.4f}"
        except GeocoderUnavailable as e:
            logger.warning(f"Geocoding service unavailable: {str(e)}")
            # Fallback to coordinates if geocoding fails
            lat, lon = coordinates
            return f"{lat:.4f}, {lon:.4f}"
        except RequestException as e:
            logger.warning(f"Network request failed: {str(e)}")
            # Fallback to coordinates if geocoding fails
            lat, lon = coordinates
            return f"{lat:.4f}, {lon:.4f}"
            
    except Exception as e:
        logger.warning(f"Failed to get location name: {str(e)}")
        # Fallback to coordinates if any other error occurs
        lat, lon = coordinates
        return f"{lat:.4f}, {lon:.4f}"
    
    # Final fallback if all else fails
    return None

def image_resize_and_add_caption(image_path, temp_dir, target_width, target_height, max_file_size, date_format="%Y-%m-%d %H:%M", caption_position="bottom", font_size=40, font_path=None, caption=True):
    """
    Resize image to fit the target dimensions and ensure it's under max_file_size.
    Adds text overlay with date and location (from GPS data) if caption is True.
    Returns path to resized image or None if processing failed or file is too large.
    """
    try:
        with Image.open(image_path) as img:
            # Calculate dimensions while maintaining aspect ratio
            img_width, img_height = img.size
            aspect_ratio = img_width / img_height
            
            if img_width / target_width > img_height / target_height:
                # Width is the limiting factor
                new_width = target_width
                new_height = int(new_width / aspect_ratio)
            else:
                # Height is the limiting factor
                new_height = target_height
                new_width = int(new_height * aspect_ratio)
            
            # Resize image
            resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to RGB if necessary (for text overlay)
            if resized_img.mode != 'RGB':
                resized_img = resized_img.convert('RGB')
            
            # Only add text overlay if caption is True
            if caption:
                # Calculate text color based on image background
                # Sample the background color from the bottom of the image
                sample_height = int(new_height * 0.1)  # Sample 10% from bottom
                sample_region = resized_img.crop((0, new_height - sample_height, new_width, new_height))
                avg_color = tuple(map(int, sample_region.resize((1, 1)).getpixel((0, 0))))
                
                # Calculate luminance to determine text color
                luminance = (0.299 * avg_color[0] + 0.587 * avg_color[1] + 0.114 * avg_color[2]) / 255
                text_color = (0, 0, 0) if luminance > 0.5 else (255, 255, 255)  # Black or white text
                
                # Create a copy of the image for drawing
                img_with_text = resized_img.copy()
                
                # Load font
                if font_path and os.path.exists(font_path):
                    font = ImageFont.truetype(font_path, font_size)
                else:
                    # Use default system font
                    try:
                        font = ImageFont.truetype("arial.ttf", font_size)
                    except:
                        font = ImageFont.load_default()
                
                draw = ImageDraw.Draw(img_with_text)
                
                # Get image creation date from EXIF data if available
                try:
                    exif = img._getexif()
                    if exif and 36867 in exif:  # 36867 is DateTimeOriginal
                        date_str = exif[36867]
                        date_obj = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
                    else:
                        # Use file modification time as fallback
                        date_obj = datetime.fromtimestamp(os.path.getmtime(image_path))
                except:
                    # Use file modification time as fallback
                    date_obj = datetime.fromtimestamp(os.path.getmtime(image_path))
                
                # Format date string
                date_text = date_obj.strftime(date_format)
                
                # Get location from GPS coordinates
                location_text = None
                coordinates = _get_gps_coordinates(img)
                if coordinates:
                    location_text = _get_location_name(coordinates)
                
                # Prepare text lines
                text_lines = [date_text]
                if location_text:
                    text_lines.append(location_text)
                
                # Calculate text positions
                caption_y_offset = 100
                caption_x_offset = 100
                if caption_position == "bottom":
                    y_position = new_height - (len(text_lines) * font_size * 1.2) - caption_y_offset  
                else:  # top
                    y_position = caption_y_offset  
                
                # Draw text with outline for better visibility
                outline_color = (0, 0, 0) if text_color == (255, 255, 255) else (255, 255, 255)
                outline_width = 2
                
                for i, line in enumerate(text_lines):
                    # Draw outline
                    for dx in range(-outline_width, outline_width + 1):
                        for dy in range(-outline_width, outline_width + 1):
                            draw.text((caption_x_offset + dx, y_position + (i * font_size * 1.2) + dy), line, font=font, fill=outline_color)
                    # Draw main text
                    draw.text((caption_x_offset, y_position + (i * font_size * 1.2)), line, font=font, fill=text_color)
                
                resized_img = img_with_text
            
            # Create output path in temp directory
            img_filename = os.path.basename(image_path)
            output_path = os.path.join(temp_dir, img_filename)
            
            # Save with 80% quality for JPG/JPEG
            if img_filename.lower().endswith(('.jpg', '.jpeg')):
                resized_img.save(output_path, quality=80)
            else:
                resized_img.save(output_path)
            
            # Check if the processed file is still too large
            if os.path.getsize(output_path) > max_file_size:
                logger.debug(f"Skipping {img_filename}: too large after resizing ({os.path.getsize(output_path)/1024/1024:.2f}MB)")
                os.remove(output_path)  # Clean up the temporary file
                return None
            
            return output_path
    
    except Exception as e:
        logger.warning(f"Error processing image {image_path}: {str(e)}")
        return None

def setup_webdriver(headless):
    """Set up and configure Chrome WebDriver."""
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        options.add_argument("--ignore-certificate-errors")
        options.page_load_strategy = 'normal'
        
        options.headless = headless
        if headless == True:
            options.add_argument("--headless")
        
        options.add_argument("--log-level=1") # cap the loglevel at INFO
        
        # gemini
        options.add_argument("--silent")
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(60)
        return driver
    except Exception as e:
        logger.error(f"Failed setting up WebDriver: {str(e)}")
        exit(1)


def login_to_nixplay(driver, base_url, username, password):
    """Log in to Nixplay account."""
    try:
        logger.debug("Logging in to Nixplay...")
        login_url = f"{base_url}/login"
        driver.get(login_url)
        save_debug_snapshot(driver, "login_page_loaded")
        
        wait = WebDriverWait(driver, 40)
        logger.debug("Waiting for email field...")
        email_field = wait.until(EC.presence_of_element_located((By.ID, "login_username")))
        logger.debug("Found email field.")
        
        logger.debug("Waiting for password field...")
        password_field = wait.until(EC.presence_of_element_located((By.ID, "login_password")))
        logger.debug("Found password field.")
        
        email_field.send_keys(username)
        password_field.send_keys(password)
        
        logger.debug("Looking for login button...")
        login_button = wait.until(EC.element_to_be_clickable((By.ID, "nixplay_login_btn")))
        logger.debug("Clicking login button...")
        login_button.click()
        
        # Check for invalid credentials error before waiting for URL change
        try:
            # Short timeout for checking error message
            error_wait = WebDriverWait(driver, 5)
            error_message = error_wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".login-error-container ul.error li"))
            )
            
            if "Please use your username and password" in error_message.text:
                logger.error("Login failed: Invalid credentials: Please use your username and password")
                save_debug_snapshot(driver, "login_failed_invalid_credentials")
                return False
        except TimeoutException:
            # No error message found, continue with login flow
            pass
        
        # Wait until the login redirects (e.g., away from /login)
        wait.until(EC.url_changes(login_url))
        
        logger.info("Successfully logged in to nixplay.")
        save_debug_snapshot(driver, "login_successful")
        return True
    except TimeoutException:
        logger.error("Timeout while trying to log in.")
        save_debug_snapshot(driver, "login_failed_timeout")
        return False
    except Exception as e:
        logger.error(f"Failed to login: {str(e)}")
        save_debug_snapshot(driver, "login_failed_exception")
        return False

def find_playlist(driver, base_url, playlist_name):
    """Find and select the specified playlist by name, then index."""
    try:
        logger.debug(f"Finding playlist: {playlist_name}...")
        playlists_url = f"{base_url}/#/playlists"
        driver.get(playlists_url)

        wait = WebDriverWait(driver, 30)

        # Add a wait for the modal background to disappear
        logger.debug("Waiting for any modal background to disappear...")
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".nix-modal-bg")))
        logger.debug("Modal background is gone.")

        # Find the playlist's name element.
        playlist_name_element = wait.until(
            EC.presence_of_element_located((By.XPATH, f'//span[@class="name" and @title="{playlist_name}"]'))
        )

        # Find the parent playlist container and extract the index from the ID.
        playlist_container = playlist_name_element.find_element(By.XPATH, "./ancestor::div[contains(@id, 'playlist-')]")
        playlist_id = playlist_container.get_attribute("id")
        playlist_index = int(re.search(r'\d+', playlist_id).group()) #extract the digits

        logger.info(f"Found playlist '{playlist_name}' with index: {playlist_index}")

        # Find the playlist's clickable element using the index.
        playlist_element = wait.until(
            EC.element_to_be_clickable((By.XPATH, f'//div[@id="playlist-{playlist_index}"]//div[@class="playlist-draggable-wrapper"]'))
        )

        # This often bypasses ElementClickInterceptedException when standard .click() fails due to dynamic overlays.
        driver.execute_script("arguments[0].click();", playlist_element)
        logger.debug("Clicked playlist element using JavaScript.")

        wait.until(EC.url_contains("/playlist/"))
        save_debug_snapshot(driver, f"playlist_selected_{playlist_name}")
        return True

    except Exception as e:
        logger.error(f"Could not find playlist: {repr(e)}")
        traceback.print_exc()
        save_debug_snapshot(driver, "find_playlist_error")
        return False

def delete_my_uploads(driver, base_url, timeout=30):
    """
    Delete the 'My Uploads' album from the albums page.
    
    Args:
        driver: Selenium WebDriver instance
        base_url: Base URL of the Nixplay website
        timeout: Maximum time to wait for elements (seconds)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info("Navigating to albums page to delete 'My Uploads'...")
        albums_url = f"{base_url}/#/albums/nixplay"
        driver.get(albums_url)
        save_debug_snapshot(driver, "albums_page_loaded")
        
        wait = WebDriverWait(driver, timeout)
        
        # Wait for the page to load
        logger.debug("Waiting for albums page to load...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.album-info")))
        
        # Find the "My Uploads" album by looking for the name span
        logger.debug("Looking for 'My Uploads' album...")
        my_uploads_name = wait.until(
            EC.presence_of_element_located((By.XPATH, '//span[@class="name" and @title="My Uploads"]'))
        )
        
        # Navigate up to find the album container
        album_container = my_uploads_name.find_element(By.XPATH, './ancestor::div[contains(@class, "album")]')
        
        # Find the trash icon within this container
        logger.debug("Found 'My Uploads'. Looking for delete button...")
        delete_button = album_container.find_element(By.XPATH, './/div[contains(@class, "album-delete fa fa-trash-o")]')
        save_debug_snapshot(driver, "found_my_uploads_delete_button")
        
        # Click the delete button
        logger.debug("'My Uploads'.Clicking delete button...")
        delete_button.click()
        time.sleep(5) # arbitrary delay before clicking "Yes"
        save_debug_snapshot(driver, "after_my_uploads_delete_button_clicked")
        
        # Wait for confirmation dialog
        logger.debug("Waiting for 'My Uploads'Delete legacy album' confirmation dialog...")
        wait.until(EC.presence_of_element_located((By.XPATH, '//span[@class="nix-modal-title-text" and text()="Delete legacy album"]')))
        save_debug_snapshot(driver, "found_delete_legacy_album_confirmation_dialog")
        
        # Find and click the "Yes" button
        logger.debug("Looking for 'Yes' button...")
        yes_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//div[@class="nix-modal-buttons"]//button[text()="Yes"]')))
        save_debug_snapshot(driver, "delete_my_uploads_legacy_album_confirmation_dialog_yes_button")
        logger.debug("Clicking 'Yes' button...")
        # Use JavaScript click to ensure AngularJS ng-click handler is triggered
        driver.execute_script("arguments[0].click();", yes_button)
        
        # Wait for the dialog to disappear - wait for modal background to disappear (more reliable than title text)
        logger.debug("Waiting for 'My Uploads'Delete legacy album' dialog to close...")
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".nix-modal-bg")))
        
        logger.info("Successfully deleted 'My Uploads' album")
        save_debug_snapshot(driver, "after_delete_my_uploads_album")
        return True
        
    except TimeoutException as e:
        logger.error(f"Timeout while trying to delete 'My Uploads' album: {str(e)}")
        save_debug_snapshot(driver, "delete_uploads_timeout")
        return False
    except Exception as e:
        logger.error(f"Failed to delete 'My Uploads' album: {str(e)}")
        traceback.print_exc()
        save_debug_snapshot(driver, "delete_uploads_error")
        return False



def delete_all_from_playlist(driver, timeout=500):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    
    try:
        logger.debug("Switching to main document...")
        driver.switch_to.default_content()
        wait = WebDriverWait(driver, timeout)

        # Wait for any modal background to disappear before proceeding
        logger.debug("Waiting for any modal background to disappear...")
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".nix-modal-bg")))
        logger.debug("Modal background is gone.")

        # Step 2: Open Actions dropdown
        logger.debug("Locating Actions button container...")
        # Find the Actions container div (the one with dropdown-hover class)
        actions_container_div = wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'nix-modal-playlist-actions') and contains(@class, 'dropdown-hover')]"))
        )
        logger.debug("Found Actions container div.")
        
        # Find the button inside the container
        actions_button = actions_container_div.find_element(By.XPATH, ".//button[contains(@class, 'dropdown-toggle') and contains(@class, 'btn-gray')]")
        logger.debug("Found Actions button.")
        
        # Hover over the container div to trigger the dropdown (since it's dropdown-hover)
        from selenium.webdriver.common.action_chains import ActionChains
        action_chains = ActionChains(driver)
        action_chains.move_to_element(actions_container_div).perform()
        logger.debug("Hovered over Actions container.")
        
        # Also click the button as a backup
        driver.execute_script("arguments[0].click();", actions_button)
        logger.debug("Clicked Actions button.")
        save_debug_snapshot(driver, "after_actions_clicked")
        
        # Wait a moment for dropdown to appear
        time.sleep(2)
        
        # Wait for the specific dropdown menu (the one with action-delete-all links)
        logger.debug("Waiting for dropdown menu to appear...")
        wait.until(EC.visibility_of_element_located((By.XPATH, "//div[contains(@class, 'nix-modal-playlist-actions')]//ul[contains(@class, 'dropdown-menu')]//a[contains(@class, 'action-delete-all')]")))
        logger.debug("Dropdown menu is visible.")

        # Step 3: Click "Permanent delete all photos"
        logger.debug("Looking for 'Permanent delete all photos' link...")
        delete_all_perm = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@ng-click, 'deleteAllSlides') and contains(@ng-click, 'delete')]"))
        )
        logger.debug("Found 'Permanent delete all photos' link, clicking...")
        driver.execute_script("arguments[0].click();", delete_all_perm)
        logger.debug("Clicked 'Permanent delete all photos'.")
        save_debug_snapshot(driver, "after_delete_all_clicked")

        # Step 4: Wait for modal and read title
        logger.debug("Waiting for modal to appear...")
        modal_title_elem = wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".nix-modal-title-text"))
        )
        modal_text = modal_title_elem.text.strip()
        logger.debug(f"Modal title detected: '{modal_text}'")
        save_debug_snapshot(driver, "modal_detected")

        if modal_text == "No Photo in Playlist" or modal_text == "No Photo in album":
            logger.debug(f"'No Photo' modal detected: '{modal_text}'.")
            # Try to find OK button first, then Yes button as fallback
            try:
                ok_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='OK']")))
                save_debug_snapshot(driver, "before_clicking_ok")
                driver.execute_script("arguments[0].click();", ok_button)
                logger.info("Clicked 'OK' on No Photo modal.")
            except TimeoutException:
                # Fallback to Yes button
                yes_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[normalize-space()='Yes']")))
                save_debug_snapshot(driver, "before_clicking_yes")
                driver.execute_script("arguments[0].click();", yes_button)
                logger.info("Clicked 'Yes' on No Photo modal.")
            return True
        else:
            logger.debug(f"Confirmation modal detected: '{modal_text}'. Proceeding to click 'Yes'.")
            save_debug_snapshot(driver, "before_clicking_yes")
            # Look for Yes button in the modal buttons container
            yes_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@class='nix-modal-buttons']//button[normalize-space()='Yes']")))
            driver.execute_script("arguments[0].click();", yes_button)
            logger.info("Clicked 'Yes' to confirm deletion.")
            
            # Wait for modal to close
            try:
                wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".nix-modal-bg")))
                logger.debug("Modal closed successfully.")
            except TimeoutException:
                logger.warning("Modal may not have closed, but continuing...")
            
            return True

    except TimeoutException as e:
        logger.error(f"delete_all_from_playlist() TimeoutException: {str(e)}")
        save_debug_snapshot(driver, "timeout_exception")
        return False

    except Exception as e:
        logger.error(f"delete_all_from_playlist() Exception: {str(e)}")
        save_debug_snapshot(driver, "unexpected_exception")
        return False

      

       

class invisibility_of_any_element:
    def __init__(self, locators):
        self.locators = locators

    def __call__(self, driver):
        return all(EC.invisibility_of_element_located(locator)(driver) for locator in self.locators)


from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException

def upload_batch(driver, batch, batch_number, batch_count, batch_end_count, logfile):
    logger.debug(f"batch_number={batch_number}, batch_end_count={batch_end_count}")
    
    """Upload a single batch of photos and monitor progress."""
    wait = WebDriverWait(driver, 120)
    short_wait = WebDriverWait(driver, 5)  # Shorter wait for checking error modals
    
    # Display all file names in this batch
    logger.debug(f"Files in this batch:")
    for idx, file_path in enumerate(batch):
        logger.debug(f"  {idx+1}. {os.path.basename(file_path)}")
    
    # Click "Add photos"
    try:
        wait.until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".nix-upload-modal-bg")))
        add_photos_button = wait.until(EC.element_to_be_clickable((By.ID, "add-photos")))
        driver.execute_script("arguments[0].scrollIntoView(true);", add_photos_button)
        driver.execute_script("arguments[0].click();", add_photos_button)
    except Exception as e:
        logger.warning(f"Failed to click on 'Add photos': {e}, continuing")
        save_debug_snapshot(driver, f"add_photos_error_batch_{batch_number}")
        return False
        
    # Click "From my computer"
    try:
        from_computer = wait.until(EC.presence_of_element_located((By.XPATH, "//span[text()='From my computer']")))
        driver.execute_script("arguments[0].click();", from_computer)
    except Exception as e:
        logger.warning(f"Failed to click on 'From my computer': {e}, continuing")
        save_debug_snapshot(driver, f"from_my_computer_error_batch_{batch_number}")
        return False
        
    # Upload files
    try:
        file_input = wait.until(EC.presence_of_element_located((By.ID, "upload")))
        # Debug print: List of files to be sent
        files_to_send = "\n".join([os.path.abspath(f) for f in batch])
        logger.debug("Debug: Files being sent to input field:\n" + files_to_send)
        file_input.send_keys(files_to_send)
        try:
            logfile.write(files_to_send)
        except Exception as e:
            logger.warning(f"Error writing log of files: {e}, continuing")
            
    except Exception as e:
        logger.warning(f"Error sending files to input: {e}, continuing")
        save_debug_snapshot(driver, f"upload_input_error_batch_{batch_number}")
        return False
        
    # Monitor upload progress
    logger.debug("Waiting for upload progress indicator...")
    upload_text_xpath = "//span[contains(text(), 'files completed')]"
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, upload_text_xpath)))
    except TimeoutException:
        logger.warning("⚠️ Upload progress text not found. Continuing")
        save_debug_snapshot(driver, f"upload_progress_not_found_batch_{batch_number}")
        return False
    
    logger.debug("Monitoring batch upload progress...")
    last_progress = 0
    final_progress = 0  # Track the final progress count
    last_progress_change_time = time.time()
    stall_timeout = min(200, len(batch))
    max_upload_time = max(300, 2 * len(batch)*batch_number)
    logger.debug(f"batch_len={len(batch)}, batch_number={batch_number}, batch_count={batch_count} batch_end_count={batch_end_count} max_upload_time={max_upload_time}")
    start_time = time.time()

    while True:
        # Check for server error modal
        try:
            error_modal = short_wait.until(EC.presence_of_element_located(
                (By.XPATH, "//nix-modal//span[contains(@class, 'nix-modal-title-text') and text()='Failed Upload']")
            ))
            
            if error_modal:
                logger.warning("Server error modal detected. Attempting to click OK button")
                save_debug_snapshot(driver, f"server_error_modal_batch_{batch_number}")
                
                try:
                    # Find and click the OK button in the error modal
                    ok_button = short_wait.until(EC.element_to_be_clickable(
                        (By.XPATH, "//nix-modal//button[text()='Ok']")
                    ))
                    driver.execute_script("arguments[0].click();", ok_button)
                    logger.info("Successfully clicked OK on server error modal")
                    
                    # Optional: Log the rejected files
                    try:
                        rejected_files = driver.find_elements(By.XPATH, "//nix-modal//div[contains(text(), 'Server error')]")
                        if rejected_files:
                            logger.warning(f"Server rejected {len(rejected_files)} files:")
                            for file_elem in rejected_files:
                                logger.warning(f"  - {file_elem.text}")
                    except Exception as e:
                        logger.warning(f"Failed to log rejected files: {e}")
                    
                    # Wait briefly after dismissing the modal
                    time.sleep(2)
                except Exception as e:
                    logger.warning(f"Failed to dismiss server error modal: {e}")
                    save_debug_snapshot(driver, f"error_modal_dismiss_failed_{batch_number}")
        except TimeoutException:
            # No error modal found, continue with upload monitoring
            pass
        except Exception as e:
            logger.warning(f"Error checking for server error modal: {e}")
            
        # Check for absolute timeout
        if time.time() - start_time > max_upload_time:
            save_debug_snapshot(driver, f"maximum_upload_time_{batch_number}")
            # Try to get final progress before breaking
            try:
                upload_text_elem = driver.find_element(By.XPATH, upload_text_xpath)
                text = upload_text_elem.text.strip()
                if " of " in text:
                    parts = text.split(" of ")
                    final_progress = int(parts[0])
            except:
                pass  # If we can't get it, use the last known value
            logger.info(f"\nMaximum upload time ({max_upload_time}s) reached. Final progress: {final_progress}/{batch_end_count}")
            break
            
        time.sleep(2)
        try:
            upload_text_elem = driver.find_element(By.XPATH, upload_text_xpath)
            text = upload_text_elem.text.strip()
            
            # Try to parse progress
            current_progress = 0
            try:
                if " of " in text:
                    parts = text.split(" of ")
                    current_progress = int(parts[0])
                    # Get the total from the text which may be different from our batch size
                    website_total = int(parts[1].split(" ")[0])
            except ValueError:
                logger.warning(f"Progress bar text '{text}' could not be parsed. Continuing")
                pass  # Progress couldn't be parsed
                
            if current_progress > 0:
                # Update final_progress to track the latest count
                final_progress = current_progress
                
                # Calculate the progress relative to this batch
                total_for_batch = len(batch)
                    
                batch_start_count = (batch_number-1)*total_for_batch+1
                batch_progress = current_progress - batch_start_count + 1

                display_progress_bar("Uploading", start_time, max_upload_time, batch_progress, total_for_batch, 
                    f"(Total: {current_progress}/{website_total}) (Batch {batch_number} of {batch_count})")
                
                # Check if progress changed
                if current_progress != last_progress:
                    last_progress = current_progress
                    last_progress_change_time = time.time()
                    
                # If we reached the expected end count for this batch, exit
                if current_progress >= batch_end_count:
                    time.sleep(5)  # Give it a few seconds after reaching target
                    logger.debug(f"\nUpload reached target {batch_end_count} - batch complete")
                    break
            else:
                print(f"\rUploading: Waiting for progress update... ('{text}')", end="")
                
            # Check for stalled progress
            if time.time() - last_progress_change_time > stall_timeout:
                logger.info(f"\nProgress stalled for {stall_timeout}s - checking completion status")
                save_debug_snapshot(driver, f"progress_stalled_batch_number_{batch_number}_of_{batch_count}")
                break
                
        except NoSuchElementException:
            # Progress element has disappeared - try to get final count one more time
            try:
                # Wait a moment and try to read the final count
                time.sleep(2)
                upload_text_elem = driver.find_element(By.XPATH, upload_text_xpath)
                text = upload_text_elem.text.strip()
                if " of " in text:
                    parts = text.split(" of ")
                    final_progress = int(parts[0])
            except:
                pass  # If we can't get it, use the last known value
            logger.info("\nUpload complete - progress indicator disappeared. Continuing")
            break
        except Exception as e:
            logger.warning(f"\nWarning reading progress: {e}. Continuing")
            # Don't update the last_progress_change_time on errors
    
    print(f"\r")
    
    # Verify that all files were uploaded successfully
    if final_progress > 0 and final_progress < batch_end_count:
        missing_count = batch_end_count - final_progress
        logger.warning(f"⚠️  WARNING: Batch {batch_number} incomplete! Only {final_progress}/{batch_end_count} files uploaded. {missing_count} file(s) failed to upload.")
        logger.warning(f"This may indicate upload failures. Check the debug snapshots for details.")
        # Still return True to continue with other batches, but log the issue
    elif final_progress == 0:
        logger.warning(f"⚠️  WARNING: Could not determine final upload count for batch {batch_number}. Upload may have failed.")
    else:
        logger.debug(f"Batch {batch_number} upload complete: {final_progress}/{batch_end_count} files uploaded successfully.")
    
    return True

def upload_photos(driver, selected_images, batch_size):
    """Upload photos to the current playlist in batches."""
    global debug_directory
    try:
        # logger.info("Preparing to upload photos max_file_size_mb=%d, max_photos=%d, batch_size=%d ..." % (max_file_size_mb, max_photos, batch_size))
        
        # Track cumulative uploads across all batches
        cumulative_uploaded_count = 0

        # Write cumulative list to debug file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        debug_file_name = f"{timestamp}_uploaded_files.txt"
        logfile=None
        try:
            debug_file_path = os.path.join(debug_directory, debug_file_name)  # Use debug_screenshots directory
            logfile=open(debug_file_path, "w")
        except Exception as e:
            logger.warning(f"Error creating {debug_file_name}. Continuing")
           
       
        for i in range(0, len(selected_images), batch_size):
            batch = selected_images[i:i + batch_size]
            batch_number = i // batch_size + 1
            batch_count = ((len(selected_images) - 1) // batch_size + 1)

            # Expected start and end counts for this batch
            batch_end_count = cumulative_uploaded_count + len(batch)

            
            # Upload the batch
            logger.debug(f"Uploading batch {batch_number} of {batch_count} ({len(batch)} photos)...")
            batch_success = upload_batch(
                driver, 
                batch, 
                batch_number, 
                batch_count,
                batch_end_count,
                logfile
            )
            
            if batch_success:
                # Update the cumulative count for the next batch
                cumulative_uploaded_count += len(batch)

            
            # Optional: wait briefly between batches
            time.sleep(5)
            
        logger.info("All batches uploaded.")
        
        logger.info(f"List of all uploaded files written to {debug_file_path}")
        return True
        
    except Exception as e:
        logger.error(f"upload_photos() Exception: {e}")
        save_debug_snapshot(driver, "upload_exception")
        return False

from types import SimpleNamespace
        
def main():
    """Main function to orchestrate the Nixplay photo upload process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Upload photos to Nixplay')
    parser.add_argument('-c', '--config', 
                        default='config.json',
                        help='Path to configuration file (default: config.json)')
    args = parser.parse_args()
    
    # Load config first to get debug_directory
    config = load_config(args.config)
    
    # Set up file logging first so all logs are captured
    setup_file_logging(config.get('debug_directory', 'debug'))
    
    # Convert dictionary to an object with attributes
    cfg = SimpleNamespace(**config)
    
    # Now you can use cfg.username, cfg.password, etc.
    for key, value in vars(cfg).items():
        if key == "password":
            logger.debug(f"{key}: **************")
        else:
            logger.debug(f"{key}: {value}")

    image_files = get_image_files(cfg.photos_directory, cfg.max_file_size_mb, cfg.max_photos, cfg.image_width, cfg.image_height, cfg.date_format, cfg.caption_position, cfg.font_size, cfg.font_path, cfg.caption)
    if not image_files:
        logger.error(f"No image files found in '{cfg.photos_directory}'.")
        exit(1)

    logger.debug(f"Found {len(image_files)} image files.")
    driver = setup_webdriver(cfg.headless)
    
    try:
        if not login_to_nixplay(driver, cfg.base_url, cfg.username, cfg.password):
            logger.error("Login failed. Exiting.")
            exit(1)
        
        if(cfg.delete_my_uploads == True):
            if not delete_my_uploads(driver, cfg.base_url):
                logger.warning("Failed to delete 'My Uploads'. Continuing with upload...")
        
        # Navigate to playlist
        if not find_playlist(driver, cfg.base_url, cfg.playlist_name):
            logger.error(f"Could not find playlist '{cfg.playlist_name}'. Exiting.")
            return False
 
#        if(cfg.delete_my_uploads == False):
        if not delete_all_from_playlist(driver):
            logger.warning("Failed to delete existing photos. Continuing with upload...")
        
        if not upload_photos(driver, image_files, cfg.batch_size ):
            logger.error("Failed to upload photos.")
            exit(1)
        
        logger.info("Nixplay photo upload completed successfully!")
    except Exception as e:
        logger.error(f"main() Exception: {str(e)}")
        save_debug_snapshot(driver, "unexpected_error")
    finally:
        logger.debug("Closing WebDriver...")
        save_debug_snapshot(driver, "final_state_before_exit")
        driver.quit()


if __name__ == "__main__":
    main()
