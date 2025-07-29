"""
This script checks the compatibility of Python packages listed in a requirements.txt file with a
specified version of Python. It queries the PyPI API to fetch the latest versions of the packages,
their release dates, and the minimum required versions that are compatible with the given Python version.

The script can output the results in either Markdown format printed to stdout or CSV format written
to a specified file. It accepts a requirements.txt file generated via pip-compile that includes
package versions and hashes.

Usage:
    python check-python-upgrade.py requirements.txt [-o OUTPUT_FILE] [-t TARGET_PYTHON_VERSION]

Arguments:
    requirements_file (str): The path to the requirements.txt file to be processed.

Optional Arguments:
    -o, --output (str): The output file path where the report will be saved. If a file extension
    is provided, it determines the format (.csv for CSV output, any other for Markdown). If omitted,
    the script prints the Markdown report to stdout.
    -t, --target-python-version (str): The Python version to check package compatibility against (defaults to '3.12').

The report includes the following information for each package:
- Current installed version
- Latest available version
- Release date of the latest version
- Minimum version compatible with the target Python version
- A flag indicating if an update is required to be compatible with the target Python version

If the current package version is not compatible with the specified version of Python, the script marks it in the report, suggesting that an update is required.

Please note that an internet connection is required to fetch the latest package information from the PyPI API.

Example:
    To check against Python 3.12 and output the report in CSV format to 'compatibility_report.csv':
    python check-python-upgrade.py requirements.txt -o compatibility_report.csv

    To print the report to stdout in Markdown format:
    python check-python-upgrade.py requirements.txt

Credits: Taken and modified/updated from https://gist.githubusercontent.com/mgaitan/5bc6d834465e1ab68ed5880a27e4ace4/raw/9d3d96d06b5ea81709f292c912aa1db74b7163b6/check-python-upgrade.py

"""

import argparse
import csv
import os
from datetime import datetime
from packaging.version import parse
from packaging.specifiers import SpecifierSet

import requests


def get_pypi_package_info(package_name: str, current_version, target_python_version):
    url = f"https://pypi.org/pypi/{package_name.strip()}/json"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            print(
                f"Error Requesting Package {package_name} - Code: {response.status_code}"
            )
            print(url)
            return "Unknown", "Unknown Date", "Unknown", "Unknown"
        # Get the latest version
        latest_version = data["info"]["version"]
        # Get the release date of the latest version
        latest_release_date = data["releases"][latest_version][0]["upload_time"]
        # To find the minimum version that is compatible with Python 3.12, you would need to iterate
        # over the releases and check which one specifies that it is compatible.
        compatible_releases = {
            version: release
            for version, release in data["releases"].items()
            for release_info in release
            if release_info.get("requires_python")
            and target_python_version in SpecifierSet(release_info["requires_python"])
        }
        min_version = (
            min(compatible_releases, key=parse) if compatible_releases else "Unknown"
        )
        try:
            requires_python = data["releases"][current_version][0].get(
                "requires_python"
            )
            if requires_python:
                requires_update = target_python_version not in SpecifierSet(
                    requires_python
                )
            else:
                requires_update = "Unknown"
        except (AttributeError, KeyError, IndexError):
            requires_update = "Unknown"

        return latest_version, latest_release_date, min_version, requires_update
    else:
        return "Unknown", "Unknown Date", "Unknown", "Unknown"


# Function to process the requirements.txt file and get the information
def process_requirements(file_path, target_python_version):
    with open(file_path) as file:
        lines = file.readlines()

    requirements_info = []

    for line in lines:
        if "==" in line:
            package_name, current_version = line.strip("\\\n ").split("==")

            if package_name.startswith("#"):
                continue

            if "[" in package_name:
                package_name = package_name.split("[")[0]

            latest_version, latest_release_date, min_version, requires_update = (
                get_pypi_package_info(
                    package_name, current_version, target_python_version
                )
            )
            # We do not have a direct way to get the minimum compatible version with Python 3.12 without internet access
            requirements_info.append(
                {
                    "package": package_name,
                    "current_version": current_version,
                    "latest_version": latest_version,
                    "latest_release_date": latest_release_date,
                    "python_target_min_version": min_version,
                    "requires_update": requires_update,
                }
            )

    return requirements_info


def generate_markdown_report(requirements_info, target_python_version, file=None):
    headers = [
        "Package",
        "Current Version",
        "Latest Version",
        "Latest Release Date",
        f"Min Version for Python {target_python_version}",
        "Requires Update",
    ]
    rows = []
    for req_info in requirements_info:
        rows.append(
            [
                req_info["package"],
                req_info["current_version"],
                req_info["latest_version"],
                req_info["latest_release_date"],
                req_info["python_target_min_version"],
                req_info["requires_update"],
            ]
        )

    sort_order = {"True": 0, "Unknown": 1, "False": 3}

    rows = sorted(rows, key=lambda x: sort_order.get(x[5], 2))

    # Determine the maximum width for each column
    column_widths = [max(len(str(row[i])) for row in rows) for i in range(len(headers))]
    # Create the header row
    header_row = " | ".join(
        header.ljust(column_widths[i]) for i, header in enumerate(headers)
    )
    # Create the separator row
    separator_row = " | ".join("-" * column_widths[i] for i, _ in enumerate(headers))
    # Create the data rows
    data_rows = [
        " | ".join(str(row[i]).ljust(column_widths[i]) for i in range(len(headers)))
        for row in rows
    ]

    # Add Title and Small Summary

    markdown_header = f"# Compatability Report for Python {target_python_version} \n\n"

    now = datetime.now()
    markdown_header += f"This Report was Generated on the {now.strftime('%A, %d %B %Y, %I:%M %p')} \n\n"

    # Combine all rows into a single string
    markdown_output = markdown_header + "\n".join(
        [header_row, separator_row, *data_rows]
    )

    # Print to stdout or write to a file
    if file:
        with open(file, "w") as f:
            f.write(markdown_output)
    else:
        print(markdown_output)


def generate_csv_report(requirements_info, target_python_version, filename):
    fieldnames = [
        "Package",
        "Current Version",
        "Latest Version",
        "Latest Release Date",
        f"Min Version for Python {target_python_version}",
        "Requires Update",
    ]

    with open(filename, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for req_info in requirements_info:
            row = {
                "Package": req_info["package"],
                "Current Version": req_info["current_version"],
                "Latest Version": req_info["latest_version"],
                "Latest Release Date": req_info["latest_release_date"],
                f"Min Version for Python {target_python_version}": req_info[
                    "python_target_min_version"
                ],
                "Requires Update": req_info["requires_update"],
            }
            writer.writerow(row)


# Set up the argument parser
parser = argparse.ArgumentParser(
    description="Check package compatibility with a specified version of Python."
)
parser.add_argument(
    "requirements_file", type=str, help="Path to the requirements.txt file."
)
parser.add_argument(
    "-o",
    "--output",
    type=str,
    help="Output file name. Format is determined by file extension (.csv for CSV, otherwise Markdown).",
)
parser.add_argument(
    "-t",
    "--target-python-version",
    type=str,
    default="3.12",
    help='Target Python version for compatibility check. Default is "3.12".',
)

args = parser.parse_args()

# Process the requirements file
requirements_info = process_requirements(
    args.requirements_file, args.target_python_version
)
if args.output:
    file_ext = os.path.splitext(args.output)[-1]
    if file_ext.lower() == ".csv":
        generate_csv_report(requirements_info, args.target_python_version, args.output)
    else:
        generate_markdown_report(
            requirements_info, args.target_python_version, args.output
        )
else:
    generate_markdown_report(requirements_info, args.target_python_version)
