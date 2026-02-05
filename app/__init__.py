import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name=None):
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///news.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # CORS configuration - secure for production
    allowed_origins = os.getenv('CORS_ORIGINS', '*')
    if allowed_origins != '*':
        origins = [o.strip() for o in allowed_origins.split(',')]
    else:
        origins = '*'
    CORS(app, origins=origins)

    # Register blueprints
    from app.routes.feeds import feeds_bp
    from app.routes.articles import articles_bp
    from app.routes.api import api_bp
    from app.routes.topics import topics_bp

    app.register_blueprint(feeds_bp, url_prefix='/feeds')
    app.register_blueprint(articles_bp, url_prefix='/articles')
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(topics_bp, url_prefix='/topics')

    # Create tables
    with app.app_context():
        db.create_all()

    return app
