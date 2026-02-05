from datetime import datetime
from app import db


class Article(db.Model):
    __tablename__ = 'articles'

    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.Integer, db.ForeignKey('feeds.id'), nullable=False)
    guid = db.Column(db.String(500), unique=True, nullable=False)
    title = db.Column(db.String(500), nullable=False)
    link = db.Column(db.String(500))
    description = db.Column(db.Text)
    content = db.Column(db.Text)
    author = db.Column(db.String(255))
    thumbnail = db.Column(db.String(500))
    published_at = db.Column(db.DateTime)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    is_starred = db.Column(db.Boolean, default=False)

    # LLM analysis fields
    llm_category = db.Column(db.String(100), index=True)  # Politics, Technology, etc.
    llm_sentiment = db.Column(db.String(20))  # positive, negative, neutral
    analysis_status = db.Column(db.String(20), index=True, default='pending')  # pending, processing, completed, failed
    analyzed_at = db.Column(db.DateTime)
    llm_metadata = db.Column(db.JSON)  # entities, topics, key_facts
    content_hash = db.Column(db.String(64))  # SHA-256 hash to detect content changes

    # Index for faster queries
    __table_args__ = (
        db.Index('idx_feed_published', 'feed_id', 'published_at'),
        db.Index('idx_published', 'published_at'),
        db.Index('idx_analysis_status', 'analysis_status'),
    )

    def to_dict(self, include_content=False, include_llm=False):
        data = {
            'id': self.id,
            'feed_id': self.feed_id,
            'feed_name': self.feed.name if self.feed else None,
            'guid': self.guid,
            'title': self.title,
            'link': self.link,
            'description': self.description,
            'author': self.author,
            'thumbnail': self.thumbnail,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'fetched_at': self.fetched_at.isoformat() if self.fetched_at else None,
            'is_read': self.is_read,
            'is_starred': self.is_starred,
        }
        if include_content:
            data['content'] = self.content
        if include_llm:
            data['llm_category'] = self.llm_category
            data['llm_sentiment'] = self.llm_sentiment
            data['analysis_status'] = self.analysis_status
            data['analyzed_at'] = self.analyzed_at.isoformat() if self.analyzed_at else None
            data['llm_metadata'] = self.llm_metadata
        return data

    def __repr__(self):
        return f'<Article {self.title[:50]}>'
