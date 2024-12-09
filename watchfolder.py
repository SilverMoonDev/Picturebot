import os
import time
import requests
import configparser
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class Watcher:
    def __init__(self, directory_to_watch):
        self.DIRECTORY_TO_WATCH = directory_to_watch
        self.observer = Observer()

    def run(self):
        event_handler = Handler()
        self.observer.schedule(event_handler, self.DIRECTORY_TO_WATCH, recursive=False)
        self.observer.start()
        try:
            while True:
                print("Waiting for new pictures...")
                time.sleep(5)
        except KeyboardInterrupt:
            self.observer.stop()
            print("Stopped Watching for new pictures")

        self.observer.join()

class Handler(FileSystemEventHandler):
    @staticmethod
    def on_created(event):
        if event.is_directory:
            return None

        elif event.src_path.endswith(('.png', '.jpg', '.jpeg')):
            print(f"Received created event - {event.src_path}")
            send_file_and_metadata_to_discord(event.src_path)

def send_file_and_metadata_to_discord(file_path):
    config = configparser.ConfigParser()
    config.read('config.ini')
    if 'settings' not in config:
        print("Error: 'settings' section not found in config.ini")
        return
    
    webhook_url = config['settings']['webhook_url']
    
    # Retry opening the file until it's available
    for attempt in range(5):  # Retry 5 times
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
            break  # If successful, exit the loop
        except PermissionError:
            print(f"File is locked, retrying... (Attempt {attempt + 1}/5)")
            time.sleep(1)  # Wait 1 second before retrying
    else:
        print("Failed to open file after multiple attempts.")
        return

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    creation_time = time.ctime(os.path.getctime(file_path))

    metadata = f"**File Name:** {file_name}\n**Original File Size:** {file_size} bytes\n**Creation Time:** {creation_time}"

    response = requests.post(
        webhook_url,
        files={'file': (file_name, file_data)},
        data={"content": metadata}
    )
    if response.status_code == 200:
        print("File and metadata successfully sent to Discord")
    else:
        print(f"Failed to send file and metadata to Discord with status code {response.status_code}")

if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('config.ini')
    print("Config file content:", open('config.ini').read())  # Debug print
    print("Config sections:", config.sections())  # Debug print
    if 'settings' not in config:
        print("Error: 'settings' section not found in config.ini")
        exit(1)
    print("Settings keys:", list(config['settings'].keys()))  # Debug print
    print("Settings content:", dict(config['settings']))  # Debug print
    
    directory_to_watch = config['settings']['directory_to_watch']
    
    w = Watcher(directory_to_watch)
    w.run()
