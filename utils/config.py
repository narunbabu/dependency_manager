# utils/config.py

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
dotenv_path = Path(__file__).parent.parent / '.env'  # Adjust the path as needed
load_dotenv(dotenv_path=dotenv_path)

# Retrieve the project path
PROJECT_PATH = Path(os.getenv('PROJECT_PATH', './default_project')).resolve()
ANTHROPIC_API = os.getenv('ANTHROPIC_API')

print(f"[DEBUG] Loaded PROJECT_PATH: {PROJECT_PATH}")
