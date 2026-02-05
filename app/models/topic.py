from datetime import datetime
from app import db


class Topic(db.Model):
    """Represents a clustered news topic with multiple related articles."""
    __tablename__ = 'topics'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(500), nullable=False)
    summary = db.Column(db.Text)
    keywords = db.Column(db.Text)  # Comma-separated keywords
    thumbnail = db.Column(db.String(500))
    article_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # LLM-generated fields
    llm_summary = db.Column(db.Text)  # AI-generated summary
    category = db.Column(db.String(100), index=True)  # Politics, Technology, etc.
    importance_score = db.Column(db.Float, default=0.5)  # 0.0 to 1.0

    # Relationship to articles
    articles = db.relationship('ArticleTopic', backref='topic', lazy='dynamic', cascade='all, delete-orphan')

    def to_dict(self, include_articles=False):
        data = {
            'id': self.id,
            'title': self.title,
            'summary': self.llm_summary or self.summary,  # Prefer LLM summary if available
            'keywords': self.keywords.split(',') if self.keywords else [],
            'thumbnail': self.thumbnail,
            'article_count': self.article_count,
            'category': self.category,
            'importance_score': self.importance_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_articles:
            data['articles'] = [at.article.to_dict() for at in self.articles.limit(10).all()]
        return data


class ArticleTopic(db.Model):
    """Links articles to topics."""
    __tablename__ = 'article_topics'

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topics.id'), nullable=False)
    relevance_score = db.Column(db.Float, default=1.0)

    article = db.relationship('Article', backref='topic_links')

    __table_args__ = (
        db.UniqueConstraint('article_id', 'topic_id', name='unique_article_topic'),
    )
