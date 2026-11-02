from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import User, username_validator


class LoginForm(AuthenticationForm):
    """Connexion avec le nom d'utilisateur ou l'email."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nom d'utilisateur ou email"
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autofocus": True, "autocapitalize": "none"})
        self.fields["password"].label = "Mot de passe"

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lower()
        if "@" in value:
            found = User.objects.filter(email__iexact=value).values_list("username", flat=True).first()
            return found or value
        return value


class SignupForm(forms.ModelForm):
    password = forms.CharField(label="Mot de passe", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = User
        fields = ("name", "username", "email", "phone")
        labels = {"name": "Votre nom", "username": "Nom d'utilisateur", "email": "Adresse email", "phone": "Téléphone"}
        help_texts = {"username": "Sert à vous inviter dans une équipe. Il ne pourra plus être modifié."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = False
        self.fields["username"].widget.attrs.update({"autocapitalize": "none", "autocomplete": "username"})
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"

    def clean_website(self):
        if self.cleaned_data["website"]:
            raise forms.ValidationError("Envoi refusé.")
        return ""

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lower()
        username_validator(value)
        if User.objects.filter(username=value).exists():
            raise forms.ValidationError("Ce nom d'utilisateur est déjà pris.")
        return value

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cet email.")
        return email

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("password")
        if pwd:
            temp = User(username=cleaned.get("username", ""), name=cleaned.get("name", ""), email=cleaned.get("email", ""))
            try:
                password_validation.validate_password(pwd, temp)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    """Le nom d'utilisateur n'est volontairement pas modifiable."""

    class Meta:
        model = User
        fields = ("name", "email", "phone", "email_notifications")
        labels = {"name": "Nom", "email": "Adresse email", "phone": "Téléphone"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = False

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cet email est déjà utilisé par un autre compte.")
        return email


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Mot de passe actuel"
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmer le nouveau mot de passe"
        for f in self.fields.values():
            f.help_text = ""
