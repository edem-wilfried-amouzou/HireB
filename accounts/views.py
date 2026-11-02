from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render

from recruiting.security import too_many

from .forms import ProfileForm, SignupForm, StyledPasswordChangeForm


class ThrottledLoginView(LoginView):
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if too_many(request, "login", limit=10, window=600):
            return too_many_response(request)
        return super().post(request, *args, **kwargs)


def too_many_response(request):
    return render(request, "throttled.html", status=429)


def signup(request):
    if request.user.is_authenticated:
        return redirect("recruiting:dashboard")
    if request.method == "POST" and too_many(request, "signup", limit=10, window=3600):
        return too_many_response(request)
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Compte créé. Lancez votre premier recrutement.")
        return redirect("recruiting:create")
    return render(request, "accounts/signup.html", {"form": form})


@login_required
def profile(request):
    profile_form = ProfileForm(instance=request.user)
    password_form = StyledPasswordChangeForm(request.user)
    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profil mis à jour.")
                return redirect("accounts:profile")
        elif "save_password" in request.POST:
            password_form = StyledPasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)  # reste connecté
                messages.success(request, "Mot de passe modifié.")
                return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"profile_form": profile_form, "password_form": password_form})
