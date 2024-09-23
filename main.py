import calendar
import csv
import multiprocessing
import sys
from functools import partial

import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
from datetime import datetime
import humanize
from tqdm import tqdm
import argparse

SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']
BASE_PATH = "./photos"


def create_folder_structure(base_path, year, month, day):
    month_name = calendar.month_abbr[month]
    folder_path = os.path.join(base_path, str(year), month_name, str(day))
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def parse_timestamp(timestamp):
    try:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")


def download_item(base_path, item):
    filename = item['filename']
    creation_time = parse_timestamp(item['mediaMetadata']['creationTime'])
    year = creation_time.year
    month = creation_time.month
    day = creation_time.day

    folder_path = create_folder_structure(base_path, year, month, day)
    file_path = os.path.join(folder_path, filename)
    if os.path.exists(file_path):
        return 0, filename, 0, file_path, True

    media_type = item.get('mimeType', '')
    base_url = item['baseUrl']
    # Define the download URL
    url = f"{base_url}=dv" if "video" in media_type else f"{base_url}=d"
    response = requests.get(url, stream=True)

    file_size = int(response.headers.get('content-length', 0))
    if file_size == 0:
        print(f"File {file_path} size cannot be zero, please retry")
        return 0, filename, 0, file_path, True

    # Open the output file in binary mode
    with open(file_path, 'wb') as file:
        # Create a progress bar using tqdm
        with tqdm(total=file_size, unit='B', unit_scale=True, desc=file_path, ascii=True) as pbar:
            # Iterate over the response data in chunks
            for data in response.iter_content(chunk_size=1024*1024):
                # Write the chunk to the file
                file.write(data)
                # Update the progress bar
                pbar.update(len(data))

    human_readable_size = humanize.naturalsize(file_size)
    return file_size, filename, human_readable_size, file_path, False



def fetch_items_from_api(service, body):
    # Retrieve photos
    items = []
    while True:
        results = service.mediaItems().search(
            body=body
        ).execute()
        items.extend(results.get('mediaItems', []))
        page_token = results.get('nextPageToken')
        body["pageToken"] = page_token
        print(f"Loading {len(items)} items")
        if not page_token:
            break
    print(f"Loaded {len(items)} items")
    return items


def save_items_to_csv(csv_file, items):
    with open(csv_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'filename', 'creationTime', 'baseUrl']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for item in items:
            writer.writerow({
                'id': item['id'],
                'filename': item['filename'],
                'creationTime': item['mediaMetadata']['creationTime'],
                'baseUrl': item['baseUrl']
            })


def load_items_from_csv(csv_file):
    items = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            items.append({
                'id': row['id'],
                'filename': row['filename'],
                'mediaMetadata': {'creationTime': row['creationTime']},
                'baseUrl': row['baseUrl']
            })
    return items


def handle_month(service, month, year, ignore_cache=False):
    # Format dates for API
    date_filter = {
        'ranges': [{
            'startDate': {'year': year, 'month': month, 'day': 1},
            'endDate': {'year': year, 'month': month, 'day': 31}
        }]
    }
    csv_file = f'video_{year}_{month}.csv'
    # Check if CSV file exists
    if not ignore_cache and os.path.exists(csv_file):
        print("Loading items from CSV...")
        items = load_items_from_csv(csv_file)
    else:
        print("Fetching items from API...")
        body = {
            "pageSize": "100",
            "pageToken": None,
            "filters": {
                "dateFilter": date_filter
            }
        }
        items = fetch_items_from_api(service, body)
        save_items_to_csv(csv_file, items)
    handle_items(items)

def handle_items(items, base_path=None):
    total_items = len(items)
    skipped_count = 0
    # Use multiprocessing to download items in parallel
    base_path = base_path or BASE_PATH
    with multiprocessing.Pool(processes=8) as pool:
        download_func = partial(download_item, base_path)

        # Use tqdm to show progress
        with tqdm(total=total_items, desc="Downloading", unit="item") as pbar:
            results = []
            for result in pool.imap_unordered(download_func, items):
                file_size, filename, human_readable_size, file_path, is_skipped = result
                skipped_count += int(is_skipped)
                results.append(file_size)
                pbar.update(1)
                pbar.set_postfix({"Last": f"{filename} ({human_readable_size})"})

    total_size = sum(results)

    print(f"\nTotal items downloaded: {total_items - skipped_count}")
    print(f"Skipped items: {skipped_count}")
    print(f"Total size downloaded: {humanize.naturalsize(total_size)}\n")


def iterate_months(start_year, start_month, end_year, end_month):
    current_year = start_year
    current_month = start_month

    while (current_year, current_month) <= (end_year, end_month):
        yield current_year, current_month

        # Increment the month and adjust the year if needed
        if current_month == 12:
            current_month = 1
            current_year += 1
        else:
            current_month += 1

def get_service():
    creds = None
    if os.path.exists('token1.json'):
        creds = Credentials.from_authorized_user_file('token1.json', SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            'auth.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token1.json', 'w') as token:
            token.write(creds.to_json())

    return build("photoslibrary", "v1", credentials=creds, static_discovery=False)

def main(start_year, start_month, end_year, end_month, ignore_cache=False):
    service = get_service()
    for year, month in iterate_months(start_year, start_month, end_year, end_month):
        print(f"********* Start **********\nProcessing month: {year}-{month:02d}\n\n")
        handle_month(service, month, year, ignore_cache)
        print(f"Processed month: {year}-{month:02d}\n********* End **********\n\n")

def download_albums():
    service = get_service()
    # List albums
    albums_result = service.albums().list(pageSize=50).execute()
    albums = albums_result.get('albums', [])
    # List all shared albums
    shared_albums_result = service.sharedAlbums().list(pageSize=50).execute()
    shared_albums = shared_albums_result.get('sharedAlbums', [])
    # Search for media items in the album
    for album in albums + shared_albums:
        album_id = album['id']
        album_title = album.get('title', 'unknown')
        print(f"********* Start **********\nProcessing album: {album_title}\n\n")
        items = fetch_items_from_api(service, {"albumId": album_id,
                                               "pageSize": "100",
                                               "pageToken": None})
        handle_items(items, base_path=f"./albums/{album_title}")
        print(f"Processed month: {album_title}\n********* End **********\n\n")



def valid_year(value):
    """Validate the year input."""
    try:
        year = int(value)
        if year < 1:
            raise argparse.ArgumentTypeError("Year must be a positive integer.")
        return year
    except ValueError:
        raise argparse.ArgumentTypeError("Year must be an integer.")

def valid_month(value):
    """Validate the month input."""
    try:
        month = int(value)
        if month < 1 or month > 12:
            raise argparse.ArgumentTypeError("Month must be an integer between 1 and 12.")
        return month
    except ValueError:
        raise argparse.ArgumentTypeError("Month must be an integer.")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Process a date range with validation.")

    # Define the arguments
    parser.add_argument('--start_year', type=valid_year, required=True, help="Start year (positive integer).")
    parser.add_argument('--start_month', type=valid_month, required=True, help="Start month (1-12).")
    parser.add_argument('--end_year', type=valid_year, required=True, help="End year (positive integer).")
    parser.add_argument('--end_month', type=valid_month, required=True, help="End month (1-12).")
    parser.add_argument('--disable-cache', action='store_true', default=False,
                        help="disable cache (default: False).")


    args = parser.parse_args()

    # Validate that the end date is after the start date
    start_date = datetime(args.start_year, args.start_month, 1)
    end_date = datetime(args.end_year, args.end_month, 1)

    if end_date < start_date:
        sys.exit("Error: End date must be after start date.")

    return args

if __name__ == "__main__":
    args = parse_arguments()

    print(f"Start Date: {args.start_year}-{args.start_month:02d}")
    print(f"End Date: {args.end_year}-{args.end_month:02d}")
    main(args.start_year, args.start_month, args.end_year, args.end_month, args.disable_cache)
