# nix-upload
A Python utility that automatically uploads photos from your local directory (recursively) to Nixplay digital photo frames. The tool supports batch processing, image resizing, and text overlay with date and location information.

>[!CAUTION]
This script will potentially DELETE ALL OF YOUR PREVIOUSLY UPLOADED photos if you set the **delete_my_uploads** configuration value to **true**,


## How to Install
1. **Prerequisites**
   - Python 3.8 or higher
   - A Nixplay account
   - Local directory containing photos to upload

2. **Set Up Project Directory**
   - Create a new directory for the project
   - Copy the following files into it:
     - `nix-upload.py`
     - `requirements.txt`
     - `sample_config.json`
   - Make a copy of `sample_config.json` and name it `config.json`:
     ```bash
     # Windows
     copy sample_config.json config.json
     
     # macOS/Linux
     cp sample_config.json config.json
     ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the Application**
   - Edit `config.json` with your credentials and preferences
   - Required parameters:
     - `username`: Your Nixplay account email
     - `password`: Your Nixplay account password
     - `photos_directory`: Path to your photos directory

5. **Run**
   ```bash
   python nix-upload.py
   ```
   
   You can also specify a custom configuration file using the `--config` (or `-c`) option:
   ```bash
   python nix-upload.py --config my-custom-config.json
   ```

## Configuration Parameters

The script uses a `config.json` file for configuration. Here are all available parameters:

### Required Parameters
- `username`: Your Nixplay account username
- `password`: Your Nixplay account password
- `photos_directory`: Path to the directory containing your photos

### Optional Parameters
- `base_url`: Nixplay website URL (default: "https://app.nixplay.com")
- `playlist_name`: Name of the Nixplay playlist to upload to (default: "nix-upload")
- `delete_my_uploads`: Whether to delete your "My uploads" album every time (default: false)
- `max_photos`: Maximum number of photos to upload (default: 500)
- `max_file_size_mb`: Maximum file size for each photo in MB (default: 3)
- `batch_size`: Number of photos to upload in each batch (default: 100)
- `image_width`: Target width for resized images (default: 1280)
- `image_height`: Target height for resized images (default: 800)
- `log_level`: Logging level (default: "INFO")
- `headless`: Run browser in headless mode (default: true)
- `caption`: Whether to add text overlay with date and location (default: true)
- `date_format`: Format for date display on photos (default: "%Y-%m-%d %H:%M")
- `caption_position`: Position of text overlay ("top" or "bottom", default: "bottom")
- `font_size`: Font size for text overlay in points (default: 40)
- `font_path`: Path to custom font file (default: null, uses system font)
  - Windows examples:
    - `"C:/Windows/Fonts/arial.ttf"`
    - `"C:/Windows/Fonts/calibri.ttf"`
    - `"C:/Windows/Fonts/helvetica.ttf"`
  - macOS examples:
    - `"/Library/Fonts/Arial.ttf"`
    - `"/Library/Fonts/Helvetica.ttc"`
    - `"/System/Library/Fonts/Helvetica.ttc"`
  - Linux examples:
    - `"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"`
    - `"/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"`

### Date Format Options
Common date format options for the `date_format` parameter:

- `"%b %Y"` - Month and year (Jan 2024)
- `"%B %Y"` - Full month name and year (January 2024)
- `"%b %d, %Y"` - Month, day, and year (Jan 15, 2024)
- `"%Y-%m"` - Year and month (2024-01)
- `"%m/%Y"` - Month and year (01/2024)

### Example Configuration
```json
{
    "username": "USERNAME",
    "password": "PASSWORD",
    "photos_directory": "PATH/TO/ROOT/OF/YOUR/PHOTOS/DIR",
    "base_url": "https://app.nixplay.com",
    "playlist_name": "nix-upload",
    "delete_my_uploads": true,
    "max_photos": 500,
    "max_file_size_mb": 3,
    "batch_size": 100,
    "image_width": 1280,
    "image_height": 800,
    "log_level": "INFO",
    "headless": false,
    "caption": true,
    "caption_position": "bottom",
    "date_format": "%b %Y",
    "font_size": 50,
    "font_path": "C:/Windows/Fonts/arial.ttf"
}
```

## To run:
1. open a command shell in the "nix-upload" directory on your computer
2. Run "python nix-upload.py"
   - Optionally specify a custom config file: "python nix-upload.py --config my-config.json"

## NOTE
The script will first DELETE ALL PHOTOS from the specified playlist. Then it will upload all the new photos to the same playlist.
>[!CAUTION]
This script will DELETE ALL OF YOUR PREVIOUSLY UPLOADED photos if you set the **delete_my_uploads** configuration value to **true**,

## Known issues:
- I dont know why this warning shows, but it seems to be a benign message
"Attempting to use a delegate that only supports static-sized tensors with a graph that has dynamic-sized tensors (tensor#-1 is a dynamic-sized tensor)."
- In your config.json file, set "max_photos" to not more than 1900, and "batch_size" to not more than 100, for best performance

## License
Apache License 2.0

## Disclaimer
Use at your own Risk

