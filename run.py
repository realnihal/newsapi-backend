#!/usr/bin/env python3
"""Entry point for the NewsAPI Flask application."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app import create_app
from app.scheduler import init_scheduler, shutdown_scheduler

app = create_app()

# Initialize scheduler for background feed fetching
if os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true':
    init_scheduler(app)

if __name__ == '__main__':
    try:
        port = int(os.getenv('PORT', 5000))
        debug = os.getenv('FLASK_ENV') == 'development'
        app.run(host='0.0.0.0', port=port, debug=debug)
    finally:
        shutdown_scheduler()
