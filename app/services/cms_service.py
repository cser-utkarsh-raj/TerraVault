"""Reusable article creation and revision-history operations.

Routes collect request/form data; this service turns it into an Article plus
the ArticleVersion record that preserves editorial provenance.
"""

from app.extensions import db
from app.models.article import Article, ArticleVersion, Category, Tag
from app.models.user import User
from app.models.interaction import Draft
from app.utils.helpers import slugify, calculate_reading_time

class CMSService:
    """Keeps current article state and its recorded revision in sync."""
    @staticmethod
    def get_all_articles_admin():
        """Retrieve all articles, including unpublished, for admin management."""
        return Article.query.order_by(Article.created_at.desc()).all()

    @staticmethod
    def create_article(title, summary, content, category_id, tags_list, author_id, 
                       image_url=None, is_published=False, is_featured=False, references_data=None):
        """Create a new article and compute its reading time."""
        slug = slugify(title)
        
        # Verify unique slug
        base_slug = slug
        counter = 1
        while Article.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
            
        reading_time = calculate_reading_time(content)
        
        article = Article(
            title=title,
            slug=slug,
            summary=summary,
            content=content,
            category_id=category_id,
            author_id=author_id,
            image_url=image_url or 'default_article.jpg',
            is_published=is_published,
            is_featured=is_featured,
            reading_time=reading_time,
            references_data=references_data
        )
        
        # Add tags
        if tags_list:
            for tag_name in tags_list:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                tag_slug = slugify(tag_name)
                tag = Tag.query.filter_by(slug=tag_slug).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=tag_slug)
                    db.session.add(tag)
                article.tags.append(tag)
                
        db.session.add(article)
        db.session.commit()
        
        # Log initial version
        version = ArticleVersion(
            article_id=article.id,
            title=title,
            summary=summary,
            content=content,
            editor_id=author_id,
            change_summary="Initial revision"
        )
        db.session.add(version)
        db.session.commit()
        
        return article

    @staticmethod
    def update_article(article_id, title, summary, content, category_id, tags_list, editor_id, 
                       change_summary="Updated content", image_url=None, is_published=False, 
                       is_featured=False, references_data=None):
        """Update an existing article, log a version history node, and update reading time."""
        article = Article.query.get(article_id)
        if not article:
            return None
            
        # Update details
        article.title = title
        article.summary = summary
        article.content = content
        article.category_id = category_id
        article.is_published = is_published
        article.is_featured = is_featured
        article.reading_time = calculate_reading_time(content)
        article.references_data = references_data
        
        if image_url:
            article.image_url = image_url
            
        # Update tags
        article.tags.clear()
        if tags_list:
            for tag_name in tags_list:
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                tag_slug = slugify(tag_name)
                tag = Tag.query.filter_by(slug=tag_slug).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=tag_slug)
                    db.session.add(tag)
                article.tags.append(tag)
                
        # Generate version record
        version = ArticleVersion(
            article_id=article.id,
            title=title,
            summary=summary,
            content=content,
            editor_id=editor_id,
            change_summary=change_summary
        )
        db.session.add(version)
        db.session.commit()
        
        return article

    @staticmethod
    def delete_article(article_id):
        """Delete an article from the database."""
        article = Article.query.get(article_id)
        if article:
            db.session.delete(article)
            db.session.commit()
            return True
        return False

    @staticmethod
    def create_category(name, description=None):
        """Create a new category."""
        slug = slugify(name)
        if Category.query.filter_by(slug=slug).first():
            return None  # duplicate
        category = Category(name=name, slug=slug, description=description)
        db.session.add(category)
        db.session.commit()
        return category

    @staticmethod
    def update_category(category_id, name, description=None):
        """Update an existing category."""
        category = Category.query.get(category_id)
        if category:
            category.name = name
            category.slug = slugify(name)
            category.description = description
            db.session.commit()
            return category
        return None

    @staticmethod
    def delete_category(category_id):
        """Delete a category."""
        category = Category.query.get(category_id)
        if category:
            db.session.delete(category)
            db.session.commit()
            return True
        return False

    @staticmethod
    def get_cms_dashboard_stats():
        """Retrieve total statistics for the admin dashboard panel."""
        stats = {
            'total_users': User.query.count(),
            'total_articles': Article.query.count(),
            'total_published': Article.query.filter_by(is_published=True).count(),
            'total_drafts': Article.query.filter_by(is_published=False).count(),
            'total_views': db.session.query(db.func.sum(Article.views)).scalar() or 0,
            'total_categories': Category.query.count(),
            'total_tags': Tag.query.count()
        }
        return stats
