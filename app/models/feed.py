from datetime import datetime
from app import db


class Feed(db.Model):
    __tablename__ = 'feeds'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), unique=True, nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(100))
    is_active = db.Column(db.Boolean, default=True)
    last_fetched = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    articles = db.relationship('Article', backref='feed', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'description': self.description,
            'category': self.category,
            'is_active': self.is_active,
            'last_fetched': self.last_fetched.isoformat() if self.last_fetched else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'article_count': self.articles.count()
        }

    def __repr__(self):
        return f'<Feed {self.name}>'
