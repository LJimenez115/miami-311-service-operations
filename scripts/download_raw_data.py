"""Download the untouched public source extract for Project 1.

The script intentionally uses only Python's standard library so that anyone can
reproduce the download without installing packages before the EDA stage.
"""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


# Why: Keeping the official layer URL in one place makes the data provenance
# visible, makes updates simple, and prevents a hidden or manually copied source.
LAYER_URL = (
    "https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/"
    "City_of_Miami_311_Service_Requests_Since_2015/FeatureServer/0"
)

# Why: The layer's published `maxRecordCount` is 1,000, so every API page is kept
# at or below that limit to prevent the service from silently returning fewer rows.
PAGE_SIZE = 1_000

# Why: Raw data must stay separate from later cleaned/model-ready data so the
# portfolio can show a traceable, reproducible data lineage.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CHUNKS_DIR = RAW_DIR / "chunks"
RAW_FILE = RAW_DIR / "miami_311_service_requests_raw.csv"
MANIFEST_FILE = RAW_DIR / "miami_311_service_requests_raw_manifest.json"


def fetch_json(url: str, parameters: dict[str, object]) -> dict:
    """Fetch and decode one public ArcGIS API response."""
    # Why: URL parameters are encoded by the standard library to preserve
    # characters such as commas and equals signs safely in the API request.
    request_url = f"{url}?{urlencode(parameters)}"
    with urlopen(request_url, timeout=60) as response:
        return json.load(response)


def get_layer_metadata() -> dict:
    """Read the source schema before extracting records."""
    # Why: The published schema is the authority for the raw CSV column order;
    # this avoids silently guessing, renaming, or dropping source fields.
    return fetch_json(LAYER_URL, {"f": "json"})


def get_record_count() -> int:
    """Ask the source how many records are currently available."""
    # Why: A source count lets the script verify that pagination downloaded every
    # record rather than producing a plausible-looking but incomplete file.
    payload = fetch_json(
        f"{LAYER_URL}/query",
        {"where": "1=1", "returnCountOnly": "true", "f": "json"},
    )
    return int(payload["count"])


def fetch_page(offset: int, field_names: list[str]) -> list[dict]:
    """Fetch one ordered page of attributes, excluding geometry from this CSV."""
    # Why: Coordinates are already published as source attributes. Excluding the
    # duplicate GIS geometry keeps this raw analysis file tabular and portable.
    payload = fetch_json(
        f"{LAYER_URL}/query",
        {
            "where": "1=1",
            "outFields": ",".join(field_names),
            "returnGeometry": "false",
            "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE,
            "orderByFields": "ObjectId ASC",
            "f": "json",
        },
    )
    if "error" in payload:
        raise RuntimeError(f"ArcGIS returned an error: {payload['error']}")
    return [feature["attributes"] for feature in payload.get("features", [])]


def sha256(path: Path) -> str:
    """Return a checksum for the completed raw file."""
    # Why: A checksum proves which exact extract was used if the live source
    # changes after this portfolio project is completed.
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_chunk(start_offset: int, page_count: int) -> None:
    """Save a short, restartable sequence of source pages as CSV chunk files."""
    # Why: The source service can be slow. Small restartable batches prevent one
    # temporary network failure from invalidating an otherwise complete download.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    field_names = [field["name"] for field in get_layer_metadata()["fields"]]
    expected_count = get_record_count()
    end_offset = min(start_offset + page_count * PAGE_SIZE, expected_count)

    for offset in range(start_offset, end_offset, PAGE_SIZE):
        page = fetch_page(offset, field_names)
        chunk_file = CHUNKS_DIR / f"part_{offset:06d}.csv"
        # Why: Each chunk has its own header so it can be inspected independently
        # and the final raw CSV can be rebuilt deterministically from the parts.
        with chunk_file.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(output_file, fieldnames=field_names, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(page)
        print(f"Saved {chunk_file.name}: {len(page):,} records")


def assemble_raw_file() -> None:
    """Combine validated chunks into one complete raw CSV and its manifest."""
    # Why: The source count is checked after assembly so an incomplete set of
    # chunks can never be mistaken for the finished source extract.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    field_names = [field["name"] for field in get_layer_metadata()["fields"]]
    expected_count = get_record_count()
    chunk_files = sorted(CHUNKS_DIR.glob("part_*.csv"))
    downloaded_count = 0

    # Why: utf-8-sig opens cleanly in Excel while remaining valid UTF-8 for
    # Python, SQL import tools, and Power BI.
    with RAW_FILE.open("w", newline="", encoding="utf-8-sig") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=field_names, extrasaction="ignore")
        writer.writeheader()
        for chunk_file in chunk_files:
            with chunk_file.open(newline="", encoding="utf-8") as input_file:
                rows = list(csv.DictReader(input_file))
            writer.writerows(rows)
            downloaded_count += len(rows)

    if downloaded_count != expected_count:
        raise RuntimeError(
            f"Assembly incomplete: expected {expected_count:,}, got {downloaded_count:,}."
        )

    # Why: The manifest records the source, schema, time, row count, and checksum
    # alongside the raw file so the later cleaning and database steps are auditable.
    manifest = {
        "dataset_title": "City of Miami 311 Service Requests Since 2015",
        "publisher": "City of Miami, Department of Innovation and Technology, GIS Team",
        "source_layer_url": LAYER_URL,
        "source_item_url": "https://www.arcgis.com/home/item.html?id=7cc10915ede14bb58be312413842a4ce",
        "license": "CC BY 4.0",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": downloaded_count,
        "columns": field_names,
        "file_name": RAW_FILE.name,
        "sha256": sha256(RAW_FILE),
        "notes": (
            "The publisher states this historical layer covers 2022 through "
            "the last available date of August 12, 2024, following the county "
            "311 platform migration. The CSV preserves published attribute values."
        ),
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Saved raw data to: {RAW_FILE}")
    print(f"Saved provenance manifest to: {MANIFEST_FILE}")


if __name__ == "__main__":
    # Why: Explicit modes separate network downloading from local assembly, which
    # makes the process easy to resume and test after an interrupted connection.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-offset", type=int, help="First source record offset to download")
    parser.add_argument("--page-count", type=int, default=20, help="Number of 1,000-row pages to download")
    parser.add_argument("--assemble", action="store_true", help="Combine downloaded chunks into the raw CSV")
    arguments = parser.parse_args()

    if arguments.assemble:
        assemble_raw_file()
    elif arguments.start_offset is not None:
        download_chunk(arguments.start_offset, arguments.page_count)
    else:
        parser.error("use --start-offset NUMBER to download or --assemble to build the raw CSV")
