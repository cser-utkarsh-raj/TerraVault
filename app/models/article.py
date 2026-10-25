"""Knowledge-domain persistence: articles, classifications, and revisions."""

from datetime import datetime
from app.extensions import db

# This join table lets an article carry many tags and a tag group many articles
# without duplicating tag text on every content row.
article_tags = db.Table('article_tags',
    db.Column('article_id', db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True)
)


class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    
    articles = db.relationship('Article', backref='category', lazy=True)
    
    def __repr__(self):
        return f"<Category {self.name}>"


class Tag(db.Model):
    __tablename__ = 'tags'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    
    def __repr__(self):
        return f"<Tag {self.name}>"


class Article(db.Model):
    """Current editable article state; ArticleVersion stores its history."""
    __tablename__ = 'articles'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    summary = db.Column(db.String(500))
    content = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(255))
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_published = db.Column(db.Boolean, default=False, index=True)
    status = db.Column(db.String(20), default='draft', index=True)  # 'draft', 'published', 'archived'
    is_featured = db.Column(db.Boolean, default=False, index=True)
    views = db.Column(db.Integer, default=0)
    reading_time = db.Column(db.Integer, default=1)  # in minutes
    references_data = db.Column(db.Text)  # stored as raw text/citations (separated by newlines)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Cascading versions/bookmarks/history keeps dependent reader data from
    # becoming orphaned if an article is permanently deleted.
    tags = db.relationship('Tag', secondary=article_tags, backref=db.backref('articles', lazy='dynamic'))
    versions = db.relationship('ArticleVersion', backref='article', cascade="all, delete-orphan", lazy=True)
    bookmarks = db.relationship('Bookmark', backref='article', cascade="all, delete-orphan", lazy=True)
    reading_history = db.relationship('ReadingHistory', backref='article', cascade="all, delete-orphan", lazy=True)
    
    def __repr__(self):
        return f"<Article {self.title}>"


class ArticleVersion(db.Model):
    __tablename__ = 'article_versions'
    
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(500))
    content = db.Column(db.Text, nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    change_summary = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ArticleVersion article_id={self.article_id} version_id={self.id}>"
