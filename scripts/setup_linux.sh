#!/usr/bin/env bash
# Sets up (if needed) and launches the hostel booking Django project on Linux/macOS.
# Usage: bash setup_and_run_linux.sh   (or: chmod +x setup_and_run_linux.sh && ./setup_and_run_linux.sh)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DEV_DIR="$PROJECT_ROOT/dev"
VENV_DIR="$DEV_DIR/venv"
PY="$VENV_DIR/bin/python"

if [ ! -f "$PY" ]; then
    echo "No virtual environment found, creating one at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

echo "Installing dependencies..."
"$PY" -m pip install --upgrade pip --quiet
"$PY" -m pip install -r "$DEV_DIR/requirements.txt" --quiet

cd "$DEV_DIR"

echo "Applying database migrations..."
"$PY" manage.py migrate

echo "Setting up RBAC roles (Admin/Staff/Student groups)..."
"$PY" manage.py setup_roles

echo ""
echo "Starting development server at http://127.0.0.1:8000/ (Ctrl+C to stop)"
"$PY" manage.py runserver
