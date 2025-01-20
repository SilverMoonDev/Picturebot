import glob
import json
import os
import re
import time
import requests
import configparser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import ctypes
from ctypes import wintypes
from pathlib import Path
from datetime import datetime

# Main class to watch a directory for new image files
class Watcher:
    def __init__(self, directory_to_watch):
        self.directory_to_watch = directory_to_watch
        self.observer = Observer()
        self.last_month = datetime.now().strftime("%Y-%m")

    # Starts the observer and handles interruptions
    def run(self):
        try:
            event_handler = Handler()
            self.observer.schedule(event_handler, self.directory_to_watch, recursive=False)
            self.observer.start()

            while True:
                current_month = datetime.now().strftime("%Y-%m")
                # If the month has changed, update the directory path
                if current_month != self.last_month:
                    print(f"Month changed, updating path to {current_month}")
                    self.last_month = current_month
                    self.directory_to_watch = get_pictures_path()
                    # Re-schedule the observer with the updated path
                    self.observer.unschedule_all()
                    self.observer.schedule(event_handler, self.directory_to_watch, recursive=False)

                time.sleep(5)  # Keep the program running

        except KeyboardInterrupt:
            self.observer.stop()
            self.observer.join()

# Event handler for file system events
class Handler(FileSystemEventHandler):
    @staticmethod
    def on_created(event):
        if event.is_directory:
            return

        # Handle image files only
        if event.src_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            send_file_and_metadata_to_discord(event.src_path)

# Function to send file and its metadata to a Discord webhook
def send_file_and_metadata_to_discord(file_path):
    config = load_config()
    if not config:
        return

    webhook_url = config['webhook_url']
    
    file_data = read_file_with_retries(file_path)
    if file_data is None:
        return

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    creation_time = time.ctime(os.path.getctime(file_path))
    world_name, world_id, players = get_world_info()

    file_size_mb = file_size / (1024 * 1024)
    metadata = (
        f"**File Name:** {file_name}\n"
        f"**File Size:** {file_size_mb:.2f} MB\n"
        f"**Creation Time:** {creation_time}\n"
        f"**World Name:** {world_name}\n"
        f"**World ID:** {world_id}\n"
        f"**Players In World:**\n{players}"
    )

    response = requests.post(
        webhook_url,
        files={'file': (file_name, file_data)},
        data={"content": metadata}
    )
    if response.status_code == 200:
        print("File and metadata successfully sent to Discord")
    else:
        print(f"Failed to send file and metadata to Discord with status code {response.status_code}")

# Function to load configuration from config.ini
def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    
    if 'settings' not in config:
        print("Error: 'settings' section not found in config.ini")
        return None
    
    return config['settings']

# Function to read a file with retries, handling locked file scenarios
def read_file_with_retries(file_path, max_retries=5, delay=1):
    # Wait for the file to save before accessing it
    time.sleep(1)
    for attempt in range(max_retries):
        try:
            with open(file_path, 'rb') as f:
                return f.read()
        except PermissionError:
            print(f"File is locked, retrying... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
    print("Failed to open file after multiple attempts.")
    return None

def get_pictures_path() -> Path:
    # Get the vrchat config file path
    file_path = os.path.join(os.getenv('USERPROFILE'), 'AppData', 'LocalLow', 'VRChat', 'VRChat', 'config.json')

    # Look for a custom picture path
    try:
        with open(file_path, 'r') as file:
            config_data = json.load(file)
            return Path(config_data["picture_output_folder"])
    except Exception:
        pass

    # Get Windows Pictures Path if there's no custom vrchat pictures path
    PICTURESFOLDERID = 39
    buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(None, PICTURESFOLDERID, None, 0, buf)

    # Return the pictures path with the current month
    return Path(os.path.join(buf.value, 'VRChat', datetime.now().strftime("%Y-%m")))

def get_world_info() -> str:
    root_path = os.path.join(os.getenv('USERPROFILE'), 'AppData', 'LocalLow', 'VRChat', 'VRChat')
    output_log_files = glob.glob(os.path.join(root_path, 'output_log_*'))
    
    latest_log_file = max(output_log_files, key=os.path.getmtime)

    # Log line when the world loads
    worldid_pattern = r"Memory Usage: after world loaded \[([^\]]+)\]"
    world_name_pattern = r"\[Behaviour\] Joining or Creating Room: (.+)"
    player_event_pattern = r"(OnPlayerJoined|OnPlayerLeft)\s+([^\(]+)"


    with open(latest_log_file, 'r', encoding='utf-8') as file:
        log_lines = file.readlines()

    current_players = []

    # Process each line to track players joining or leaving
    for line in log_lines:
        match = re.search(player_event_pattern, line)
        if match:
            event, player_name = match.groups()
            player_name = player_name.strip()

            if event == "OnPlayerJoined" and player_name not in current_players:
                current_players.append(player_name)  # Add player if they join
            elif event == "OnPlayerLeft" and player_name in current_players:
                current_players.remove(player_name)  # Remove player if they leave

    world_name = [re.search(world_name_pattern, line) for line in log_lines if re.search(world_name_pattern, line)]
    # Find all lines that match the pattern
    world_ids = [re.search(worldid_pattern, line) for line in log_lines if re.search(worldid_pattern, line)]

    # Return the current world info
    return world_name[-1].group(1).strip(), world_ids[-1].group(1) , "\n".join(current_players)

if __name__ == '__main__':
    if not os.path.exists('config.ini'):
        print("config file not found")
        exit(1)

    watcher = Watcher(get_pictures_path())
    watcher.run()
