# Run this on Windows to produce Photo Organizer.exe
# Requirements: pip install -r requirements.txt

pyinstaller `
  --windowed `
  --onefile `
  --name "Photo Organizer" `
  --hidden-import pillow_heif `
  organize.py

Write-Host "`nDone — dist\Photo Organizer.exe" -ForegroundColor Green
