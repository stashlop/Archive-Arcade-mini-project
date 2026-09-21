import sys
import os

# Add the 'A&A' directory to the Python path so we can import from it
# even though the directory name has a special character '&'
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'A&A'))

# Import the application factory from A&A/app.py
from app import create_app

# Create the globally accessible application instance required by Vercel
app = create_app()
