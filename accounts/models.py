from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

username_validator = RegexValidator(
    r"^[a-z0-9_]{3,30}$", "3 à 30 caractères : lettres minuscules, chiffres et « _ » uniquement."
)


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, username, email, password, **extra):
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        if not email:
            raise ValueError("L'email est obligatoire.")
        user = self.model(username=username.lower(), email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, username, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(username, email, password, **extra)

    def create_superuser(self, username, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self._create(username, email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField("nom d'utilisateur", max_length=30, unique=True, validators=[username_validator])
    email = models.EmailField("email", unique=True)
    name = models.CharField("nom", max_length=120)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    email_notifications = models.BooleanField("Recevoir mes notifications par email", default=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email", "name"]

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        self.username = (self.username or "").lower()
        self.email = (self.email or "").lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.name.split(" ")[0] if self.name else self.username
