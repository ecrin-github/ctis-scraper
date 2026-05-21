import copy
from datetime import datetime
import json
import os
from typing import Iterator, Tuple, Final
from dataclasses import dataclass
from requests import exceptions
import time

import requests
import yaml
from dacite import from_dict, Config

from src.log import logger
from src.helpers import download_file, validate_response
from src.parse import TrialOverview, FullTrial

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

SEARCH_CRITERIA_PAYLOAD: dict = config["api"]["overview"]["payload"]["searchCriteria"]
DOWNLOAD_URL: Final[str] = "https://euclinicaltrials.eu/ctis-public-api/search/download"
DOWNLOAD_STATUS_IN_PROGRESS: Final[str] = "In progress"
DOWNLOAD_STATUS_DONE: Final[str] = "Done"

OVERVIEW_PAYLOAD: dict = config["api"]["overview"]["payload"]
OVERVIEW_URL: Final[str] = "https://euclinicaltrials.eu/ctis-public-api/search"
OVERVIEW_HEADERS: Final[str] = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:130.0) Gecko/20100101 Firefox/130.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Content-Type": "application/json",
    "Origin": "https://euclinicaltrials.eu",
    "Connection": "keep-alive",
    "Referer": "https://euclinicaltrials.eu/ctis-public/search?lang=en",
}

GEOCODING_URL: Final[str] = f"https://nominatim.openstreetmap.org/search"
GEOCODING_HEADERS: dict = config["api"]["geocoding"]["headers"]


def get_trial_overview() -> Iterator[TrialOverview]:
    """
    Generate a generator that yields TrialOverview dataclasses.

    This function paginates through the API results, processing each page
    and parsing data into TrialOverview dataclass and yielding it. Handles pagination by
    incrementing the page number and checking for the availability of
    the next page.

    Yields:
        dataclass: Instance of TrialOverview containing trial overview data parsed from response json
    """
    next_page_available = True
    page = 1
    payload = OVERVIEW_PAYLOAD

    while next_page_available:
        payload["pagination"]["page"] = page

        initial_retry_delay = 30
        got_trial_data = False
        retry_delay = initial_retry_delay

        while not got_trial_data and retry_delay <= 120:
            try:
                r = requests.post(
                    OVERVIEW_URL, headers=OVERVIEW_HEADERS, data=json.dumps(payload)
                )
                json_data = validate_response(r)
            except exceptions.HTTPError as e:
                print("HTTP Error, retrying after " + str(retry_delay) + " seconds")
                time.sleep(retry_delay)
                retry_delay = retry_delay * 2
                continue

            for trial in json_data["data"]:
                trial_overview = from_dict(
                    data=trial,
                    data_class=TrialOverview,
                    config=Config(check_types=False, strict=True),
                )
                yield trial_overview

            page += 1
            next_page_available = json_data["pagination"]["nextPage"]
            got_trial_data = True


def download_all_trials(data_dir: str) -> str:
    """
    Downloads a CSV file containing all CTIS trials (as one would by clicking the "Download results" button on the website).

    Parameter:
    - data_dir: Path to directory where to download the JSON file

    Returns:
    - csv_path: Downloaded CSV file path
    """
    total_records_number = get_total_trial_records()
    payload = {
        "strategy": {"size": total_records_number, "type": "All"},
        "searchCriteria": copy.copy(SEARCH_CRITERIA_PAYLOAD),
    }

    # Starting download
    print("Starting CSV download task")
    r = requests.post(DOWNLOAD_URL, headers=OVERVIEW_HEADERS, data=json.dumps(payload))
    json_data = validate_response(r)

    if not "taskId" in json_data:
        raise Exception("Failed to download all CSV trials")

    download_check_freq = 2
    file_location = ""

    task_id = json_data["taskId"]

    # Checking API at regular intervals until task is finished and we have a download link
    while not file_location:
        time.sleep(download_check_freq)

        r = requests.get(f"{DOWNLOAD_URL}/{task_id}")
        json_data = validate_response(r)

        status = json_data["status"]
        if status != DOWNLOAD_STATUS_IN_PROGRESS and status != DOWNLOAD_STATUS_DONE:
            raise ValueError(f"Unexpected download status value: {status}")

        file_location = json_data["file_location"]  # Empty or download link

    print("CSV Download task finished!")

    file_location = file_location.strip()
    if file_location[0] == '"':
        file_location = file_location[1:]
    if file_location[-1] == '"':
        file_location = file_location[:-1]

    print(f"CSV File to download: {file_location}")

    start_timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    csv_filename = f"{start_timestamp}_trials.csv"

    print("Downloading CSV file")

    csv_path = os.path.join(data_dir, csv_filename)
    download_file(file_location, csv_path)

    print(f"CSV File downloaded to {csv_path}")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Couldn't find downloaded CSV file: {csv_path}")

    return csv_path


def get_total_trial_records() -> int:
    """
    Uses the overview api endpoint to return the total number of trials currently available.
    """
    r = requests.post(
        OVERVIEW_URL, headers=OVERVIEW_HEADERS, data=json.dumps(OVERVIEW_PAYLOAD)
    )
    json_data = validate_response(r)
    total_trials = json_data.get("pagination").get("totalRecords")
    return total_trials


def get_full_trial(ct_number: str) -> FullTrial:
    """
    Requests the trial details api endpoint to get trial details of a single trial and parses json data to TrialDesign dataclass.

    Parameter:
    - ct_number: The ct number identifier of a trial listed in the ctis portal.

    Returns:
    - full_trial: An instance of the FullTrial dataclass
    """
    full_trial_url = f"https://euclinicaltrials.eu/ctis-public-api/retrieve/{ct_number}"
    r = requests.get(full_trial_url)
    json_data = validate_response(r)

    full_trial = from_dict(
        FullTrial,
        json_data,
        config=Config(check_types=False, strict=False),
    )
    return full_trial


def get_full_trial_raw(ct_number: str) -> dict:
    """
    Requests the trial details api endpoint to get trial details of a single trial and returns the raw JSON response.

    Parameter:
    - ct_number: The ct number identifier of a trial listed in the ctis portal.

    Returns:
    - json_data: The single trial JSON data
    """
    full_trial_url = f"https://euclinicaltrials.eu/ctis-public-api/retrieve/{ct_number}"
    r = requests.get(full_trial_url)
    json_data = validate_response(r)

    return json_data


def get_location_coordinates(
    street: str, city: str, country: str, postalcode: str
) -> Tuple[int, int]:
    """
    Uses the Nomatim geocoding api to get lat and lon coordinates for provided address information

    Parameter:
    - street: Location street
    - city: Location city
    - country: Location country
    - postalcode: Location postalcode

    Returns:
    - A tuple containing lat and lon coordinates if coordinates were found. Returns a tuple containing None, None otherwise.
    """

    params = {
        "street": street,
        "city": city,
        "postalcode": postalcode,
        "country": country,
        "format": "json",
        "limit": "1",
    }

    r = requests.get(GEOCODING_URL, params=params, headers=GEOCODING_HEADERS)
    json_data = validate_response(r)

    if len(json_data) == 0:
        logger.debug(f"No coordinates found for {street}, {city}, {country}")
        return None, None

    lat = json_data[0]["lat"]
    lon = json_data[0]["lon"]
    return lat, lon
