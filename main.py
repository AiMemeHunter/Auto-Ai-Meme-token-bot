#!/usr/bin/env python3
"""
Meme Token Hunter — Entry point.
Starts the API server and scanning engine.
"""
import sys
import os

# Help flag support — reads from LocalDb
if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
    help_file = "/Users/m4/Scripts/LocalDb/meme-token-hunter.md"
    if os.path.exists(help_file):
        with open(help_file, "r") as f:
            print(f.read())
    else:
        print("""
Meme Token Hunter v1.0.0
========================
Fully automatic multi-chain meme token scanner with AI-powered rug pull detection.

Usage:
  python main.py              Start the scanner + API server
  python main.py --help       Show this help

Setup:
  1. pip install -r requirements.txt
  2. cp .env.example .env
  3. Edit .env with your RPC URLs and API keys
  4. python main.py

Dashboard: http://localhost:8000
API Docs:  http://localhost:8000/docs
        """)
    sys.exit(0)


def main():
    """Start the Meme Token Hunter."""
    from api.server import run_server
    run_server()


if __name__ == "__main__":
    main()
