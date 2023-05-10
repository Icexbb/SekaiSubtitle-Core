source venv/bin/activate
nuitka --standalone --onefile --output-dir=dist --show-progress --macos-disable-console  --enable-plugin=upx core.py