from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock
from .models import Ticket, TicketComment, InboundEmail
from .ai_service import classify_ticket, auto_resolve_check

User = get_user_model()


class UserSetupMixin:
    """Shared setup for creating test users."""

    def setUp(self):
        self.client = Client()

        self.customer = User.objects.create_user(
            username='testcustomer',
            email='customer@test.com',
            password='TestPass123!',
            role='customer'
        )
        self.agent = User.objects.create_user(
            username='testagent',
            email='agent@test.com',
            password='TestPass123!',
            role='agent'
        )
        self.admin = User.objects.create_user(
            username='testadmin',
            email='admin@test.com',
            password='TestPass123!',
            role='admin'
        )
        self.ticket = Ticket.objects.create(
            owner=self.customer,
            title='Test Ticket',
            description='This is a test ticket description.',
            status='open',
            priority='medium',
            category='general'
        )


# ─── Model Tests ────────────────────────────────────────────────────────────

class UserModelTest(TestCase):

    def setUp(self):
        self.customer = User.objects.create_user(
            username='customer1', password='TestPass123!', role='customer'
        )
        self.agent = User.objects.create_user(
            username='agent1', password='TestPass123!', role='agent'
        )
        self.admin = User.objects.create_user(
            username='admin1', password='TestPass123!', role='admin'
        )

    def test_customer_is_not_agent(self):
        self.assertFalse(self.customer.is_agent())

    def test_agent_is_agent(self):
        self.assertTrue(self.agent.is_agent())

    def test_admin_is_agent(self):
        self.assertTrue(self.admin.is_agent())

    def test_customer_is_customer(self):
        self.assertTrue(self.customer.is_customer())

    def test_agent_is_not_customer(self):
        self.assertFalse(self.agent.is_customer())

    def test_user_str(self):
        self.assertEqual(str(self.customer), 'customer1 (customer)')


class TicketModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='owner', password='TestPass123!', role='customer'
        )

    def test_ticket_creation(self):
        ticket = Ticket.objects.create(
            owner=self.user,
            title='Test Ticket',
            description='Test description',
        )
        self.assertEqual(ticket.status, 'open')
        self.assertEqual(ticket.priority, 'medium')
        self.assertEqual(ticket.category, 'general')

    def test_ticket_str(self):
        ticket = Ticket.objects.create(
            owner=self.user,
            title='Test Ticket',
            description='Test description',
        )
        self.assertIn('OPEN', str(ticket))
        self.assertIn('Test Ticket', str(ticket))

    def test_ticket_sanitizes_html(self):
        ticket = Ticket.objects.create(
            owner=self.user,
            title='<script>alert("xss")</script>Clean Title',
            description='<script>bad</script>Clean description',
        )
        self.assertNotIn('<script>', ticket.title)
        self.assertNotIn('<script>', ticket.description)

    def test_ticket_ordering(self):
        ticket1 = Ticket.objects.create(
            owner=self.user, title='First', description='desc'
        )
        ticket2 = Ticket.objects.create(
            owner=self.user, title='Second', description='desc'
        )
        tickets = Ticket.objects.all()
        self.assertEqual(tickets[0], ticket2)


class TicketCommentModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='commenter', password='TestPass123!', role='customer'
        )
        self.ticket = Ticket.objects.create(
            owner=self.user, title='Test', description='Test'
        )

    def test_comment_creation(self):
        comment = TicketComment.objects.create(
            ticket=self.ticket,
            author=self.user,
            body='This is a comment'
        )
        self.assertEqual(comment.body, 'This is a comment')

    def test_comment_sanitizes_html(self):
        comment = TicketComment.objects.create(
            ticket=self.ticket,
            author=self.user,
            body='<script>alert("xss")</script>Clean comment'
        )
        self.assertNotIn('<script>', comment.body)

    def test_comment_str(self):
        comment = TicketComment.objects.create(
            ticket=self.ticket,
            author=self.user,
            body='Test comment'
        )
        self.assertIn('commenter', str(comment))


# ─── View Tests ─────────────────────────────────────────────────────────────

class DashboardViewTest(UserSetupMixin, TestCase):

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('tickets:dashboard'))
        self.assertRedirects(response, '/accounts/login/?next=/tickets/')

    def test_customer_sees_own_tickets_only(self):
        other_customer = User.objects.create_user(
            username='other', password='TestPass123!', role='customer'
        )
        Ticket.objects.create(
            owner=other_customer, title='Other ticket', description='desc'
        )
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.get(reverse('tickets:dashboard'))
        self.assertEqual(response.status_code, 200)
        tickets = response.context['tickets']
        for ticket in tickets:
            self.assertEqual(ticket.owner, self.customer)

    def test_agent_sees_all_tickets(self):
        self.client.login(username='testagent', password='TestPass123!')
        response = self.client.get(reverse('tickets:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(response.context['tickets'].count(), 1)

    def test_dashboard_shows_correct_counts(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.get(reverse('tickets:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('open_count', response.context)


class TicketCreateViewTest(UserSetupMixin, TestCase):

    def test_create_requires_login(self):
        response = self.client.get(reverse('tickets:ticket_create'))
        self.assertRedirects(response, '/accounts/login/?next=/tickets/create/')

    def test_customer_can_create_ticket(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        with patch('tickets.views.broadcast_new_ticket'), \
             patch('tickets.tasks.send_ticket_confirmation_email.delay'), \
             patch('tickets.tasks.auto_resolve_ticket.delay'), \
             patch('tickets.tasks.classify_new_ticket.delay'):
            response = self.client.post(reverse('tickets:ticket_create'), {
                'title': 'New Test Ticket',
                'description': 'Test description for new ticket',
                'priority': 'medium',
                'category': 'general',
            })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Ticket.objects.filter(title='New Test Ticket').exists())

    def test_ticket_owner_set_to_current_user(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        with patch('tickets.views.broadcast_new_ticket'), \
             patch('tickets.tasks.send_ticket_confirmation_email.delay'), \
             patch('tickets.tasks.auto_resolve_ticket.delay'), \
             patch('tickets.tasks.classify_new_ticket.delay'):
            self.client.post(reverse('tickets:ticket_create'), {
                'title': 'Ownership Test',
                'description': 'Testing owner assignment',
                'priority': 'low',
                'category': 'general',
            })
        ticket = Ticket.objects.get(title='Ownership Test')
        self.assertEqual(ticket.owner, self.customer)

    def test_invalid_form_returns_200(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.post(reverse('tickets:ticket_create'), {
            'title': '',
            'description': '',
        })
        self.assertEqual(response.status_code, 200)


class TicketDetailViewTest(UserSetupMixin, TestCase):

    def test_detail_requires_login(self):
        response = self.client.get(
            reverse('tickets:ticket_detail', args=[self.ticket.pk])
        )
        self.assertRedirects(
            response,
            f'/accounts/login/?next=/tickets/{self.ticket.pk}/'
        )

    def test_owner_can_view_ticket(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.get(
            reverse('tickets:ticket_detail', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['ticket'], self.ticket)

    def test_agent_can_view_any_ticket(self):
        self.client.login(username='testagent', password='TestPass123!')
        response = self.client.get(
            reverse('tickets:ticket_detail', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_other_customer_cannot_view_ticket(self):
        other = User.objects.create_user(
            username='other2', password='TestPass123!', role='customer'
        )
        self.client.login(username='other2', password='TestPass123!')
        response = self.client.get(
            reverse('tickets:ticket_detail', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_customer_can_add_comment(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ticket_detail', args=[self.ticket.pk]),
            {'body': 'Test comment'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TicketComment.objects.filter(body='Test comment').exists()
        )


class TicketCloseViewTest(UserSetupMixin, TestCase):

    def test_owner_can_close_ticket(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ticket_close', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'closed')

    def test_other_customer_cannot_close_ticket(self):
        other = User.objects.create_user(
            username='other3', password='TestPass123!', role='customer'
        )
        self.client.login(username='other3', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ticket_close', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 403)


class TicketStatusUpdateViewTest(UserSetupMixin, TestCase):

    def test_agent_can_update_status(self):
        self.client.login(username='testagent', password='TestPass123!')
        with patch('tickets.views.broadcast_ticket_update'):
            response = self.client.post(
                reverse('tickets:ticket_status_update', args=[self.ticket.pk]),
                {
                    'status': 'in_progress',
                    'priority': 'medium',
                    'assigned_to': '',
               }
           )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, 'in_progress')

    def test_customer_cannot_update_status(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ticket_status_update', args=[self.ticket.pk]),
            {'status': 'in_progress'}
        )
        self.assertEqual(response.status_code, 403)


# ─── AI View Tests ───────────────────────────────────────────────────────────

class AISummarizeViewTest(UserSetupMixin, TestCase):

    def test_summarize_requires_login(self):
        response = self.client.post(
            reverse('tickets:ai_summarize', args=[self.ticket.pk])
        )
        self.assertRedirects(
            response,
            f'/accounts/login/?next=/tickets/{self.ticket.pk}/ai/summarize/'
        )

    def test_summarize_returns_summary(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        with patch('tickets.views.ai_service.summarize_ticket') as mock_summarize:
            mock_summarize.return_value = 'This is a test summary.'
            response = self.client.post(
                reverse('tickets:ai_summarize', args=[self.ticket.pk])
            )
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {'summary': 'This is a test summary.'}
        )


class AIPolishViewTest(UserSetupMixin, TestCase):

    def test_polish_requires_agent(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ai_polish_reply', args=[self.ticket.pk]),
            {'rough_reply': 'fix ur problem'}
        )
        self.assertEqual(response.status_code, 403)

    def test_agent_can_polish_reply(self):
        self.client.login(username='testagent', password='TestPass123!')
        with patch('tickets.views.ai_service.polish_reply') as mock_polish:
            mock_polish.return_value = 'Polished professional reply.'
            response = self.client.post(
                reverse('tickets:ai_polish_reply', args=[self.ticket.pk]),
                {'rough_reply': 'fix ur problem'}
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('polished_reply', data)

    def test_polish_requires_rough_reply(self):
        self.client.login(username='testagent', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ai_polish_reply', args=[self.ticket.pk]),
            {'rough_reply': ''}
        )
        self.assertEqual(response.status_code, 400)


class AIClassifyViewTest(UserSetupMixin, TestCase):

    def test_classify_requires_agent(self):
        self.client.login(username='testcustomer', password='TestPass123!')
        response = self.client.post(
            reverse('tickets:ai_classify', args=[self.ticket.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_agent_can_classify(self):
        self.client.login(username='testagent', password='TestPass123!')
        with patch('tickets.views.ai_service.classify_ticket') as mock_classify:
            mock_classify.return_value = {
                'category': 'technical',
                'priority': 'high'
            }
            response = self.client.post(
                reverse('tickets:ai_classify', args=[self.ticket.pk])
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('category', data)
        self.assertIn('priority', data)


# ─── Mailgun Webhook Tests ───────────────────────────────────────────────────

class MailgunWebhookTest(TestCase):

    def test_webhook_missing_fields_returns_400(self):
        response = self.client.post(
            reverse('tickets:mailgun_webhook'),
            {'sender': '', 'body-plain': ''}
        )
        self.assertEqual(response.status_code, 400)

    def test_webhook_creates_inbound_email(self):
        with patch('tickets.views.process_inbound_email.delay'):
            response = self.client.post(
                reverse('tickets:mailgun_webhook'),
                {
                    'sender': 'customer@example.com',
                    'subject': 'Test email subject',
                    'body-plain': 'This is a test email body.',
                    'token': 'testtoken',
                    'timestamp': '1234567890',
                    'signature': 'testsignature',
                }
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            InboundEmail.objects.filter(sender='customer@example.com').exists()
        )


# ─── Account View Tests ──────────────────────────────────────────────────────

class RegisterViewTest(TestCase):

    def test_register_page_loads(self):
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 200)

    def test_valid_registration(self):
        response = self.client.post(reverse('accounts:register'), {
            'username': 'newuser',
            'email': 'newuser@test.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',        
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username='newuser').exists())

    def test_duplicate_username_rejected(self):
        User.objects.create_user(username='existing', password='TestPass123!')
        response = self.client.post(reverse('accounts:register'), {
            'username': 'existing',
            'email': 'new@test.com',
            'first_name': 'Test',
            'last_name': 'User',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_redirected(self):
        User.objects.create_user(username='loggedin', password='TestPass123!')
        self.client.login(username='loggedin', password='TestPass123!')
        response = self.client.get(reverse('accounts:register'))
        self.assertEqual(response.status_code, 302)


class LoginViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='logintest', password='TestPass123!'
        )

    def test_login_page_loads(self):
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 200)

    def test_valid_login(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'logintest',
            'password': 'TestPass123!',
        })
        self.assertEqual(response.status_code, 302)

    def test_invalid_login(self):
        response = self.client.post(reverse('accounts:login'), {
            'username': 'logintest',
            'password': 'wrongpassword',
        })
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_redirected(self):
        self.client.login(username='logintest', password='TestPass123!')
        response = self.client.get(reverse('accounts:login'))
        self.assertEqual(response.status_code, 302)


class LogoutViewTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='logouttest', password='TestPass123!'
        )

    def test_logout_requires_post(self):
        self.client.login(username='logouttest', password='TestPass123!')
        response = self.client.get(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 405)

    def test_logout_works(self):
        self.client.login(username='logouttest', password='TestPass123!')
        response = self.client.post(reverse('accounts:logout'))
        self.assertEqual(response.status_code, 302)

# Create your tests here.
