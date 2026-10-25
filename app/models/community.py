"""Anonymous community, moderation, voting, and analytics data models."""

from datetime import datetime
from app.extensions import db

class AnonymousVisitor(db.Model):
    __tablename__ = 'anonymous_visitors'
    
    uuid = db.Column(db.String(36), primary_key=True)
    display_name = db.Column(db.String(100), nullable=False)
    avatar_color = db.Column(db.String(20), nullable=False)
    is_banned = db.Column(db.Boolean, default=False)
    ban_expires = db.Column(db.DateTime, nullable=True)
    ban_reason = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_seen_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    discussions = db.relationship('Discussion', backref='visitor', lazy=True)
    comments = db.relationship('Comment', backref='visitor', lazy=True)
    votes = db.relationship('Vote', backref='visitor', lazy=True)
    reports = db.relationship('Report', backref='visitor', lazy=True)
    bookmarks = db.relationship('Bookmark', backref='visitor', cascade="all, delete-orphan", lazy=True)
    reading_history = db.relationship('ReadingHistory', backref='visitor', cascade="all, delete-orphan", lazy=True)


class Community(db.Model):
    __tablename__ = 'communities'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    description = db.Column(db.Text)
    icon = db.Column(db.String(100))
    
    discussions = db.relationship('Discussion', backref='community', lazy=True)


class Discussion(db.Model):
    __tablename__ = 'discussions'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    community_id = db.Column(db.Integer, db.ForeignKey('communities.id', ondelete='CASCADE'), nullable=False)
    visitor_uuid = db.Column(db.String(36), db.ForeignKey('anonymous_visitors.uuid', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(20), default='published')  # 'published', 'removed', 'locked'
    removed_reason = db.Column(db.String(255), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    views = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    comments = db.relationship('Comment', backref='discussion', cascade="all, delete-orphan", lazy=True)
    votes = db.relationship('Vote', backref='discussion', cascade="all, delete-orphan", lazy=True)
    reports = db.relationship('Report', backref='discussion', cascade="all, delete-orphan", lazy=True)


class Comment(db.Model):
    __tablename__ = 'comments'
    
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    discussion_id = db.Column(db.Integer, db.ForeignKey('discussions.id', ondelete='CASCADE'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=True)
    visitor_uuid = db.Column(db.String(36), db.ForeignKey('anonymous_visitors.uuid', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(20), default='published')  # 'published', 'removed'
    removed_reason = db.Column(db.String(255), nullable=True)
    removed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Self-referential relationship for nested replies
    replies = db.relationship('Comment', backref=db.backref('parent', remote_side=[id]), cascade="all, delete-orphan", lazy=True)
    votes = db.relationship('Vote', backref='comment', cascade="all, delete-orphan", lazy=True)
    reports = db.relationship('Report', backref='comment', cascade="all, delete-orphan", lazy=True)


class Vote(db.Model):
    __tablename__ = 'votes'
    
    id = db.Column(db.Integer, primary_key=True)
    visitor_uuid = db.Column(db.String(36), db.ForeignKey('anonymous_visitors.uuid', ondelete='CASCADE'), nullable=False)
    discussion_id = db.Column(db.Integer, db.ForeignKey('discussions.id', ondelete='CASCADE'), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=True)
    value = db.Column(db.Integer, nullable=False)  # 1 (upvote) or -1 (downvote)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint per visitor per discussion or comment
    __table_args__ = (
        db.UniqueConstraint('visitor_uuid', 'discussion_id', name='_visitor_discussion_vote_uc'),
        db.UniqueConstraint('visitor_uuid', 'comment_id', name='_visitor_comment_vote_uc'),
    )


class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    visitor_uuid = db.Column(db.String(36), db.ForeignKey('anonymous_visitors.uuid', ondelete='CASCADE'), nullable=False)
    discussion_id = db.Column(db.Integer, db.ForeignKey('discussions.id', ondelete='CASCADE'), nullable=True)
    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id', ondelete='CASCADE'), nullable=True)
    reason = db.Column(db.String(50), nullable=False)  # 'Spam', 'Harassment', 'Misinformation', 'NSFW', 'Other'
    details = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='pending')  # 'pending', 'reviewed', 'dismissed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class NewsletterSubscriber(db.Model):
    __tablename__ = 'newsletter_subscribers'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    interest_category = db.Column(db.String(100), nullable=True)
    source = db.Column(db.String(50), default='homepage')
    signup_date = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(150), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text, nullable=True)


class PageViewMetric(db.Model):
    __tablename__ = 'page_view_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(255), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), nullable=True)
    visitor_uuid = db.Column(db.String(36), db.ForeignKey('anonymous_visitors.uuid', ondelete='SET NULL'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class SearchMetric(db.Model):
    __tablename__ = 'search_metrics'
    
    id = db.Column(db.Integer, primary_key=True)
    query = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
