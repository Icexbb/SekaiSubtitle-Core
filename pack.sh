source venv/bin/activate
nuitka3 --standalone --onefile --output-dir=dist --show-progress --enable-plugin=upx core.py