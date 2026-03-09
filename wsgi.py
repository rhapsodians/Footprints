"""
wsgi.py — PythonAnywhere entry point for Footprints v2.0

PythonAnywhere looks for a variable called `application` in this file.
Do not rename this file or the `application` variable.
"""
import sys
import os

# ── Add the project directory to Python's path ────────────────────────────────
# Replace 'yourusername' with your actual PythonAnywhere username
project_home = '/home/footprints/footprints2'
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# ── Set a strong secret key via environment variable ─────────────────────────
# Set this in PythonAnywhere's Web tab → Environment variables
# os.environ.setdefault('FP2_SECRET_KEY', 'change-this-to-something-random')

from server import app as application  # noqa
