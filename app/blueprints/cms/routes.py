"""Contributor CMS pages for drafting and editing knowledge articles."""

import os
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.extensions import db
from app.models.article import Article, Category, Tag
from app.services.cms_service import CMSService
from app.blueprints.cms.forms import ArticleForm, CategoryForm

cms_bp = Blueprint('cms', __name__)

def moderator_required(f):
    """Decorator to limit route access to Moderators and Admins."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Login alone is not enough: contributor actions need Moderator or
        # Admin privileges, as exposed by the User model's role helpers.
        if not current_user.is_authenticated or not current_user.is_moderator:
            flash("Access denied. You do not have moderator permissions.", "danger")
            return redirect(url_for('main.home'))
        return f(*args, **kwargs)
    return decorated_function


@cms_bp.route('/')
@login_required
@moderator_required
def dashboard():
    """Renders the CMS Administrative control panel and statistics graphs."""
    stats = CMSService.get_cms_dashboard_stats()
    articles = CMSService.get_all_articles_admin()
    categories = Category.query.all()
    
    return render_template(
        'cms/dashboard.html', 
        stats=stats, 
        articles=articles,
        categories=categories
    )


@cms_bp.route('/article/create', methods=['GET', 'POST'])
@login_required
@moderator_required
def create_article():
    """Create a new encyclopedia article, handles file uploads and tagging."""
    form = ArticleForm()
    
    # Populate Category choices dynamically
    categories = Category.query.all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        filename = None
        # Handle file upload if present
        if form.image.data:
            file = form.image.data
            sec_filename = secure_filename(file.filename)
            filename = f"uploaded_{sec_filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
        # Parse tags
        tags_list = []
        if form.tags.data:
            tags_list = [tag.strip() for tag in form.tags.data.split(',') if tag.strip()]
            
        article = CMSService.create_article(
            title=form.title.data,
            summary=form.summary.data,
            content=form.content.data,
            category_id=form.category_id.data,
            tags_list=tags_list,
            author_id=current_user.id,
            image_url=filename, # if None, CMSService defaults to placeholder
            is_published=form.is_published.data,
            is_featured=form.is_featured.data,
            references_data=form.references_data.data
        )
        
        flash(f"Article '{article.title}' created successfully!", "success")
        if article.is_published:
            return redirect(url_for('wiki.article_view', slug=article.slug))
        return redirect(url_for('cms.dashboard'))
        
    return render_template('cms/article_form.html', form=form, title="Create Article")


@cms_bp.route('/article/edit/<int:article_id>', methods=['GET', 'POST'])
@login_required
@moderator_required
def edit_article(article_id):
    """Edit an existing encyclopedia article, records edit history/versions."""
    article = Article.query.get_or_404(article_id)
    form = ArticleForm()
    
    # Populate categories choice list
    categories = Category.query.all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        filename = None
        # Check if new cover image is uploaded
        if form.image.data:
            file = form.image.data
            sec_filename = secure_filename(file.filename)
            filename = f"uploaded_{sec_filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
        tags_list = []
        if form.tags.data:
            tags_list = [tag.strip() for tag in form.tags.data.split(',') if tag.strip()]
            
        # Update article metadata
        CMSService.update_article(
            article_id=article.id,
            title=form.title.data,
            summary=form.summary.data,
            content=form.content.data,
            category_id=form.category_id.data,
            tags_list=tags_list,
            editor_id=current_user.id,
            change_summary=form.change_summary.data,
            image_url=filename, # only overwrites if not None
            is_published=form.is_published.data,
            is_featured=form.is_featured.data,
            references_data=form.references_data.data
        )
        
        flash("Article updated and new revision saved.", "success")
        if form.is_published.data:
            return redirect(url_for('wiki.article_view', slug=article.slug))
        return redirect(url_for('cms.dashboard'))
        
    elif request.method == 'GET':
        # Prefill form fields
        form.title.data = article.title
        form.summary.data = article.summary
        form.content.data = article.content
        form.category_id.data = article.category_id
        form.tags.data = ", ".join([t.name for t in article.tags])
        form.references_data.data = article.references_data
        form.is_published.data = article.is_published
        form.is_featured.data = article.is_featured
        
    return render_template('cms/article_form.html', form=form, title=f"Edit: {article.title}", article=article)


@cms_bp.route('/article/delete/<int:article_id>', methods=['POST'])
@login_required
@moderator_required
def delete_article(article_id):
    """Delete an article from the database."""
    if CMSService.delete_article(article_id):
        flash("Article deleted successfully.", "success")
    else:
        flash("Error deleting article.", "danger")
    return redirect(url_for('cms.dashboard'))


@cms_bp.route('/categories', methods=['GET', 'POST'])
@login_required
@moderator_required
def categories():
    """List and manage encyclopedia category structure."""
    form = CategoryForm()
    categories_list = Category.query.all()
    
    if form.validate_on_submit():
        category = CMSService.create_category(
            name=form.name.data,
            description=form.description.data
        )
        if category:
            flash(f"Category '{category.name}' created successfully.", "success")
            return redirect(url_for('cms.categories'))
        else:
            flash("Category name already exists.", "warning")
            
    return render_template('cms/categories.html', form=form, categories=categories_list)


@cms_bp.route('/category/delete/<int:category_id>', methods=['POST'])
@login_required
@moderator_required
def delete_category(category_id):
    """Delete a category from the database."""
    # Ensure there are no articles under this category first
    category = Category.query.get_or_404(category_id)
    if category.articles:
        flash(f"Cannot delete category '{category.name}' because it contains active articles.", "danger")
    else:
        CMSService.delete_category(category_id)
        flash("Category deleted successfully.", "success")
    return redirect(url_for('cms.categories'))
