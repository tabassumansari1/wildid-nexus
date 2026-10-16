#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/ and run this again."
  exit 1
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
echo ""
echo "Pugmark is running. Open http://127.0.0.1:8000"
echo ""
exec python manage.py runserver "127.0.0.1:${PORT:-8000}"
