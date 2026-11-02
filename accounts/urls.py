from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import LoginForm

app_name = "accounts"

urlpatterns = [
    path("inscription/", views.signup, name="signup"),
    path("connexion/", views.ThrottledLoginView.as_view(authentication_form=LoginForm), name="login"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="logout"),
    path("profil/", views.profile, name="profile"),
    path("mot-de-passe/oublie/", auth_views.PasswordResetView.as_view(
        email_template_name="registration/password_reset_email.txt",
        subject_template_name="registration/password_reset_subject.txt",
        success_url=reverse_lazy("accounts:password_reset_done")), name="password_reset"),
    path("mot-de-passe/oublie/envoye/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("mot-de-passe/reinitialiser/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        success_url=reverse_lazy("accounts:password_reset_complete")), name="password_reset_confirm"),
    path("mot-de-passe/termine/", auth_views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
