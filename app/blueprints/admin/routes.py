"""Administrator-only moderation, content, analytics, and export views."""

from functools import wraps
import csv
import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response, make_response
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.article import Article, Category, Tag, ArticleVersion
from app.models.interaction import Bookmark, ReadingHistory
from app.models.community import (
    AnonymousVisitor, Community, Discussion, Comment, Vote, Report,
    NewsletterSubscriber, AuditLog, PageViewMetric, SearchMetric
)
from app.blueprints.admin.forms import AdminLoginForm, ArticleForm, CategoryForm

admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Flask-Login confirms a session; the role check then prevents a normal
        # reader from reaching administrator operations.
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("Admin access required.", "danger")
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        logout_user()  # Logout any non-admin users
        
    form = AdminLoginForm()
    if form.validate_on_submit():
        from app.services.auth_service import AuthService
        user = AuthService.authenticate_user(form.username.data, form.password.data)
        if user and user.is_admin:
            login_user(user)
            flash("Welcome to TerraVault Control Center.", "success")
            
            # Log audit entry
            log = AuditLog(action="Admin Login", details=f"Admin session started for {user.username}")
            db.session.add(log)
            db.session.commit()
            
            return redirect(url_for('admin.dashboard'))
        else:
            flash("Invalid credentials or unauthorized access.", "danger")
            
    return render_template('admin/login.html', form=form)


@admin_bp.route('/logout')
@login_required
def logout():
    log = AuditLog(action="Admin Logout", details=f"Admin session ended for {current_user.username}")
    db.session.add(log)
    db.session.commit()
    
    logout_user()
    flash("Logged out from Control Center.", "info")
    return redirect(url_for('main.home'))


@admin_bp.route('/')
@login_required
@admin_required
def dashboard():
    # Aggregate persisted events rather than trusting browser counters, so the
    # moderation and traffic summary remains auditable after the fact.
    total_visitors = AnonymousVisitor.query.count()
    total_page_views = PageViewMetric.query.count()
    total_discussions = Discussion.query.count()
    total_comments = Comment.query.count()
    pending_reports = Report.query.filter_by(status='pending').count()
    total_subscribers = NewsletterSubscriber.query.count()
    
    # Traffic last 7 days calculation
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    views_over_time = db.session.query(
        db.func.date(PageViewMetric.timestamp).label('date'), db.func.count(PageViewMetric.id).label('count')
    ).filter(PageViewMetric.timestamp >= seven_days_ago).group_by(db.func.date(PageViewMetric.timestamp)).all()
    
    # Popular articles by views
    popular_articles = Article.query.order_by(Article.views.desc()).limit(5).all()
    
    # Top searches
    top_searches = db.session.query(
        SearchMetric.query, db.func.count(SearchMetric.id).label('search_count')
    ).group_by(SearchMetric.query).order_by(db.func.count(SearchMetric.id).desc()).limit(5).all()
    
    # Recent audit logs
    recent_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(8).all()
    
    return render_template(
        'admin/dashboard.html',
        section='overview',
        total_visitors=total_visitors,
        total_page_views=total_page_views,
        total_discussions=total_discussions,
        total_comments=total_comments,
        pending_reports=pending_reports,
        total_subscribers=total_subscribers,
        views_over_time=views_over_time,
        popular_articles=popular_articles,
        top_searches=top_searches,
        recent_logs=recent_logs
    )


@admin_bp.route('/cms')
@login_required
@admin_required
def cms():
    articles = Article.query.order_by(Article.created_at.desc()).all()
    categories = Category.query.all()
    drafts_count = Article.query.filter_by(status='draft').count()
    published_count = Article.query.filter_by(status='published').count()
    archived_count = Article.query.filter_by(status='archived').count()
    
    return render_template(
        'admin/dashboard.html',
        section='cms',
        articles=articles,
        categories=categories,
        drafts_count=drafts_count,
        published_count=published_count,
        archived_count=archived_count
    )


@admin_bp.route('/cms/article/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_article():
    form = ArticleForm()
    categories = Category.query.all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        from app.utils.helpers import slugify, calculate_reading_time
        title = form.title.data
        slug = slugify(title)
        
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while Article.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1
            
        reading_time = calculate_reading_time(form.content.data)
        
        filename = None
        if form.image.data:
            from werkzeug.utils import secure_filename
            import os
            file = form.image.data
            sec_filename = secure_filename(file.filename)
            filename = f"uploaded_{sec_filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            # Create folder if it doesn't exist
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)
            
        article = Article(
            title=title,
            slug=slug,
            summary=form.summary.data,
            content=form.content.data,
            category_id=form.category_id.data,
            author_id=current_user.id,
            image_url=filename or 'default_article.jpg',
            status=form.status.data,
            is_published=(form.status.data == 'published'),
            is_featured=form.is_featured.data,
            reading_time=reading_time,
            references_data=form.references_data.data
        )
        
        # Tags parsing
        from app.utils.helpers import slugify
        if form.tags.data:
            tags_list = [t.strip() for t in form.tags.data.split(',') if t.strip()]
            for tag_name in tags_list:
                tag_slug = slugify(tag_name)
                tag = Tag.query.filter_by(slug=tag_slug).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=tag_slug)
                    db.session.add(tag)
                article.tags.append(tag)
                
        db.session.add(article)
        db.session.commit()
        
        # Version log
        version = ArticleVersion(
            article_id=article.id,
            title=title,
            summary=form.summary.data,
            content=form.content.data,
            editor_id=current_user.id,
            change_summary="Initial revision"
        )
        db.session.add(version)
        
        # Audit log
        audit = AuditLog(action="Article Created", details=f"Created article '{title}' (Status: {article.status})")
        db.session.add(audit)
        
        db.session.commit()
        flash(f"Article '{title}' created successfully.", "success")
        return redirect(url_for('admin.cms'))
        
    return render_template('admin/article_form.html', form=form, title="Create Article")


@admin_bp.route('/cms/article/edit/<int:article_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_article(article_id):
    article = Article.query.get_or_404(article_id)
    form = ArticleForm()
    categories = Category.query.all()
    form.category_id.choices = [(c.id, c.name) for c in categories]
    
    if form.validate_on_submit():
        from app.utils.helpers import slugify, calculate_reading_time
        
        article.title = form.title.data
        article.summary = form.summary.data
        article.content = form.content.data
        article.category_id = form.category_id.data
        article.status = form.status.data
        article.is_published = (form.status.data == 'published')
        article.is_featured = form.is_featured.data
        article.reading_time = calculate_reading_time(form.content.data)
        article.references_data = form.references_data.data
        
        if form.image.data:
            from werkzeug.utils import secure_filename
            import os
            file = form.image.data
            sec_filename = secure_filename(file.filename)
            filename = f"uploaded_{sec_filename}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)
            article.image_url = filename
            
        # Update tags
        article.tags.clear()
        if form.tags.data:
            tags_list = [t.strip() for t in form.tags.data.split(',') if t.strip()]
            for tag_name in tags_list:
                tag_slug = slugify(tag_name)
                tag = Tag.query.filter_by(slug=tag_slug).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=tag_slug)
                    db.session.add(tag)
                article.tags.append(tag)
                
        # Save version
        version = ArticleVersion(
            article_id=article.id,
            title=article.title,
            summary=article.summary,
            content=article.content,
            editor_id=current_user.id,
            change_summary=form.change_summary.data or "Updated content"
        )
        db.session.add(version)
        
        # Audit log
        audit = AuditLog(action="Article Edited", details=f"Edited article '{article.title}' (Revision: {version.change_summary})")
        db.session.add(audit)
        
        db.session.commit()
        flash("Article updated successfully.", "success")
        return redirect(url_for('admin.cms'))
        
    elif request.method == 'GET':
        form.title.data = article.title
        form.summary.data = article.summary
        form.content.data = article.content
        form.category_id.data = article.category_id
        form.status.data = article.status
        form.is_featured.data = article.is_featured
        form.references_data.data = article.references_data
        form.tags.data = ", ".join([t.name for t in article.tags])
        
    return render_template('admin/article_form.html', form=form, title=f"Edit: {article.title}", article=article)


@admin_bp.route('/cms/article/delete/<int:article_id>', methods=['POST'])
@login_required
@admin_required
def delete_article(article_id):
    article = Article.query.get_or_404(article_id)
    title = article.title
    
    # Audit log
    audit = AuditLog(action="Article Deleted", details=f"Deleted article '{title}'")
    db.session.add(audit)
    
    db.session.delete(article)
    db.session.commit()
    
    flash("Article deleted successfully.", "success")
    return redirect(url_for('admin.cms'))


@admin_bp.route('/cms/category/create', methods=['POST'])
@login_required
@admin_required
def create_category():
    name = request.form.get('name')
    description = request.form.get('description')
    if name:
        from app.utils.helpers import slugify
        slug = slugify(name)
        if Category.query.filter_by(slug=slug).first():
            flash("Category name already exists.", "warning")
        else:
            cat = Category(name=name, slug=slug, description=description)
            db.session.add(cat)
            
            # Audit log
            audit = AuditLog(action="Category Created", details=f"Created category '{name}'")
            db.session.add(audit)
            
            db.session.commit()
            flash(f"Category '{name}' created successfully.", "success")
    else:
        flash("Category name is required.", "danger")
    return redirect(url_for('admin.cms'))


@admin_bp.route('/cms/category/delete/<int:category_id>', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    if category.articles:
        flash(f"Cannot delete category '{category.name}' because it contains active articles.", "danger")
    else:
        name = category.name
        db.session.delete(category)
        
        # Audit log
        audit = AuditLog(action="Category Deleted", details=f"Deleted category '{name}'")
        db.session.add(audit)
        
        db.session.commit()
        flash("Category deleted successfully.", "success")
    return redirect(url_for('admin.cms'))


@admin_bp.route('/moderation')
@login_required
@admin_required
def moderation():
    reports = Report.query.order_by(Report.created_at.desc()).all()
    banned_visitors = AnonymousVisitor.query.filter_by(is_banned=True).all()
    
    return render_template(
        'admin/dashboard.html',
        section='moderation',
        reports=reports,
        banned_visitors=banned_visitors
    )


@admin_bp.route('/moderation/report/dismiss/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def dismiss_report(report_id):
    report = Report.query.get_or_404(report_id)
    report.status = 'dismissed'
    
    # Audit log
    audit = AuditLog(action="Report Dismissed", details=f"Dismissed report #{report.id} on visitor {report.visitor_uuid}")
    db.session.add(audit)
    
    db.session.commit()
    flash(f"Report #{report.id} dismissed.", "success")
    return redirect(url_for('admin.moderation'))


@admin_bp.route('/moderation/report/remove/<int:report_id>', methods=['POST'])
@login_required
@admin_required
def remove_content(report_id):
    report = Report.query.get_or_404(report_id)
    reason = request.form.get('reason', 'Spam/Inappropriate content')
    
    if report.discussion_id:
        discussion = Discussion.query.get(report.discussion_id)
        if discussion:
            discussion.status = 'removed'
            discussion.removed_reason = reason
            discussion.removed_at = datetime.utcnow()
            # Mark report reviewed
            report.status = 'reviewed'
            
            # Audit log
            audit = AuditLog(
                action="Discussion Soft-Deleted",
                details=f"Removed discussion '{discussion.title}' (ID: {discussion.id}). Reason: {reason}"
            )
            db.session.add(audit)
            
            # Soft-delete all its comments as well
            for comm in discussion.comments:
                comm.status = 'removed'
                comm.removed_reason = 'Parent discussion removed'
                comm.removed_at = datetime.utcnow()
                
            db.session.commit()
            flash("Discussion content soft-deleted successfully.", "success")
            
    elif report.comment_id:
        comment = Comment.query.get(report.comment_id)
        if comment:
            comment.status = 'removed'
            comment.removed_reason = reason
            comment.removed_at = datetime.utcnow()
            # Mark report reviewed
            report.status = 'reviewed'
            
            # Audit log
            audit = AuditLog(
                action="Comment Soft-Deleted",
                details=f"Removed comment (ID: {comment.id}) under discussion ID {comment.discussion_id}. Reason: {reason}"
            )
            db.session.add(audit)
            
            db.session.commit()
            flash("Comment content soft-deleted successfully.", "success")
            
    return redirect(url_for('admin.moderation'))


@admin_bp.route('/moderation/ban/<string:visitor_uuid>', methods=['POST'])
@login_required
@admin_required
def ban_visitor(visitor_uuid):
    visitor = AnonymousVisitor.query.get_or_404(visitor_uuid)
    reason = request.form.get('reason', 'Violated terms')
    days = int(request.form.get('days', '7'))  # default 7 days, or 0 for permanent
    
    visitor.is_banned = True
    visitor.ban_reason = reason
    if days > 0:
        visitor.ban_expires = datetime.utcnow() + timedelta(days=days)
        details = f"Banned visitor '{visitor.display_name}' ({visitor.uuid}) for {days} days. Reason: {reason}"
    else:
        visitor.ban_expires = None
        details = f"Banned visitor '{visitor.display_name}' ({visitor.uuid}) permanently. Reason: {reason}"
        
    # Audit log
    audit = AuditLog(action="Visitor Banned", details=details)
    db.session.add(audit)
    
    db.session.commit()
    flash(f"Visitor {visitor.display_name} has been banned.", "success")
    return redirect(url_for('admin.moderation'))


@admin_bp.route('/moderation/unban/<string:visitor_uuid>', methods=['POST'])
@login_required
@admin_required
def unban_visitor(visitor_uuid):
    visitor = AnonymousVisitor.query.get_or_404(visitor_uuid)
    visitor.is_banned = False
    visitor.ban_reason = None
    visitor.ban_expires = None
    
    # Audit log
    audit = AuditLog(action="Visitor Unbanned", details=f"Unbanned visitor '{visitor.display_name}' ({visitor.uuid})")
    db.session.add(audit)
    
    db.session.commit()
    flash(f"Visitor {visitor.display_name} has been unbanned.", "success")
    return redirect(url_for('admin.moderation'))


@admin_bp.route('/crm')
@login_required
@admin_required
def crm():
    subscribers = NewsletterSubscriber.query.order_by(NewsletterSubscriber.signup_date.desc()).all()
    # Simple conversion rate (subscribers / unique visitors)
    total_visitors = AnonymousVisitor.query.count()
    total_subs = NewsletterSubscriber.query.count()
    conversion_rate = 0.0
    if total_visitors > 0:
        conversion_rate = round((total_subs / total_visitors) * 100, 2)
        
    return render_template(
        'admin/dashboard.html',
        section='crm',
        subscribers=subscribers,
        conversion_rate=conversion_rate
    )


@admin_bp.route('/crm/export-csv')
@login_required
@admin_required
def export_subscribers():
    subscribers = NewsletterSubscriber.query.all()
    
    # Generate CSV in memory
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Email', 'Interest Category', 'Source', 'Signup Date'])
    for sub in subscribers:
        cw.writerow([sub.email, sub.interest_category or 'General', sub.source, sub.signup_date.strftime('%Y-%m-%d %H:%M:%S')])
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=newsletter_subscribers.csv"
    output.headers["Content-type"] = "text/csv"
    
    # Audit log
    audit = AuditLog(action="Subscribers Exported", details="Exported newsletter subscriber database to CSV")
    db.session.add(audit)
    db.session.commit()
    
    return output


@admin_bp.route('/logs')
@login_required
@admin_required
def logs():
    audit_logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template(
        'admin/dashboard.html',
        section='logs',
        audit_logs=audit_logs
    )


@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    # Category Views
    try:
        category_views = db.session.query(
            Category.name, db.func.sum(Article.views)
        ).join(Article).group_by(Category.name).all()
    except Exception as e:
        db.session.rollback()
        category_views = []
    
    # Top Active Communities
    try:
        community_discussions = db.session.query(
            Community.name, db.func.count(Discussion.id)
        ).join(Discussion).group_by(Community.name).all()
    except Exception as e:
        db.session.rollback()
        community_discussions = []
    
    # Most bookmarked articles
    try:
        bookmarked_articles = db.session.query(
            Article.title, db.func.count(Bookmark.id)
        ).join(Bookmark).group_by(Article.title).order_by(db.func.count(Bookmark.id).desc()).limit(5).all()
    except Exception as e:
        db.session.rollback()
        bookmarked_articles = []
    
    # Average reading duration (safely cast Decimal to float for PostgreSQL compatibility)
    try:
        avg_reading_time = db.session.query(db.func.avg(ReadingHistory.time_spent)).scalar() or 0
        avg_reading_minutes = round(float(avg_reading_time) / 60.0, 2)
    except Exception as e:
        db.session.rollback()
        avg_reading_minutes = 0.0
    
    # Detailed recent views
    try:
        recent_views = PageViewMetric.query.order_by(PageViewMetric.timestamp.desc()).limit(15).all()
    except Exception as e:
        db.session.rollback()
        recent_views = []

    try:
        pending_reports = Report.query.filter_by(status='pending').count()
    except Exception:
        pending_reports = 0
    
    return render_template(
        'admin/dashboard.html',
        section='analytics',
        category_views=category_views,
        community_discussions=community_discussions,
        bookmarked_articles=bookmarked_articles,
        avg_reading_minutes=avg_reading_minutes,
        recent_views=recent_views,
        pending_reports=pending_reports
    )
