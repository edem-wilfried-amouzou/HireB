import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import ApplicationForm, InviteForm, QuestionFormSet, RecruitmentForm, TestSubmitForm, TopicFormSet
from .models import Answer, Application, Invitation, Member, Notification, Recruitment, TestSubmission
from .security import too_many
from .uploads import CONTENT_TYPES, ext_of, preview_kind


# ---------- Helpers ----------

def _accessible(user):
    return Recruitment.objects.filter(
        Q(owner=user) | Q(pk__in=Member.objects.filter(user=user).values("recruitment_id"))
    )


def _get(request, pk, owner_only=False):
    qs = Recruitment.objects.filter(owner=request.user) if owner_only else _accessible(request.user)
    return get_object_or_404(qs.select_related("owner"), pk=pk)


def _too_many(request):
    return render(request, "throttled.html", status=429)


# ---------- Pages publiques ----------

def landing(request):
    return render(request, "landing.html")


def apply(request, public_id):
    r = get_object_or_404(Recruitment.objects.select_related("owner").prefetch_related("questions", "topics"), public_id=public_id)
    if not r.is_accepting:
        return render(request, "recruiting/apply_closed.html", {"r": r})
    if request.method == "POST" and too_many(request, "apply", limit=30, window=3600):
        return _too_many(request)
    form = ApplicationForm(r, request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            app = services.create_application(form)
        except IntegrityError:
            form.add_error("email", "Une candidature existe déjà avec cet email.")
        else:
            services.on_application_created(request, app)
            url = reverse("recruiting:thanks", args=[r.public_id])
            return redirect(url + ("?t=1" if app.topic_id else ""))
    return render(request, "recruiting/apply.html", {"r": r, "form": form})


def thanks(request, public_id):
    r = get_object_or_404(Recruitment, public_id=public_id)
    return render(request, "recruiting/thanks.html", {
        "r": r, "with_test": request.GET.get("t") == "1", "test_done": request.GET.get("k") == "test",
    })


def submit_test(request, public_id):
    r = get_object_or_404(Recruitment.objects.select_related("owner"), public_id=public_id, test_enabled=True)
    if request.method == "POST" and too_many(request, "test", limit=20, window=600):
        return _too_many(request)
    form = TestSubmitForm(r, request.POST or None, request.FILES or None, initial={"email": request.GET.get("email", "")})
    if request.method == "POST" and form.is_valid():
        try:
            TestSubmission.objects.create(application=form.application, file=form.cleaned_data["file"], note=form.cleaned_data["note"])
        except IntegrityError:
            form.add_error(None, "Un travail a déjà été rendu avec cet email.")
        else:
            services.on_test_submitted(request, form.application)
            return redirect(reverse("recruiting:thanks", args=[r.public_id]) + "?k=test")
    return render(request, "recruiting/test_submit.html", {"r": r, "form": form})


# ---------- Espace recruteur ----------

@login_required
def dashboard(request):
    items = list(_accessible(request.user).annotate(n_apps=Count("applications")).select_related("owner"))
    ids = [r.pk for r in items]
    stats = {
        "open": sum(1 for r in items if r.is_accepting),
        "apps": sum(r.n_apps for r in items),
        "to_review": TestSubmission.objects.filter(application__recruitment_id__in=ids, application__status=Application.Status.NEW).count(),
    }
    return render(request, "recruiting/dashboard.html", {"items": items, "stats": stats})


@login_required
def recruitment_edit(request, pk=None):
    r = _get(request, pk, owner_only=True) if pk else Recruitment(owner=request.user)
    form = RecruitmentForm(request.POST or None, instance=r)
    questions = QuestionFormSet(request.POST or None, instance=r, prefix="questions")
    topics = TopicFormSet(request.POST or None, instance=r, prefix="topics")
    if request.method == "POST" and form.is_valid() and questions.is_valid() and topics.is_valid():
        with transaction.atomic():
            r = form.save()
            questions.instance = topics.instance = r
            questions.save()
            topics.save()
        messages.success(request, "Recrutement enregistré.")
        return redirect("recruiting:detail", pk=r.pk)
    return render(request, "recruiting/recruitment_form.html", {
        "r": r, "form": form, "questions": questions, "topics": topics, "is_new": pk is None,
    })


@login_required
@require_POST
def recruitment_delete(request, pk):
    _get(request, pk, owner_only=True).delete()
    messages.success(request, "Recrutement supprimé.")
    return redirect("recruiting:dashboard")


@login_required
@require_POST
def recruitment_toggle(request, pk):
    r = _get(request, pk, owner_only=True)
    if r.status == Recruitment.Status.OPEN and r.is_accepting:
        r.status = Recruitment.Status.CLOSED
        messages.success(request, "Candidatures clôturées. Les candidats ne peuvent plus postuler.")
    else:
        r.status, r.closes_at = Recruitment.Status.OPEN, None
        messages.success(request, "Candidatures rouvertes.")
    r.save(update_fields=["status", "closes_at"])
    return redirect("recruiting:detail", pk=r.pk)


@login_required
def recruitment_detail(request, pk):
    r = _get(request, pk)
    status = request.GET.get("statut", "")
    counts = dict(r.applications.order_by().values_list("status").annotate(n=Count("id")))
    qs = r.applications.select_related("topic", "submission")
    if status in Application.Status.values:
        qs = qs.filter(status=status)
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "recruiting/recruitment_detail.html", {
        "r": r, "page": page, "status": status, "counts": counts, "total": sum(counts.values()),
        "submitted": TestSubmission.objects.filter(application__recruitment=r).count() if r.test_enabled else 0,
        "statuses": Application.Status.choices, "is_owner": r.owner_id == request.user.id,
        "public_url": request.build_absolute_uri(r.get_public_path()),
    })


@login_required
def application_detail(request, pk, app_pk):
    r = _get(request, pk)
    app = get_object_or_404(r.applications.select_related("topic", "submission"), pk=app_pk)
    is_owner = r.owner_id == request.user.id
    if request.method == "POST":
        if not is_owner:
            raise PermissionDenied
        action = request.POST.get("action")
        S = Application.Status
        transitions = {"shortlist": (S.SHORTLISTED, True), "select": (S.SELECTED, True), "reject": (S.REJECTED, False), "reset": (S.NEW, False)}
        if action in transitions:
            new_status, reveal = transitions[action]
            services.set_status(app, new_status, reveal, notify_candidate=request.POST.get("notify") == "on")
            messages.success(request, "Statut mis à jour." + (" L'identité est maintenant visible." if reveal and r.anonymous else ""))
        return redirect("recruiting:application", pk=r.pk, app_pk=app.pk)
    return render(request, "recruiting/application_detail.html", {
        "r": r, "app": app, "answers": app.answers.select_related("question"), "is_owner": is_owner,
    })


# ---------- Aperçu des fichiers (sans téléchargement) ----------

def _file_object(request, kind, pk):
    if kind == "answer":
        obj = get_object_or_404(Answer.objects.select_related("application__recruitment"), pk=pk)
    elif kind == "test":
        obj = get_object_or_404(TestSubmission.objects.select_related("application__recruitment"), pk=pk)
    else:
        raise Http404
    if not obj.file or not _accessible(request.user).filter(pk=obj.application.recruitment_id).exists():
        raise Http404
    return obj


@login_required
def preview(request, kind, pk):
    obj = _file_object(request, kind, pk)
    app = obj.application
    pk_kind = preview_kind(obj.file.name)
    text, truncated = "", False
    if pk_kind == "text":
        with obj.file.open("rb") as fh:
            raw = fh.read(100_001)
        truncated = len(raw) > 100_000
        text = raw[:100_000].decode("utf-8", errors="replace")
    return render(request, "recruiting/preview.html", {
        "r": app.recruitment, "app": app, "obj": obj, "kind": kind, "pk_kind": pk_kind, "text": text, "truncated": truncated,
        "raw_url": reverse("recruiting:raw", args=[kind, obj.pk]),
    })


@login_required
def raw(request, kind, pk):
    """Flux inline pour l'affichage (PDF/images). Le nom d'origine n'est jamais exposé."""
    obj = _file_object(request, kind, pk)
    ext = ext_of(obj.file.name)
    ctype = CONTENT_TYPES.get(ext)
    if not ctype:
        raise Http404
    resp = FileResponse(obj.file.open("rb"), as_attachment=False, content_type=ctype)
    resp["Content-Disposition"] = f'inline; filename="candidat-{obj.application.code}.{ext}"'
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "private, no-store"
    return resp


# ---------- Équipe & notifications ----------

@login_required
def team(request, pk):
    r = _get(request, pk, owner_only=True)
    form = InviteForm(r, request.POST or None)
    if request.method == "POST":
        if "revoke" in request.POST:
            r.invitations.filter(pk=request.POST["revoke"], status=Invitation.Status.PENDING).delete()
            messages.success(request, "Invitation annulée.")
            return redirect("recruiting:team", pk=r.pk)
        if "remove" in request.POST:
            member = r.members.filter(pk=request.POST["remove"]).select_related("user", "recruitment").first()
            if member:
                member.delete()
                services.member_removed(member)
                r.invitations.filter(invitee_id=member.user_id).delete()
                messages.success(request, "Collaborateur retiré.")
            return redirect("recruiting:team", pk=r.pk)
        if form.is_valid():
            inv, created = Invitation.objects.get_or_create(recruitment=r, invitee=form.invitee, defaults={"invited_by": request.user})
            if not created and inv.status == Invitation.Status.PENDING:
                messages.info(request, "Une invitation est déjà en attente pour cette personne.")
            else:
                if not created:  # ré-invitation après refus
                    inv.status, inv.responded_at, inv.invited_by = Invitation.Status.PENDING, None, request.user
                    inv.save(update_fields=["status", "responded_at", "invited_by"])
                services.send_invitation(request, inv)
                messages.success(request, f"Invitation envoyée à @{form.invitee.username}.")
            return redirect("recruiting:team", pk=r.pk)
    return render(request, "recruiting/team.html", {
        "r": r, "form": form,
        "members": r.members.select_related("user"),
        "invitations": r.invitations.filter(status=Invitation.Status.PENDING).select_related("invitee"),
    })


@login_required
def notifications(request):
    qs = request.user.notifications.select_related("invitation__recruitment", "invitation__invited_by")
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    to_mark = []
    for n in page:
        n.is_new = n.read_at is None
        pending = n.invitation_id and n.invitation.status == Invitation.Status.PENDING
        if n.is_new and not pending:
            to_mark.append(n.pk)
    if to_mark:
        Notification.objects.filter(pk__in=to_mark).update(read_at=timezone.now())
    return render(request, "recruiting/notifications.html", {"page": page})


@login_required
@require_POST
def invitation_respond(request, pk):
    inv = get_object_or_404(Invitation.objects.select_related("recruitment", "invited_by", "invitee"),
                            pk=pk, invitee=request.user, status=Invitation.Status.PENDING)
    accept = request.POST.get("action") == "accept"
    services.answer_invitation(request, inv, accept)
    if accept:
        messages.success(request, "Invitation acceptée : vous avez maintenant accès au recrutement.")
        return redirect("recruiting:detail", pk=inv.recruitment_id)
    messages.success(request, "Invitation refusée.")
    return redirect("recruiting:notifications")
