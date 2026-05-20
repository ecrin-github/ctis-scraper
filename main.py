import argparse
import logging
from src.helpers import get_db_uri, get_data_dir
from src.crud import (
    scrape_ctis,
    scrape_ctis_to_file,
    update_location_coordinates,
)


def main():
    parser = argparse.ArgumentParser(description="ctis-scraper")
    parser.add_argument(
        "mode",
        choices=["scrape", "scrape-to-file", "update_coordinates"],
        help="Mode of operation: 'scrape' or 'update_coordinates'",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    DATABASE_URI = get_db_uri()
    DATA_DIR = get_data_dir()

    if args.mode == "scrape-to-file":
        scrape_ctis_to_file(DATA_DIR)
    elif args.mode == "scrape":
        scrape_ctis(DATABASE_URI)
    elif args.mode == "update_coordinates":
        update_location_coordinates(DATABASE_URI)


if __name__ == "__main__":
    main()
