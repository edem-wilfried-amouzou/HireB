import os
import secrets
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.urls import reverse
from django.utils import timezone


def private_storage():
    if getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""):
        from storages.backends.s3 import S3Storage

        return S3Storage()
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def private_upload(instance, filename):
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


def new_public_id():
    return secrets.token_urlsafe(8)


class Recruitment(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Ouvert"
        CLOSED = "closed", "Clôturé"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recruitments")
    title = models.CharField("intitulé du poste", max_length=160)
    description = models.TextField("description", blank=True)
    public_id = models.CharField(max_length=16, unique=True, default=new_public_id, editable=False)
    status = models.CharField("statut", max_length=10, choices=Status.choices, default=Status.OPEN)
    closes_at = models.DateTimeField("date limite", null=True, blank=True)

    anonymous = models.BooleanField(
        "Candidatures anonymes",
        default=False,
        help_text="Nom, email, téléphone et noms de fichiers restent masqués (codes 001, 002…) jusqu'à la présélection d'un candidat.",
    )
    test_enabled = models.BooleanField("Demander un travail à rendre (test, design, document…)", default=False)
    task_title = models.CharField("nom de l'étape", max_length=80, default="Test", help_text="Ex. : Test technique, Conception de design…")
    test_hours = models.PositiveSmallIntegerField("délai pour rendre le travail (heures)", default=48)
    test_instructions = models.TextField("consignes générales", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["owner", "-created_at"])]

    def __str__(self):
        return self.title

    @property
    def is_accepting(self):
        if self.status != self.Status.OPEN:
            return False
        return self.closes_at is None or self.closes_at > timezone.now()

    def get_public_path(self):
        return reverse("recruiting:apply", args=[self.public_id])


class Question(models.Model):
    class Kind(models.TextChoices):
        SHORT = "short", "Réponse courte"
        LONG = "long", "Réponse longue"
        CHOICE = "choice", "Choix unique"
        FILE = "file", "Fichier (CV, lettre…)"

    recruitment = models.ForeignKey(Recruitment, on_delete=models.CASCADE, related_name="questions")
    label = models.CharField("question", max_length=300)
    kind = models.CharField("type", max_length=10, choices=Kind.choices, default=Kind.SHORT)
    required = models.BooleanField("obligatoire", default=True)
    choices = models.TextField("options (une par ligne)", blank=True)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.label

    @property
    def choice_list(self):
        return [c.strip() for c in self.choices.splitlines() if c.strip()]


class TestTopic(models.Model):
    recruitment = models.ForeignKey(Recruitment, on_delete=models.CASCADE, related_name="topics")
    title = models.CharField("thème", max_length=200)
    brief = models.TextField("consignes du sujet", blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title


class Application(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Nouvelle"
        SHORTLISTED = "shortlisted", "Présélectionnée"
        SELECTED = "selected", "Retenue"
        REJECTED = "rejected", "Refusée"

    recruitment = models.ForeignKey(Recruitment, on_delete=models.CASCADE, related_name="applications")
    number = models.PositiveIntegerField()
    full_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    identity_revealed = models.BooleanField(default=False)
    topic = models.ForeignKey(TestTopic, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    test_deadline = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["number"]
        constraints = [
            models.UniqueConstraint(fields=["recruitment", "email"], name="uniq_application_email"),
            models.UniqueConstraint(fields=["recruitment", "number"], name="uniq_application_number"),
        ]
        indexes = [models.Index(fields=["recruitment", "status"])]

    def __str__(self):
        return f"{self.recruitment_id}-{self.code}"

    @property
    def code(self):
        return f"{self.number:03d}"

    @property
    def shows_identity(self):
        return (not self.recruitment.anonymous) or self.identity_revealed

    @property
    def display_name(self):
        return self.full_name if self.shows_identity else f"Candidat {self.code}"


class Answer(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="answers")
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="answers")
    text = models.TextField(blank=True)
    file = models.FileField(upload_to=private_upload, storage=private_storage, blank=True, null=True)

    class Meta:
        ordering = ["question__position", "question_id"]
        constraints = [models.UniqueConstraint(fields=["application", "question"], name="uniq_answer")]


class TestSubmission(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name="submission")
    file = models.FileField(upload_to=private_upload, storage=private_storage)
    note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)


class Member(models.Model):
    """Collaborateur en lecture seule sur un recrutement."""

    recruitment = models.ForeignKey(Recruitment, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["recruitment", "user"], name="uniq_member")]


class Invitation(models.Model):
    """Invitation envoyée à un utilisateur existant (par nom d'utilisateur)."""

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        ACCEPTED = "accepted", "Acceptée"
        DECLINED = "declined", "Refusée"

    recruitment = models.ForeignKey(Recruitment, on_delete=models.CASCADE, related_name="invitations")
    invitee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="invitations")
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["recruitment", "invitee"], name="uniq_invitation")]


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=300)
    url = models.CharField(max_length=300, blank=True)
    invitation = models.ForeignKey(Invitation, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["user", "read_at"])]
