# check-python-upgrade.py

A script to check the compatibility of Python packages in a `requirements.txt` file with a specified Python version. It helps identify which packages need to be updated for compatibility with future or specific Python releases, such as Python 3.12.

## Features

- Reads a `requirements.txt` file (preferably generated via `pip-compile`).
- Fetches the latest package info from PyPI, including version and release date.
- Determines the minimum version of each package compatible with a specified Python version.
- Reports packages that require updating for compatibility.
- Outputs a report in Markdown (stdout) or CSV (to a file).

## Usage

```bash
python main.py requirements.txt
