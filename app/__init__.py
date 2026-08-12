import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template
from flask_talisman import Talisman
from flask_compress import Compress
from whitenoise import WhiteNoise
from app.config import config_by_name
from app.extensions import db, migrate, login_manager, csrf

def create_app(config_name=None):
    """Application Factory Pattern."""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
        
    # Set explicit root paths for template and static folders
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    template_dir = os.path.join(root_dir, 'templates')
    static_dir = os.path.join(root_dir, 'static')
        
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    app.config.from_object(config_by_name.get(config_name, config_by_name['default']))
    
    # Initialize Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    
    # Create upload directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Setup logging
    setup_logging(app)
    
    # Register User Loader for Flask-Login
    from app.models.user import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
        
    # Register blueprints
    register_blueprints(app)
    
    # Register global error handlers
    register_error_handlers(app)
    
    # Global context processors and custom Jinja filters
    register_context_processors(app)
    
    # Custom Content Security Policy supporting Bootstrap 5 and FontAwesome CDNs plus inline scripts
    csp = {
        'default-src': [
            '\'self\'',
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
        ],
        'script-src': [
            '\'self\'',
            '\'unsafe-inline\'', # Required for Chart.js & Dark Mode toggler scripts
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
        ],
        'style-src': [
            '\'self\'',
            '\'unsafe-inline\'',
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
            'https://fonts.googleapis.com',
        ],
        'font-src': [
            '\'self\'',
            'https://fonts.gstatic.com',
            'https://cdnjs.cloudflare.com',
        ],
        'img-src': [
            '\'self\'',
            'data:',
            'https://images.unsplash.com',
            'https://upload.wikimedia.org',
        ]
    }
    
    # Enforce Talisman security headers (HTTP Strict Transport Security, XSS protections, frame guards)
    # Require HTTPS only if in production mode
    is_prod = (config_name == 'production' or os.environ.get('FLASK_ENV') == 'production')
    Talisman(app, content_security_policy=csp, force_https=is_prod)
    
    # Enable Gzip and Brotli compression for server responses
    Compress(app)
    
    # Wrap WSGI pipeline with WhiteNoise to serve static assets with far-future caching headers
    app.wsgi_app = WhiteNoise(app.wsgi_app, root=static_dir, prefix='static/')
    
    # Register anonymous visitor cookies & metrics logging
    register_request_handlers(app)
    
    with app.app_context():
        # Ensure database tables exist in production
        db.create_all()
        
        # Self-healing check for Roles, Admin user, and Communities
        from app.models.user import User, Role
        from app.models.community import Community
        
        # Seed basic roles if not present
        if not Role.query.filter_by(name='Admin').first():
            admin_role = Role(name='Admin', description='Global platform administrator')
            mod_role = Role(name='Moderator', description='Community moderator')
            user_role = Role(name='User', description='Standard registered user')
            db.session.add_all([admin_role, mod_role, user_role])
            db.session.commit()
            
        # Seed admin user if not present
        admin_role = Role.query.filter_by(name='Admin').first()
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user and admin_role:
            admin_user = User(
                username='admin',
                email='admin@terravault.com',
                role_id=admin_role.id,
                is_verified=True
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            
            # Create corresponding Profile
            from app.models.user import Profile
            profile = Profile(user=admin_user)
            db.session.add(profile)
            db.session.commit()
            
        # Seed basic communities if not present
        if not Community.query.first():
            communities_data = [
                {'name': 'History', 'slug': 'history', 'description': 'Discuss ancient records, historical milestones, and humanity\'s lineage.', 'icon': 'fa-monument'},
                {'name': 'Mythology', 'slug': 'mythology', 'description': 'Debate ancient legends, cryptids, folklore, and mythic civilizations.', 'icon': 'fa-dragon'},
                {'name': 'Disasters', 'slug': 'disasters', 'description': 'Revisit historical cataclysms, fires, volcanic eruptions, and nuclear accidents.', 'icon': 'fa-burst'},
                {'name': 'Environment', 'slug': 'environment', 'description': 'Share news and insights on Earth\'s ecosystems, climate change, and geographies.', 'icon': 'fa-leaf'},
                {'name': 'Cosmology', 'slug': 'cosmology', 'description': 'Explore stellar horizons: black holes, astronomical anomalies, and deep space.', 'icon': 'fa-meteor'},
                {'name': 'Archaeology', 'slug': 'archaeology', 'description': 'Discuss monuments, megaliths, ancient cities, and archaeological digs.', 'icon': 'fa-compass'}
            ]
            for comm in communities_data:
                c = Community(name=comm['name'], slug=comm['slug'], description=comm['description'], icon=comm['icon'])
                db.session.add(c)
            db.session.commit()

        # Seed articles if not present
        from app.models.article import Article, Category
        if not Article.query.first() and admin_user:
            import json
            import re
            json_path = os.path.join(root_dir, 'articles.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                cleaned = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                try:
                    raw_articles = json.loads(cleaned)
                    from app.services.cms_service import CMSService
                    categories_dict = {}
                    for cat_data in Category.query.all():
                        categories_dict[cat_data.slug] = cat_data
                    
                    for art in raw_articles:
                        cat_slug = art.get('category')
                        category = categories_dict.get(cat_slug)
                        if not category:
                            category = Category(name=cat_slug.capitalize(), slug=cat_slug, description=f"{cat_slug.capitalize()} articles")
                            db.session.add(category)
                            db.session.commit()
                            categories_dict[cat_slug] = category
                            
                        ref_list = [
                            "Encyclopaedia Britannica, Online Edition.",
                            "National Geographic Historical Archives.",
                            f"Scientific Reports on {art.get('title')} (2024)."
                        ]
                        ref_data = "\n".join(ref_list)
                        
                        CMSService.create_article(
                            title=art.get('title'),
                            summary=art.get('summary'),
                            content=art.get('content'),
                            category_id=category.id,
                            tags_list=[category.name.split()[0]],
                            author_id=admin_user.id,
                            image_url=art.get('img'),
                            is_published=True,
                            is_featured=(art.get('slug') in ['atlantis', 'chernobyl', 'black-holes']),
                            references_data=ref_data
                        )
                except Exception as e:
                    print(f"Self-healing articles seed failed: {e}")
                    
    return app


def register_request_handlers(app):
    import uuid
    import hashlib
    from datetime import datetime
    from flask import g, request
    from app.models.community import AnonymousVisitor, PageViewMetric
    from app.models.article import Article

    @app.before_request
    def before_request_func():
        # Skip static assets, health check, robots.txt, sitemap, favicon
        path = request.path
        if (path.startswith('/static/') or 
            path == '/health' or 
            path == '/favicon.ico' or 
            path == '/robots.txt' or 
            path == '/sitemap.xml'):
            g.visitor = None
            return
            
        anon_cookie = request.cookies.get('anon_explorer_id')
        cookie_to_set = None
        if not anon_cookie:
            anon_cookie = str(uuid.uuid4())
            g.set_anon_cookie = anon_cookie
            cookie_to_set = anon_cookie
        else:
            g.set_anon_cookie = None
            
        # Fetch or create AnonymousVisitor
        visitor = AnonymousVisitor.query.filter_by(uuid=anon_cookie).first()
        if not visitor:
            # Generate name based on UUID prefix
            short_id = anon_cookie[:4].upper()
            display_name = f"Anonymous Explorer #{short_id}"
            
            # Generate colorful avatar background based on hash
            h = int(hashlib.md5(anon_cookie.encode('utf-8')).hexdigest(), 16)
            hue = h % 360
            avatar_color = f"hsl({hue}, 70%, 45%)"
            
            visitor = AnonymousVisitor(
                uuid=anon_cookie,
                display_name=display_name,
                avatar_color=avatar_color
            )
            db.session.add(visitor)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                # Query again in case of concurrent writes
                visitor = AnonymousVisitor.query.filter_by(uuid=anon_cookie).first()
        else:
            # Update last seen timestamp
            visitor.last_seen_at = datetime.utcnow()
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                
        # Set on global context
        g.visitor = visitor
        
        # Track page view metrics selectively
        article_id = None
        if path.startswith('/wiki/'):
            slug = path.split('/wiki/')[-1]
            article = Article.query.filter_by(slug=slug).first()
            if article:
                article_id = article.id
                
        metric = PageViewMetric(
            path=path,
            article_id=article_id,
            visitor_uuid=visitor.uuid if visitor else None
        )
        db.session.add(metric)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    @app.after_request
    def after_request_func(response):
        if hasattr(g, 'set_anon_cookie') and g.set_anon_cookie:
            # 1 year long-lived secure browser cookie
            response.set_cookie(
                'anon_explorer_id',
                g.set_anon_cookie,
                max_age=365 * 24 * 60 * 60,
                httponly=True,
                samesite='Lax',
                secure=(os.environ.get('FLASK_ENV') == 'production')
            )
        return response


def register_blueprints(app):
    """Register all application blueprints."""
    from app.blueprints.main.routes import main_bp
    from app.blueprints.wiki.routes import wiki_bp
    from app.blueprints.admin.routes import admin_bp
    from app.blueprints.community.routes import community_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(wiki_bp, url_prefix='/wiki')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(community_bp, url_prefix='/c')


def register_error_handlers(app):
    """Register HTTP error handlers."""
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500


def register_context_processors(app):
    """Register custom filters and context variables."""
    # Custom filters
    @app.template_filter('datetimeformat')
    def datetimeformat(value, format='%b %d, %Y'):
        if value is None:
            return ""
        return value.strftime(format)

    # Inject categories list into templates for navbar dropdowns
    from app.models.article import Category
    @app.context_processor
    def inject_categories():
        try:
            categories = Category.query.all()
        except Exception:
            categories = []
        return dict(nav_categories=categories)


def setup_logging(app):
    """Configure system logging rotating files."""
    if not app.debug and not app.testing:
        # Log to file in production
        os.makedirs('logs', exist_ok=True)
        file_handler = RotatingFileHandler('logs/terravault.log', maxBytes=10240, backupCount=10)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('TerraVault Startup')
    else:
        # Stdout logging for development
        logging.basicConfig(level=logging.INFO)
