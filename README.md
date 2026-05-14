# AI Support System

A production-grade AI-powered customer support ticket system built with Django. 
Deployed live on Railway with PostgreSQL, Redis, Celery, and WebSockets.

## Features

### Ticket Management
- Role-based access control (Customer, Agent, Admin)
- Full ticket lifecycle — open, in progress, resolved, closed
- Priority and category classification
- Real-time dashboard updates via WebSockets
- Comment threads on tickets

### AI Features (Anthropic Claude API)
- **Summarize** — condense long ticket conversations in one click
- **Polish Reply** — transform rough agent drafts into professional responses
- **Auto-classify** — automatically assign category and priority using AI
- **Auto-resolve** — AI resolves simple tickets automatically

### Email AI Agent
- Customers email support@mg.simedelonney.com
- AI agent picks up the email automatically
- Generates and sends a professional reply within seconds
- Escalates complex issues to human agents
- No human involvement for simple requests

### Security
- IP-based rate limiting on authentication endpoints
- CSRF protection on all forms
- XSS prevention with bleach sanitization
- Role-based access control
- Mailgun webhook signature verification
- Environment variables for all secrets
- 49 automated security tests — all passing

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.x |
| Database | PostgreSQL |
| Cache/Queue | Redis |
| Background Tasks | Celery |
| Real-time | Django Channels + WebSockets |
| AI | Anthropic Claude API |
| Email | Mailgun |
| Frontend | Bootstrap 5 |
| Containerization | Docker |
| Deployment | Railway |
| Testing | Django TestCase (49 tests) |

## Architecture
Browser → Daphne (ASGI) → Django
→ Django Channels → Redis (WebSockets)
→ Celery Worker → Redis (Task Queue)
→ PostgreSQL (Data)
→ Anthropic API (AI)
→ Mailgun (Email)

## Live Demo

[https://web-production-4e3df.up.railway.app](https://web-production-4e3df.up.railway.app)

## Local Development

### Prerequisites
- Python 3.11+
- Redis running locally
- PostgreSQL database

### Setup

```bash
# Clone the repository
git clone https://github.com/Deloney-code/ai-support-system.git
cd ai-support-system

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Edit .env with your credentials

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start Redis (WSL on Windows)
redis-server

# Start Celery worker
celery -A core worker --loglevel=info --pool=solo

# Start development server
daphne -p 8000 core.asgi:application
```

## Environment Variables
SECRET_KEY=your-secret-key
DEBUG=False
ALLOWED_HOSTS=your-domain.com
DATABASE_URL=postgresql://...
REDIS_URL=redis://...
ANTHROPIC_API_KEY=your-anthropic-key
MAILGUN_API_KEY=your-mailgun-key
MAILGUN_SMTP_KEY=your-smtp-key
MAILGUN_SMTP_LOGIN=postmaster@mg.yourdomain.com
DEFAULT_FROM_EMAIL=support@mg.yourdomain.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend

## Running Tests

```bash
python manage.py test tickets accounts --verbosity=2
```

49 tests covering:
- Model validation and XSS sanitization
- View access control and permissions
- AI endpoint authorization
- Mailgun webhook security
- Authentication flows

## Project Structure
ai_support_system/
├── accounts/          # Custom user model, auth views
├── tickets/           # Tickets, comments, AI features
│   ├── models.py      # Ticket, TicketComment, InboundEmail
│   ├── views.py       # All views including webhook
│   ├── ai_service.py  # Anthropic API integration
│   ├── tasks.py       # Celery background tasks
│   ├── consumers.py   # WebSocket consumers
│   └── tests.py       # 49 automated tests
├── core/              # Settings, URLs, Celery config
├── templates/         # Bootstrap 5 templates
└── start.py           # Production startup script

## Author

Built by **Sime Delonney** as part of a Professional Masters 
in Cybersecurity project.

---

⭐ Star this repo if you find it useful!
