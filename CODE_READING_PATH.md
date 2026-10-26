# TerraVault Code Reading Path

TerraVault is a Flask application where browser requests enter a blueprint,
call a service when an operation has domain rules, read or write SQLAlchemy
models, and render a Jinja template. Read this guide with the relevant source
open beside it.

## Start here

1. `run.py` creates the configured Flask application.
2. `app/__init__.py` is the application factory. It binds extensions, security
   middleware, blueprints, error handlers, template helpers, anonymous visitor
   tracking, and initial development/demo records.
3. `app/config.py` selects environment values such as the secret, database,
   upload storage, and upload limit.
4. `app/extensions.py` defines the unbound Flask extensions used throughout
   the project: database, migrations, login state, and CSRF protection.

## Request architecture

```text
Browser -> Flask app -> Blueprint route -> Service -> SQLAlchemy model -> DB
                     -> Jinja template <- query result / form validation
```

`app/__init__.py` also runs before/after request handlers that give each
anonymous browser a durable cookie ID and record page-view metrics. That is
separate from a registered `User` account.

## File map

| Path | What it does |
| --- | --- |
| `app/__init__.py` | Application composition, extension setup, security/compression/static middleware, blueprints, error pages, visitor identity, and initial seed checks. |
| `app/config.py` | Development/testing/production settings and database URL normalization. |
| `app/extensions.py` | Shared `db`, migration, login, and CSRF extension objects. |
| `app/models/user.py` | Registered users, roles, and user profiles. |
| `app/models/article.py` | Categories, tags, current article state, article-version history, bookmarks, and reading history. |
| `app/models/community.py` | Anonymous visitors, communities, discussions, comments, votes, reports, metrics, newsletters, and audit logs. |
| `app/models/interaction.py` | Reader-to-article interactions such as bookmarks and reading history. |
| `app/services/auth_service.py` | Account registration/authentication/profile persistence. |
| `app/services/cms_service.py` | Article create/update workflows that preserve `ArticleVersion` history. |
| `app/services/wiki_service.py` | Published-article discovery and reader-facing article operations. |
| `app/blueprints/main/routes.py` | Landing page, category/tag/search views, and general public navigation. |
| `app/blueprints/wiki/routes.py` | Article reading, table-of-contents behavior, bookmarks, and reading history. |
| `app/blueprints/auth/routes.py` | Registration, login, verification, reset, and profile pages. |
| `app/blueprints/cms/routes.py` | Contributor article authoring/editing forms. |
| `app/blueprints/community/routes.py` | Anonymous posts, comments, votes, reports, and moderation-aware discussion display. |
| `app/blueprints/admin/routes.py` | Admin login, analytics, article/category management, moderation, and exports. |
| `app/blueprints/*/forms.py` | Flask-WTF validation definitions for each adjacent blueprint. |
| `app/utils/helpers.py` | Small shared transforms such as slug creation and reading-time estimates. |
| `templates/base.html` | Shared page shell, navigation, assets, and template blocks. |
| `templates/main/` | Public discovery pages. |
| `templates/wiki/` | Article reading page. |
| `templates/auth/` | Account/profile workflows. |
| `templates/cms/` | Contributor editing screens. |
| `templates/community/` | Discussion/community user interface. |
| `templates/admin/` | Administrative dashboard and content-management UI. |
| `static/` | Images, CSS, JavaScript, favicon, manifest, and browser-facing assets. |
| `migrations/` | Alembic migration environment and database schema revisions. |
| `seed.py` | Optional explicit data seeding for local/demo environments. |
| `verify_app.py` | Application verification helper. |
| `Dockerfile`, `docker-compose.yml`, `gunicorn.conf.py`, `Procfile` | Container and production-server deployment configuration. |

## Follow the important flows

### Read an article

`main/routes.py` or `wiki/routes.py` finds a published `Article`, increments
or records reader signals through `WikiService`, then renders
`templates/wiki/article.html`. The global request hook separately records a
`PageViewMetric` for the visitor cookie.

### Create or revise an article

`cms/routes.py` validates a Flask-WTF form, calls `CMSService`, writes the
current `Article` fields, then creates an `ArticleVersion`. The latter is the
history trail: it lets the platform show who changed what without silently
overwriting previous content.

### Participate anonymously

The `before_request` hook creates or reads `anon_explorer_id` and stores an
`AnonymousVisitor` in `flask.g`. `community/routes.py` uses that identity to
attribute posts/comments, constrain one vote per target, check bans, and file
reports. It is browser-level attribution, not authentication.

### Run admin workflows

`admin_required` first requires a Flask-Login session then checks the user’s
role. Dashboard numbers come from persisted articles, visitors, reports,
searches, and audit logs, so they can be reviewed after the fact.

## How to understand any screen

1. Find its template under `templates/`.
2. Search for the `render_template` call that renders it.
3. Read the route’s form/query/permission code.
4. Follow any called service method.
5. Inspect the model relationships it reads or updates.
6. Return to the template and match the passed names to Jinja expressions.

This order prevents a common mistake: trying to understand database behavior
from the template alone. Templates display state; routes and services decide
what it is allowed to be.
