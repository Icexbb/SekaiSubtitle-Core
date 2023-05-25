call .\venv\Scripts\activate
nuitka --standalone --onefile --output-dir=dist --show-progress --enable-plugin=upx core.py