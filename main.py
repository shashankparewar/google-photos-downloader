import calendar
import csv
import multiprocessing
from functools import partial

import requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os
from datetime import datetime, timedelta
import humanize
from tqdm import tqdm

SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']
BASE_PATH = "./downloaded"


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
        print(f"File {file_path} already exists, skipping")
        return 0, filename, 0, file_path

    url = item['baseUrl'] + '=d'
    response = requests.get(url)

    file_size = int(response.headers.get('content-length', 0))

    with open(file_path, 'wb') as file:
        file.write(response.content)

    human_readable_size = humanize.naturalsize(file_size)
    return file_size, filename, human_readable_size, file_path

def fetch_items_from_api(service, date_filter):
    # Retrieve photos
    items = []
    page_token = None
    while True:
        results = service.mediaItems().search(
            body={
                "pageSize": "100",
                "pageToken": page_token,
                "filters": {
                    "dateFilter": date_filter,
                    "mediaTypeFilter": {
                        "mediaTypes": [
                            "PHOTO"
                        ]
                    }
                }
            }
        ).execute()
        items.extend(results.get('mediaItems', []))
        page_token = results.get('nextPageToken')

        if not page_token:
            break
        print(f"Loading {len(items)} items")
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

def handle_month(service, month, year):
    # Format dates for API
    date_filter = {
        'ranges': [{
            'startDate': {'year': year, 'month': month, 'day': 1},
            'endDate': {'year': year, 'month': month, 'day': 31}
        }]
    }
    csv_file = f'photo_{year}_{month}.csv'
    # Check if CSV file exists
    if os.path.exists(csv_file):
        print("Loading items from CSV...")
        items = load_items_from_csv(csv_file)
    else:
        print("Fetching items from API...")
        items = fetch_items_from_api(service, date_filter)
        save_items_to_csv(csv_file, items)
    total_items = len(items)
    # Use multiprocessing to download items in parallel
    with multiprocessing.Pool(processes=8) as pool:
        download_func = partial(download_item, BASE_PATH)

        # Use tqdm to show progress
        with tqdm(total=total_items, desc="Downloading", unit="item") as pbar:
            results = []
            for result in pool.imap_unordered(download_func, items):
                file_size, filename, human_readable_size, file_path = result
                results.append(file_size)
                pbar.update(1)
                pbar.set_postfix({"Last": f"{filename} ({human_readable_size})"})

    total_size = sum(results)

    print(f"\nTotal items downloaded: {total_items}")
    print(f"Total size downloaded: {humanize.naturalsize(total_size)}")

def main():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            'auth.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build("photoslibrary", "v1", credentials=creds, static_discovery=False)
    year = 2021
    for month in range(12, 0, -1):
        handle_month(service, month, year)



if __name__ == '__main__':
    main()