"""Anonymous discussion, comments, votes, and content reports.

The app-level request hook establishes g.visitor before these handlers run.
That browser-scoped identity enables moderation without requiring a login.
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, g, abort
from app.extensions import db
from app.models.community import Community, Discussion, Comment, Vote, Report, AnonymousVisitor

community_bp = Blueprint('community', __name__)

@community_bp.route('/<slug>')
def view_community(slug):
    """Browse discussions in a specific community."""
    community = Community.query.filter_by(slug=slug).first_or_404()
    
    # Filter out removed discussions
    sort_by = request.args.get('sort', 'new')
    query = Discussion.query.filter_by(community_id=community.id).filter(Discussion.status != 'removed')
    
    if sort_by == 'popular':
        # Simple popularity score: count of upvotes minus downvotes
        # For simplicity, order by views or count of votes
        discussions = query.order_by(Discussion.views.desc()).all()
    else:
        discussions = query.order_by(Discussion.created_at.desc()).all()
        
    # Inject net score into discussions for rendering
    for disc in discussions:
        upvotes = Vote.query.filter_by(discussion_id=disc.id, value=1).count()
        downvotes = Vote.query.filter_by(discussion_id=disc.id, value=-1).count()
        disc.score = upvotes - downvotes
        # Check current visitor's vote
        visitor_vote = 0
        if g.visitor:
            v = Vote.query.filter_by(visitor_uuid=g.visitor.uuid, discussion_id=disc.id).first()
            if v:
                visitor_vote = v.value
        disc.visitor_vote = visitor_vote
        
    all_communities = Community.query.all()
    return render_template(
        'community/view_community.html',
        community=community,
        discussions=discussions,
        all_communities=all_communities,
        sort_by=sort_by
    )


@community_bp.route('/<slug>/post/create', methods=['GET', 'POST'])
def create_post(slug):
    """Anonymously post a new discussion thread."""
    community = Community.query.filter_by(slug=slug).first_or_404()
    
    # Check if banned
    if g.visitor and g.visitor.is_banned:
        ban_msg = f"Your anonymous ID is banned. Reason: {g.visitor.ban_reason or 'No reason provided'}."
        if g.visitor.ban_expires:
            ban_msg += f" Ban expires on {g.visitor.ban_expires.strftime('%Y-%b-%d')}."
        flash(ban_msg, "danger")
        return redirect(url_for('community.view_community', slug=slug))
        
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        
        if not title or not content:
            flash("Title and Content are required fields.", "warning")
            return redirect(request.referrer)
            
        discussion = Discussion(
            title=title,
            content=content,
            community_id=community.id,
            visitor_uuid=g.visitor.uuid if g.visitor else None,
            status='published'
        )
        db.session.add(discussion)
        db.session.commit()
        
        flash("Discussion posted successfully!", "success")
        return redirect(url_for('community.view_discussion', id=discussion.id))
        
    return render_template('community/create_post.html', community=community)


@community_bp.route('/discussion/<int:id>')
def view_discussion(id):
    """View a single discussion thread, its views count, and comments hierarchy."""
    # Find discussion (even if removed by admin, we will show a placeholder if requested, or 404)
    discussion = Discussion.query.get_or_404(id)
    if discussion.status == 'removed':
        return render_template('community/removed.html'), 404
        
    # Increment view count
    discussion.views += 1
    db.session.commit()
    
    # Calculate score
    upvotes = Vote.query.filter_by(discussion_id=discussion.id, value=1).count()
    downvotes = Vote.query.filter_by(discussion_id=discussion.id, value=-1).count()
    discussion.score = upvotes - downvotes
    
    # Current visitor's vote on discussion
    visitor_vote = 0
    if g.visitor:
        v = Vote.query.filter_by(visitor_uuid=g.visitor.uuid, discussion_id=discussion.id).first()
        if v:
            visitor_vote = v.value
    discussion.visitor_vote = visitor_vote
    
    # Fetch top-level comments (excluding soft-deleted parents entirely, or rendering them as [removed] if they have replies)
    top_level_comments = Comment.query.filter_by(discussion_id=discussion.id, parent_id=None).order_by(Comment.created_at.asc()).all()
    
    # Templates need score and current-visitor vote on every nested reply.
    # Recursion mirrors the Comment parent/child relationship.
    def process_comments(comments_list):
        for comm in comments_list:
            comm_up = Vote.query.filter_by(comment_id=comm.id, value=1).count()
            comm_down = Vote.query.filter_by(comment_id=comm.id, value=-1).count()
            comm.score = comm_up - comm_down
            
            comm_visitor_vote = 0
            if g.visitor:
                cv = Vote.query.filter_by(visitor_uuid=g.visitor.uuid, comment_id=comm.id).first()
                if cv:
                    comm_visitor_vote = cv.value
            comm.visitor_vote = comm_visitor_vote
            
            # Recurse down children replies
            process_comments(comm.replies)
            
    process_comments(top_level_comments)
    
    all_communities = Community.query.all()
    return render_template(
        'community/view_discussion.html',
        discussion=discussion,
        comments=top_level_comments,
        all_communities=all_communities
    )


@community_bp.route('/discussion/<int:id>/comment', methods=['POST'])
def add_comment(id):
    """Anonymously add a comment or nested reply to a discussion thread."""
    discussion = Discussion.query.get_or_404(id)
    
    # Check if banned
    if g.visitor and g.visitor.is_banned:
        ban_msg = f"Your anonymous ID is banned. Reason: {g.visitor.ban_reason or 'No reason provided'}."
        flash(ban_msg, "danger")
        return redirect(url_for('community.view_discussion', id=id))
        
    content = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id')
    
    if not content:
        flash("Comment content cannot be empty.", "warning")
        return redirect(url_for('community.view_discussion', id=id))
        
    comment = Comment(
        content=content,
        discussion_id=discussion.id,
        parent_id=int(parent_id) if parent_id else None,
        visitor_uuid=g.visitor.uuid if g.visitor else None,
        status='published'
    )
    db.session.add(comment)
    db.session.commit()
    
    flash("Comment posted successfully!", "success")
    return redirect(url_for('community.view_discussion', id=id))


@community_bp.route('/vote', methods=['POST'])
def cast_vote():
    """Cast an upvote/downvote on a discussion or a comment."""
    if g.visitor and g.visitor.is_banned:
        return jsonify({'error': 'Your anonymous ID is banned from voting.'}), 403
        
    data = request.json or {}
    discussion_id = data.get('discussion_id')
    comment_id = data.get('comment_id')
    value = data.get('value')  # Expected: 1 or -1
    
    if value not in [1, -1]:
        return jsonify({'error': 'Invalid vote value.'}), 400
        
    if not g.visitor:
        return jsonify({'error': 'Anonymous session not established.'}), 400
        
    # Each visitor has one vote per target. Repeating the same direction clears
    # it; switching direction updates it, so the UI behaves like a toggle.
    if discussion_id:
        vote = Vote.query.filter_by(visitor_uuid=g.visitor.uuid, discussion_id=discussion_id).first()
        if vote:
            if vote.value == value:
                # Toggle vote off
                db.session.delete(vote)
                action = 'cleared'
            else:
                # Update vote value
                vote.value = value
                action = 'updated'
        else:
            vote = Vote(visitor_uuid=g.visitor.uuid, discussion_id=discussion_id, value=value)
            db.session.add(vote)
            action = 'created'
            
        db.session.commit()
        # Count total net score
        up = Vote.query.filter_by(discussion_id=discussion_id, value=1).count()
        down = Vote.query.filter_by(discussion_id=discussion_id, value=-1).count()
        return jsonify({'success': True, 'score': up - down, 'action': action})
        
    elif comment_id:
        vote = Vote.query.filter_by(visitor_uuid=g.visitor.uuid, comment_id=comment_id).first()
        if vote:
            if vote.value == value:
                db.session.delete(vote)
                action = 'cleared'
            else:
                vote.value = value
                action = 'updated'
        else:
            vote = Vote(visitor_uuid=g.visitor.uuid, comment_id=comment_id, value=value)
            db.session.add(vote)
            action = 'created'
            
        db.session.commit()
        up = Vote.query.filter_by(comment_id=comment_id, value=1).count()
        down = Vote.query.filter_by(comment_id=comment_id, value=-1).count()
        return jsonify({'success': True, 'score': up - down, 'action': action})
        
    return jsonify({'error': 'Missing vote target.'}), 400


@community_bp.route('/report', methods=['POST'])
def report_content():
    """Anonymously flag discussions or comments for admin review."""
    discussion_id = request.form.get('discussion_id')
    comment_id = request.form.get('comment_id')
    reason = request.form.get('reason', 'Other')
    details = request.form.get('details', '')
    
    if not g.visitor:
        flash("Anonymous session not established.", "danger")
        return redirect(request.referrer)
        
    report = Report(
        visitor_uuid=g.visitor.uuid,
        discussion_id=int(discussion_id) if discussion_id else None,
        comment_id=int(comment_id) if comment_id else None,
        reason=reason,
        details=details,
        status='pending'
    )
    db.session.add(report)
    db.session.commit()
    
    flash("Thank you. Content flagged for administrative review.", "success")
    return redirect(request.referrer)
