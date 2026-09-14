from django.shortcuts import render, redirect


def landing(request):
    """
    Public marketing landing page served at /.
    Authenticated users are sent straight to their dashboard.
    """
    if request.user.is_authenticated:
        return redirect('tickets:dashboard')
    return render(request, 'landing.html')
