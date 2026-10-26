"""Public discovery routes: home, search, categories, tags, and health."""

from flask import Blueprint, render_template, request, jsonify, current_app, Response, send_from_directory, flash, redirect, url_for
from app.services.wiki_service import WikiService
from app.models.article import Category, Tag, Article
from app.models.community import Community, Discussion, SearchMetric, NewsletterSubscriber, AuditLog
from app.extensions import db
import os

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """Renders the main catalog home page, featured articles, recent publications, and communities."""
    featured = WikiService.get_featured_articles()
    recent = WikiService.get_all_published_articles(limit=6)
    categories = WikiService.get_all_categories()
    
    # Load communities and popular discussions
    communities = Community.query.all()
    popular_discussions = Discussion.query.filter(Discussion.status != 'removed').order_by(Discussion.views.desc()).limit(5).all()
    
    # Discussions persist individual votes. Calculate the display-only net
    # score here rather than adding a second, potentially stale score column.
    from app.models.community import Vote
    for disc in popular_discussions:
        upvotes = Vote.query.filter_by(discussion_id=disc.id, value=1).count()
        downvotes = Vote.query.filter_by(discussion_id=disc.id, value=-1).count()
        disc.score = upvotes - downvotes
    
    return render_template(
        'main/home.html', 
        featured=featured, 
        recent=recent, 
        categories=categories,
        communities=communities,
        popular_discussions=popular_discussions
    )


@main_bp.route('/search')
def search():
    """Global search across articles and community discussions."""
    query = request.args.get('q', '').strip()
    results = []
    discussion_results = []
    
    if query:
        # Search wiki articles
        results = WikiService.search_articles(query)
        
        # Search community discussions
        discussion_results = Discussion.query.filter(
            Discussion.status != 'removed'
        ).filter(
            Discussion.title.like(f"%{query}%") | Discussion.content.like(f"%{query}%")
        ).all()
        
        # Inject scores
        from app.models.community import Vote
        for disc in discussion_results:
            upvotes = Vote.query.filter_by(discussion_id=disc.id, value=1).count()
            downvotes = Vote.query.filter_by(discussion_id=disc.id, value=-1).count()
            disc.score = upvotes - downvotes
            
        # Search logs are independent from article results so administrators can
        # learn demand even when a query returns nothing useful.
        search_log = SearchMetric(query=query)
        db.session.add(search_log)
        db.session.commit()
        
    return render_template(
        'main/search.html', 
        query=query, 
        results=results, 
        discussion_results=discussion_results
    )


@main_bp.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    """Anonymously subscribe to the newsletter."""
    email = request.form.get('email', '').strip()
    interest = request.form.get('interest', 'General')
    source = request.form.get('source', 'homepage')
    
    if not email:
        flash("Email is required for newsletter subscription.", "danger")
        return redirect(request.referrer or url_for('main.home'))
        
    existing = NewsletterSubscriber.query.filter_by(email=email).first()
    if existing:
        flash("You are already subscribed to the TerraVault newsletter!", "info")
    else:
        sub = NewsletterSubscriber(
            email=email,
            interest_category=interest,
            source=source
        )
        db.session.add(sub)
        
        # Log audit entry
        audit = AuditLog(action="Newsletter Signup", details=f"New subscriber: {email} (Category interest: {interest})")
        db.session.add(audit)
        
        db.session.commit()
        flash("Thank you for subscribing to the TerraVault newsletter!", "success")
        
    return redirect(request.referrer or url_for('main.home'))


@main_bp.route('/category/<slug>')
def category(slug):
    """Renders articles filtered by a specific category."""
    cat = Category.query.filter_by(slug=slug).first_or_404()
    articles = WikiService.get_all_published_articles(category_id=cat.id)
    return render_template('main/category.html', category=cat, articles=articles)


@main_bp.route('/tag/<slug>')
def tag(slug):
    """Renders articles filtered by a specific tag."""
    tag_obj = Tag.query.filter_by(slug=slug).first_or_404()
    articles = WikiService.get_all_published_articles(tag_id=tag_obj.id)
    return render_template('main/tag.html', tag=tag_obj, articles=articles)


@main_bp.route('/health')
def health():
    """Health check endpoint for Render/hosting platforms."""
    db_status = "healthy"
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        
    return jsonify({
        'status': 'healthy' if db_status == 'healthy' else 'unhealthy',
        'database': db_status,
        'app': 'healthy'
    }), 200 if db_status == "healthy" else 500


@main_bp.route('/robots.txt')
def robots():
    """SEO robots.txt crawling configuration."""
    content = "User-agent: *\nAllow: /\nDisallow: /admin/\nSitemap: " + request.url_root + "sitemap.xml"
    return content, 200, {'Content-Type': 'text/plain'}


@main_bp.route('/sitemap.xml')
def sitemap():
    """SEO XML sitemap of all active articles."""
    pages = []
    pages.append({'loc': request.url_root, 'changefreq': 'daily', 'priority': '1.0'})
    
    try:
        articles = Article.query.filter_by(is_published=True).all()
        for art in articles:
            loc = request.url_root + 'wiki/' + art.slug
            pages.append({'loc': loc, 'changefreq': 'weekly', 'priority': '0.8'})
            
        communities = Community.query.all()
        for comm in communities:
            loc = request.url_root + 'c/' + comm.slug
            pages.append({'loc': loc, 'changefreq': 'daily', 'priority': '0.7'})
    except Exception:
        pass
        
    sitemap_xml = render_template('main/sitemap.xml', pages=pages)
    return Response(sitemap_xml, mimetype='application/xml')


@main_bp.route('/favicon.ico')
def favicon():
    """Serve favicon shortcut icons directly from static folder."""
    return send_from_directory(current_app.static_folder, 'favicon.ico', mimetype='image/vnd.microsoft.icon')
