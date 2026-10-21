import unittest
from app import create_app
from app.extensions import db
from app.models.community import AnonymousVisitor, Discussion, Comment, Vote, Report, PageViewMetric
from app.models.user import User, Role
from flask import g

class TestTerraVault(unittest.TestCase):
    def setUp(self):
        self.app = create_app('testing')
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Seed or reuse a basic community
        from app.models.community import Community
        self.comm = Community.query.filter_by(slug="history").first()
        if not self.comm:
            self.comm = Community(name="History", slug="history", description="Test history community")
            db.session.add(self.comm)
            db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_anonymous_cookie_generation(self):
        # Initial request should set the cookie
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        
        # Check that the cookie exists in headers
        cookies = response.headers.getlist('Set-Cookie')
        cookie_header = next((c for c in cookies if 'anon_explorer_id' in c), None)
        self.assertIsNotNone(cookie_header)
        
        # Verify cookie attributes
        self.assertTrue('HttpOnly' in cookie_header)
        self.assertTrue('SameSite=Lax' in cookie_header)

    def test_voting_constraints(self):
        # Simulate creating a visitor
        visitor = AnonymousVisitor(uuid="test-uuid", display_name="Test Explorer", avatar_color="blue")
        db.session.add(visitor)
        db.session.commit()
        
        disc = Discussion(title="Test Post", content="Test Body", community_id=self.comm.id, visitor_uuid=visitor.uuid)
        db.session.add(disc)
        db.session.commit()
        
        # First vote
        vote1 = Vote(visitor_uuid=visitor.uuid, discussion_id=disc.id, value=1)
        db.session.add(vote1)
        db.session.commit()
        
        # Duplicate vote should violate unique constraint
        vote2 = Vote(visitor_uuid=visitor.uuid, discussion_id=disc.id, value=-1)
        db.session.add(vote2)
        with self.assertRaises(Exception):
            db.session.commit()
        db.session.rollback()

    def test_selective_page_views(self):
        # Request health check
        self.client.get('/health')
        # Request static asset simulation
        self.client.get('/static/globe-logo.svg')
        # Request normal page
        self.client.get('/')
        
        # Verify only the page view was recorded, not static or health
        metrics = PageViewMetric.query.all()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].path, '/')

    def test_admin_access_limits(self):
        # Attempt to access admin dashboard without admin role
        response = self.client.get('/admin/')
        # Should redirect to admin login
        self.assertEqual(response.status_code, 302)
        self.assertTrue('/admin/login' in response.headers['Location'])

    def test_auth_blueprints_accessible(self):
        # Test that /auth/login and /auth/register render 200
        res_login = self.client.get('/auth/login')
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'Log In', res_login.data)

        res_reg = self.client.get('/auth/register')
        self.assertEqual(res_reg.status_code, 200)
        self.assertIn(b'Register', res_reg.data)

    def test_cms_protected_routes(self):
        # Unauthenticated access to CMS should redirect
        res_cms = self.client.get('/cms/')
        self.assertIn(res_cms.status_code, [302, 401, 403])

if __name__ == '__main__':
    unittest.main()
