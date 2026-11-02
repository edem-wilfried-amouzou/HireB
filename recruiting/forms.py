from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from accounts.models import User

from .models import Application, Question, Recruitment, TestSubmission, TestTopic
from .uploads import validate_upload

ACCEPT = ".pdf,.png,.jpg,.jpeg,.txt,.md,.csv"


class RecruitmentForm(forms.ModelForm):
    closes_at = forms.DateTimeField(
        label="Date limite (facultatif)",
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = Recruitment
        fields = ["title", "description", "status", "closes_at", "anonymous", "test_enabled", "task_title", "test_hours", "test_instructions"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4}), "test_instructions": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.closes_at:
            self.initial["closes_at"] = timezone.localtime(self.instance.closes_at).strftime("%Y-%m-%dT%H:%M")

    def clean_test_hours(self):
        hours = self.cleaned_data["test_hours"]
        if not 1 <= hours <= 24 * 30:
            raise forms.ValidationError("Choisissez un délai entre 1 heure et 30 jours.")
        return hours


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ["label", "kind", "required", "choices", "position"]
        widgets = {"position": forms.HiddenInput, "choices": forms.Textarea(attrs={"rows": 3})}

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("kind") == Question.Kind.CHOICE and not (cleaned.get("choices") or "").strip():
            self.add_error("choices", "Indiquez au moins deux options, une par ligne.")
        return cleaned


QuestionFormSet = inlineformset_factory(Recruitment, Question, form=QuestionForm, extra=0, can_delete=True)
TopicFormSet = inlineformset_factory(Recruitment, TestTopic, fields=["title", "brief"], extra=0, can_delete=True,
                                     widgets={"brief": forms.Textarea(attrs={"rows": 3})})


class ApplicationForm(forms.Form):
    # Section « Contact » : toujours demandée, masquée à l'équipe si l'anonymat est activé.
    full_name = forms.CharField(label="Nom complet", max_length=150)
    email = forms.EmailField(label="Adresse email")
    phone = forms.CharField(label="Téléphone", max_length=30, required=False)
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))

    def __init__(self, recruitment, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recruitment = recruitment
        self.fields["full_name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["phone"].widget.attrs["autocomplete"] = "tel"
        self.questions = list(recruitment.questions.all())
        for q in self.questions:
            self.fields[f"q_{q.pk}"] = self._build(q)
        if recruitment.test_enabled and recruitment.topics.all():
            self.fields["topic"] = forms.ModelChoiceField(
                label="Thème", queryset=recruitment.topics.all(), widget=forms.RadioSelect, empty_label=None
            )

    @property
    def contact_fields(self):
        return [self["full_name"], self["email"], self["phone"]]

    @property
    def question_fields(self):
        return [self[f"q_{q.pk}"] for q in self.questions]

    @staticmethod
    def _build(q):
        opts = {"label": q.label, "required": q.required}
        if q.kind == Question.Kind.LONG:
            return forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), max_length=5000, **opts)
        if q.kind == Question.Kind.CHOICE:
            return forms.ChoiceField(choices=[(c, c) for c in q.choice_list], widget=forms.RadioSelect, **opts)
        if q.kind == Question.Kind.FILE:
            return forms.FileField(validators=[validate_upload], widget=forms.ClearableFileInput(attrs={"accept": ACCEPT}), **opts)
        return forms.CharField(max_length=300, **opts)

    def clean_website(self):
        if self.cleaned_data["website"]:
            raise forms.ValidationError("Envoi refusé.")
        return ""

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if Application.objects.filter(recruitment=self.recruitment, email=email).exists():
            raise forms.ValidationError("Une candidature existe déjà avec cet email.")
        return email


class TestSubmitForm(forms.Form):
    email = forms.EmailField(label="Email utilisé pour candidater")
    file = forms.FileField(label="Votre travail", validators=[validate_upload],
                           widget=forms.ClearableFileInput(attrs={"accept": ACCEPT}),
                           help_text="PDF, PNG, JPG, TXT, MD ou CSV.")
    note = forms.CharField(label="Message", required=False, max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, recruitment, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recruitment = recruitment
        self.application = None
        self.fields["email"].widget.attrs["autocomplete"] = "email"

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").strip().lower()
        if not email:
            return cleaned
        if not self.recruitment.is_accepting:
            raise forms.ValidationError("Ce recrutement est clôturé : il n'est plus possible de rendre un travail.")
        app = Application.objects.filter(recruitment=self.recruitment, email=email, topic__isnull=False).first()
        if app is None:
            raise forms.ValidationError("Aucun travail en attente pour cet email.")
        if TestSubmission.objects.filter(application=app).exists():
            raise forms.ValidationError("Un travail a déjà été rendu avec cet email.")
        if app.test_deadline and timezone.now() > app.test_deadline:
            raise forms.ValidationError("Le délai pour rendre ce travail est dépassé.")
        self.application = app
        return cleaned


class InviteForm(forms.Form):
    username = forms.CharField(label="Nom d'utilisateur du collaborateur", max_length=31)

    def __init__(self, recruitment, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.recruitment = recruitment
        self.invitee = None
        self.fields["username"].widget.attrs.update({"autocapitalize": "none", "autocomplete": "off", "placeholder": "@nom_utilisateur"})

    def clean_username(self):
        value = self.cleaned_data["username"].strip().lstrip("@").lower()
        user = User.objects.filter(username=value, is_active=True).first()
        if user is None:
            raise forms.ValidationError("Aucun utilisateur avec ce nom d'utilisateur.")
        r = self.recruitment
        if user.pk == r.owner_id or r.members.filter(user=user).exists():
            raise forms.ValidationError("Cette personne a déjà accès.")
        self.invitee = user
        return value
