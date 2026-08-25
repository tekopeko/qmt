"""Local web launcher: python serve.py [--reload] [--port 8100] [--force]"""

import argparse
import socket
import subprocess
import sys

import uvicorn


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8100)   # 8000 is mojimakrosi's
    ap.add_argument("--reload", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="kill whatever currently holds the port, then start")
    a = ap.parse_args()

    if port_in_use(a.host, a.port):
        if a.force:
            subprocess.run(f"lsof -ti:{a.port} | xargs kill", shell=True)
            import time
            time.sleep(1)
        else:
            sys.exit(
                f"Port {a.port} je zauzet (vjerojatno stara instanca).\n"
                f"  oslobodi ga:   lsof -ti:{a.port} | xargs kill\n"
                f"  ili pokreni:   python serve.py --force"
            )

    print(f"\n  QMT → http://{a.host}:{a.port}\n")
    uvicorn.run("qmt.web.app:app", host=a.host, port=a.port, reload=a.reload)
