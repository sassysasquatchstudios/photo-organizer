#!/usr/bin/env bash
# Run this on a Mac to produce Photo Organizer.app
# Requirements: pip install -r requirements.txt

pyinstaller \
  --windowed \
  --onefile \
  --name "Photo Organizer" \
  --hidden-import pillow_heif \
  organize.py

echo ""
echo "Done — dist/Photo Organizer.app"
echo "First launch on another Mac: right-click → Open to bypass Gatekeeper."
