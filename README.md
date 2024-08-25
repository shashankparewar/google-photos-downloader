# google-photos-downloader
Download photos from your google photos account.


## Decision Driver
The primary purpose why this repo was created was:
- I wanted to download photos within a date range.
- Google Photos doesn't provide interface to do so.

## Features of this script
The primary action is to download photos from a google account. Other notable features:
- Script takes `start_year`, `start_month`, `end_year`, `end_month` as input.
- Photos existing in the date range provided are downloaded.
- Downloads are granularized on per-month basis.
- Creates folders based on file creation date( folder structure is `year/month/day/file_name`)
- The photos metadata (fetched from api) is stored in csv file to prevent unnecessary API calls.
  - csv format - `photo_{year}-{month}.csv`
  - if the csv file is present, fetching metadata from source api is skipped.
  - If there is an error while pushing items to csv, please delete the csv before retrying the script.
- Skipping files if they are already present in the destination.
- Multiprocessing integration to parallely download multiple files (may not help in case files are large since network bandwidth limits the total speed).
- Progress Bar integration using `tqdm` package.
- Information related to total items, total download size

## Setup
- Setup your google account to allow access for Google Photos Library API
  - Follow the [link](https://developers.google.com/photos/library/guides/get-started) to setup developer account.
  - Download the OAuth 2.0 Credentials
    - After creating the OAuth client, you'll be given a Client ID and Client Secret.
    - Download the credentials in JSON format(auth.json) and save them securely, as you'll need them to authenticate your application.
    - Move `auth.json` to the same folder as the script.
  - Go to [API Dashboard](https://console.cloud.google.com/apis/dashboard)
    - go to `OAuth consent screen`
    - Under `Test Users`, click on `Add Users`
    - Add your email as test user.
    - This step allows your account(associated with email) to be accessed by the application.
- Setup python environment
  - Install python on your system(tested with 3.11)
  - Install dependencies - `pip install -r requirements.txt`


## Run script
Example -
`python main.py --start_year 2022 --start_month 1 --end_year 2022 --end_month 12`
