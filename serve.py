"""Local web launcher: python serve.py [--reload] [--port 8100]"""

import argparse

import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8100)   # 8000 is mojimakrosi's
    ap.add_argument("--reload", action="store_true")
    a = ap.parse_args()
    print(f"\n  QMT → http://{a.host}:{a.port}\n")
    uvicorn.run("qmt.web.app:app", host=a.host, port=a.port, reload=a.reload)
