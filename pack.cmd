call .\venv\Scripts\activate
nuitka --standalone --onefile --output-dir=dist --show-progress --windows-disable-console --enable-plugin=upx core.py