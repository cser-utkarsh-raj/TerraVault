from sqlalchemy import or_
"""Reader-facing article discovery and interaction helpers."""

from app.extensions import db
from app.models.article import Article, Category, Tag
from app.models.interaction import Bookmark, ReadingHistory

class WikiService:
    """Queries published knowledge and records non-editor reader actions."""
    @staticmethod
    def get_article_by_slug(slug, increment_view=True):
        """Retrieve a published article by slug and optionally increment the view count."""
        article = Article.query.filter_by(slug=slug, is_published=True).first()
        if article and increment_view:
            article.views += 1
            db.session.commit()
        return article

    @staticmethod
    def get_all_published_articles(category_id=None, tag_id=None, limit=None):
        """Retrieve all published articles, optionally filtered by category or tag."""
        query = Article.query.filter_by(is_published=True)
        
        if category_id:
            query = query.filter_by(category_id=category_id)
        if tag_id:
            query = query.join(Article.tags).filter(Tag.id == tag_id)
            
        # Order by newest
        query = query.order_by(Article.created_at.desc())
        
        if limit:
            query = query.limit(limit)
            
        return query.all()

    @staticmethod
    def get_featured_articles():
        """Get all featured articles."""
        return Article.query.filter_by(is_published=True, is_featured=True).order_by(Article.created_at.desc()).all()

    @staticmethod
    def get_related_articles(article, limit=3):
        """Find articles under the same category or sharing tags, excluding the current article."""
        if not article:
            return []
        
        # Primary filter: same category, excluding current article
        query = Article.query.filter(
            Article.is_published == True,
            Article.category_id == article.category_id,
            Article.id != article.id
        )
        
        # If we have tags, we could also order or filter by tags, but a simple same-category search is clean
        related = query.order_by(Article.views.desc()).limit(limit).all()
        return related

    @staticmethod
    def search_articles(query_string):
        """Search published articles by title, summary, or content."""
        if not query_string:
            return []
        search_pattern = f"%{query_string}%"
        return Article.query.filter(
            Article.is_published == True
        ).filter(
            or_(
                Article.title.like(search_pattern),
                Article.summary.like(search_pattern),
                Article.content.like(search_pattern)
            )
        ).all()

    @staticmethod
    def is_bookmarked(visitor_uuid, article_id):
        """Check if an article is bookmarked by a visitor."""
        if not visitor_uuid:
            return False
        return Bookmark.query.filter_by(visitor_uuid=visitor_uuid, article_id=article_id).first() is not None

    @staticmethod
    def toggle_bookmark(visitor_uuid, article_id):
        """Bookmark or unbookmark an article."""
        bookmark = Bookmark.query.filter_by(visitor_uuid=visitor_uuid, article_id=article_id).first()
        if bookmark:
            db.session.delete(bookmark)
            db.session.commit()
            return False  # Unbookmarked
        else:
            bookmark = Bookmark(visitor_uuid=visitor_uuid, article_id=article_id)
            db.session.add(bookmark)
            db.session.commit()
            return True  # Bookmarked

    @staticmethod
    def log_reading_history(visitor_uuid, article_id, time_spent=0):
        """Record or update reading history for a visitor and article."""
        if not visitor_uuid:
            return
        
        history = ReadingHistory.query.filter_by(visitor_uuid=visitor_uuid, article_id=article_id).first()
        if history:
            history.time_spent += time_spent
        else:
            history = ReadingHistory(visitor_uuid=visitor_uuid, article_id=article_id, time_spent=time_spent)
            db.session.add(history)
            
        db.session.commit()

    @staticmethod
    def get_reading_history(visitor_uuid, limit=10):
        """Get the visitor's reading history list."""
        return ReadingHistory.query.filter_by(visitor_uuid=visitor_uuid).order_by(ReadingHistory.last_viewed.desc()).limit(limit).all()

    @staticmethod
    def get_user_bookmarks(visitor_uuid):
        """Get all bookmarks for a visitor."""
        return Bookmark.query.filter_by(visitor_uuid=visitor_uuid).order_by(Bookmark.created_at.desc()).all()

    @staticmethod
    def get_all_categories():
        """Retrieve all categories."""
        return Category.query.all()

    @staticmethod
    def get_category_by_slug(slug):
        """Retrieve a single category by slug."""
        return Category.query.filter_by(slug=slug).first()

    @staticmethod
    def get_all_tags():
        """Retrieve all tags."""
        return Tag.query.all()
