"""WSGI entry point for production deployment."""
import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.scheduler import init_scheduler

app = create_app()

# Initialize scheduler for background feed fetching in production
if os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true':
    init_scheduler(app)
