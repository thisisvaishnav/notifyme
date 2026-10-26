"""Hugging Face Spaces Entry Point for NotifyMe."""

import os
import sys
import asyncio

# Set environment variables for Hugging Face Spaces port binding
os.environ.setdefault("HOST", "0.0.0.0")
os.environ.setdefault("PORT", "7860")
os.environ.setdefault("WEB_HOST", "0.0.0.0")
os.environ.setdefault("WEB_PORT", "7860")

from main import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
