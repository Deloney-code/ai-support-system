from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from .forms import SecureRegistrationForm, SecureLoginForm


@require_http_methods(["GET", "POST"])
def register_view(request):
    """
    Registration view.
    Redirects authenticated users away — no point showing
    the register page to someone already logged in.
    """
    if request.user.is_authenticated:
        return redirect('tickets:dashboard')

    form = SecureRegistrationForm(request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = form.save()
            # Log the user in immediately after registration
            login(request, user)
            messages.success(request, "Account created. Welcome!")
            return redirect('tickets:dashboard')
        else:
            messages.error(request, "Please correct the errors below.")

    return render(request, 'accounts/register.html', {'form': form})


@ratelimit(key='ip', rate='5/m', method='POST', block=True)
@require_http_methods(["GET", "POST"])
def login_view(request):
    """
    Login view with IP-based rate limiting.
    5 failed attempts per minute per IP triggers a block.
    This defends against brute force and credential stuffing.
    """
    if request.user.is_authenticated:
        return redirect('tickets:dashboard')

    form = SecureLoginForm(request, data=request.POST or None)

    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Redirect to the page they were trying to reach,
            # or fall back to the dashboard
            next_url = request.GET.get('next', 'tickets:dashboard')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, 'accounts/login.html', {'form': form})


@login_required
@require_http_methods(["POST"])
def logout_view(request):
    """
    Logout only accepts POST requests.
    Accepting GET would allow CSRF logout attacks where
    a malicious link silently logs the user out.
    """
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('accounts:login')


@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html', {'user': request.user})

# Create your views here.
