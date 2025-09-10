#!/usr/bin/env bash
set -e

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

# Activate the venv
source .venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy .env.example to .env if needed
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "Copied .env.example to .env"
fi

# Create required directories
mkdir -p data/raw data/chroma logs

echo "Setup complete."
