import sys

VERSION = 'v1.0.0.230525'

if __name__ == '__main__':
    if '-v' in sys.argv:
        print(VERSION, file=sys.stdout)
    else:
        import uvicorn
        from app import app

        uvicorn.run(app, host="localhost", port=50000)
