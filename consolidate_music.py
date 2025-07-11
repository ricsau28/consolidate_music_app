import os
from getpass import getpass
import stat
import tempfile
import time

# Optional: For SFTP support
try:
    import paramiko
except ImportError:
    paramiko = None

# Optional: For music metadata extraction
try:
    from mutagen import File as MutagenFile
except ImportError:
    MutagenFile = None

def prompt_base_directory():
    default = "/media/ricsau/MUSIC/Richard"
    base_dir = input(f"Enter base save directory [{default}]: ").strip()
    return base_dir or default

def prompt_scan_directories():
    dirs = input("Enter directories to scan (comma-separated, prefix remote with sftp://): ").strip()
    return [d.strip() for d in dirs.split(",") if d.strip()]

def scan_local_directory(directory):
    music_files = []
    for root, _, files in os.walk(directory):
        # Skip any folder/subfolder containing 'iTunes'
        if 'itunes' in root.lower().split(os.sep):
            continue
        if 'itunes' in root.lower():
            continue
        for file in files:
            if file.lower().endswith((".mp3", ".m4a", ".flac", ".wav", ".m4p")):
                music_files.append(os.path.join(root, file))
    return music_files

def get_sftp_client(sftp_url, sftp_clients={}):
    import re
    pattern = r"sftp://(?:(?P<user>[^@]+)@)?(?P<host>[^:/]+):(?P<path>/.*)"
    match = re.match(pattern, sftp_url)
    if not match:
        print(f"Invalid SFTP URL: {sftp_url}")
        return None, None, None, None
    user = match.group('user') or input("SFTP username: ")
    host = match.group('host')
    password_key = f"{user}@{host}"
    if password_key not in sftp_clients:
        password = getpass(f"Password for {user}@{host}: ")
        try:
            transport = paramiko.Transport((host, 22))
            transport.connect(username=user, password=password)
            sftp = paramiko.SFTPClient.from_transport(transport)
            sftp_clients[password_key] = (sftp, transport, password)
        except Exception as e:
            print(f"SFTP connection failed: {e}")
            return None, None, None, None
    else:
        sftp, transport, password = sftp_clients[password_key]
    path = match.group('path')
    return sftp, transport, path, password_key

def scan_sftp_directory(sftp_url, sftp_clients={}):
    if not paramiko:
        print("paramiko not installed. Cannot scan SFTP directories.")
        return []
    import re
    sftp, transport, path, password_key = get_sftp_client(sftp_url, sftp_clients)
    if not sftp:
        return []
    user, host = password_key.split('@')
    music_files = []
    def recursive_list(remote_path):
        # Skip any folder/subfolder containing 'iTunes'
        if 'itunes' in remote_path.lower().split('/'):
            return
        if 'itunes' in remote_path.lower():
            return
        try:
            for entry in sftp.listdir_attr(remote_path):
                full_path = os.path.join(remote_path, entry.filename)
                if stat.S_ISDIR(entry.st_mode):
                    recursive_list(full_path)
                else:
                    if entry.filename.lower().endswith((".mp3", ".m4a", ".flac", ".wav", ".m4p")):
                        music_files.append(f"sftp://{user}@{host}:{full_path}")
        except Exception as e:
            print(f"Error listing {remote_path}: {e}")
    recursive_list(path)
    return music_files

def extract_metadata(filepath):
    if not MutagenFile:
        return {"artist": "Unknown"}
    audio = MutagenFile(filepath, easy=True)
    artist = audio.get("artist", ["Unknown"])[0] if audio else "Unknown"
    return {"artist": artist}

def download_sftp_file(sftp_url, sftp_clients={}):
    import re
    sftp, transport, path, password_key = get_sftp_client(sftp_url, sftp_clients)
    if not sftp:
        return None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            sftp.get(path, tmp.name)
            tmp_path = tmp.name
        return tmp_path
    except Exception as e:
        print(f"Failed to download {sftp_url}: {e}")
        return None

def close_all_sftp_clients(sftp_clients):
    for sftp, transport, _ in sftp_clients.values():
        try:
            sftp.close()
            transport.close()
        except Exception:
            pass

def copy_file_to_destination(local_path, dest_path):
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    import shutil
    shutil.copy2(local_path, dest_path)

def estimate_scan_time(scan_dirs, base_dir, sftp_clients, sample_size=10, threshold_seconds=60):
    sample_files = []
    start_time = time.time()
    count = 0
    for d in scan_dirs:
        if d.startswith("sftp://"):
            print(f"Warning: Cannot estimate scan time for SFTP directory: {d}")
            continue
        for root, _, files in os.walk(d):
            for file in files:
                if file.lower().endswith((".mp3", ".m4a", ".flac", ".wav", ".m4p")):
                    sample_files.append(os.path.join(root, file))
                    count += 1
                    if count >= sample_size:
                        break
            if count >= sample_size:
                break
        if count >= sample_size:
            break
    elapsed = time.time() - start_time
    if count == 0:
        return 0, 0
    # Estimate total files
    total_files = 0
    for d in scan_dirs:
        if d.startswith("sftp://"):
            continue
        for root, _, files in os.walk(d):
            for file in files:
                if file.lower().endswith((".mp3", ".m4a", ".flac", ".wav", ".m4p")):
                    total_files += 1
    if total_files == 0:
        return 0, 0
    est_total_time = (elapsed / count) * total_files
    return total_files, est_total_time

def main():
    base_dir = prompt_base_directory()
    scan_dirs = prompt_scan_directories()
    all_music_files = []
    sftp_clients = {}
    error_log_path = "error_log.txt"
    processed = 0
    max_files = 5

    # Check that no scan directory is the same as the base save directory
    for d in scan_dirs:
        scan_path = d
        if d.startswith("sftp://"):
            continue
        abs_scan_path = os.path.abspath(os.path.expanduser(scan_path))
        abs_base_dir = os.path.abspath(os.path.expanduser(base_dir))
        if abs_scan_path == abs_base_dir:
            print(f"Error: Scan directory '{scan_path}' is the same as the base save directory '{base_dir}'. Aborting.")
            return
    # Estimate scan time
    total_files, est_total_time = estimate_scan_time(scan_dirs, base_dir, sftp_clients)
    if total_files > 0 and est_total_time > 0:
        print(f"Estimated scan time: {est_total_time:.1f} seconds for {total_files} files.")
        if est_total_time > 60:
            resp = input("Scan may take a long time. Continue? (y/n): ").strip().lower()
            if resp != 'y':
                print("Aborted by user.")
                return
    for d in scan_dirs:
        if d.startswith("sftp://"):
            all_music_files.extend(scan_sftp_directory(d, sftp_clients))
        else:
            all_music_files.extend(scan_local_directory(d))
    print(f"Scan complete. {len(all_music_files)} music files found.")
    for filepath in all_music_files:
        if processed >= max_files:
            break
        is_sftp = filepath.startswith("sftp://")
        local_path = filepath
        tmp_path = None
        try:
            if is_sftp:
                tmp_path = download_sftp_file(filepath, sftp_clients)
                if not tmp_path:
                    raise Exception("Failed to download SFTP file.")
                local_path = tmp_path
            meta = extract_metadata(local_path)
            artist = meta.get("artist", "Unknown")
            filename = os.path.basename(filepath)
            new_location = os.path.join(base_dir, artist, filename)
            if os.path.exists(new_location):
                print(f"Skipped (already exists): {new_location}")
                continue
            copy_file_to_destination(local_path, new_location)
            print(f"Copied {filepath} to {new_location}")
            processed += 1
        except Exception as e:
            with open(error_log_path, "a") as error_log:
                error_log.write(f"Error processing {filepath}: {e}\n")
            print(f"Error processing {filepath}: {e}")
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception as e:
                    with open(error_log_path, "a") as error_log:
                        error_log.write(f"Failed to remove temp file {tmp_path}: {e}\n")
    close_all_sftp_clients(sftp_clients)
    print(f"Done. Errors (if any) are logged in {error_log_path}.")

if __name__ == "__main__":
    main()
