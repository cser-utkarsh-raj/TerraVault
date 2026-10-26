"""Reader routes for published articles, navigation aids, and bookmarks."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, g
from flask_login import login_required, current_user
from app.services.wiki_service import WikiService
from app.utils.helpers import generate_toc, inject_header_ids

wiki_bp = Blueprint('wiki', __name__)

@wiki_bp.route('/<slug>')
def article_view(slug):
    """Renders a dynamic article wiki page with Breadcrumbs, TOC, Reading History, and Bookmarks."""
    # Fetch article and increment views
    article = WikiService.get_article_by_slug(slug, increment_view=True)
    if not article:
        abort(404)
        
    # The stored article body is transformed at render time: headings gain
    # stable anchor IDs and the matching table of contents points to them.
    toc = generate_toc(article.content)
    processed_content = inject_header_ids(article.content)
    
    # Process references list (newline-delimited)
    references = []
    if article.references_data:
        references = [ref.strip() for ref in article.references_data.split('\n') if ref.strip()]
        
    # Related articles
    related = WikiService.get_related_articles(article, limit=3)
    
    # Check bookmark status
    bookmarked = False
    if g.visitor:
        bookmarked = WikiService.is_bookmarked(g.visitor.uuid, article.id)
        # Anonymous history supports a personalized reading trail without
        # requiring account registration for basic discovery.
        WikiService.log_reading_history(g.visitor.uuid, article.id, time_spent=30) # default initial read weight
        
    # Build breadcrumbs list
    breadcrumbs = [
        {'name': 'Home', 'url': url_for('main.home')},
        {'name': article.category.name, 'url': url_for('main.category', slug=article.category.slug)},
        {'name': article.title, 'url': None}
    ]
    
    return render_template(
        'wiki/article.html', 
        article=article,
        content=processed_content,
        toc=toc,
        references=references,
        related=related,
        bookmarked=bookmarked,
        breadcrumbs=breadcrumbs
    )


@wiki_bp.route('/bookmark/<int:article_id>', methods=['POST'])
def bookmark_toggle(article_id):
    """Toggle bookmarks on/off for the current anonymous visitor."""
    if not g.visitor:
        flash('Session not established.', 'danger')
        return redirect(request.referrer or url_for('main.home'))
        
    is_added = WikiService.toggle_bookmark(g.visitor.uuid, article_id)
    if is_added:
        flash('Article added to bookmarks.', 'success')
    else:
        flash('Article removed from bookmarks.', 'info')
        
    # Redirect back to referring page or home
    return redirect(request.referrer or url_for('main.home'))
