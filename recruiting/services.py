import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from .models import Answer, Application, Invitation, Member, Notification, Question, Recruitment

log = logging.getLogger(__name__)

FOOTER = (
    "\n\n—\n{site}\nVous ne voyez pas nos emails ? Pensez à vérifier votre dossier spam / courriers indésirables."
)


# ---------- Utilitaires ----------

def abs_url(request, name, *args):
    path = reverse(name, args=args)
    if request is not None:
        return request.build_absolute_uri(path)
    return settings.SITE_URL.rstrip("/") + path


def _send(subject, body, to):
    """Un email raté ne doit jamais bloquer l'action de l'utilisateur."""
    try:
        send_mail(f"[{settings.SITE_NAME}] {subject}", body + FOOTER.format(site=settings.SITE_NAME), None, [to])
    except Exception:
        log.exception("Échec d'envoi d'email à %s", to)


def notify(user, message, url="", invitation=None, subject=None, body=None):
    """Notification interne + email (si l'utilisateur ne l'a pas désactivé)."""
    Notification.objects.create(user=user, message=message, url=url, invitation=invitation)
    if subject and user.email and user.email_notifications:
        _send(subject, f"Bonjour {user.name},\n\n{body or message}", user.email)


# ---------- Candidatures ----------

def create_application(form):
    r = form.recruitment
    cd = form.cleaned_data
    topic = cd.get("topic")
    with transaction.atomic():
        Recruitment.objects.select_for_update().filter(pk=r.pk).first()
        last = Application.objects.filter(recruitment=r).aggregate(m=Max("number"))["m"] or 0
        app = Application.objects.create(
            recruitment=r,
            number=last + 1,
            full_name=cd["full_name"].strip(),
            email=cd["email"],
            phone=cd.get("phone", ""),
            topic=topic,
            test_deadline=timezone.now() + timedelta(hours=r.test_hours) if topic else None,
        )
        for q in form.questions:
            value = cd.get(f"q_{q.pk}")
            if q.kind == Question.Kind.FILE:
                Answer.objects.create(application=app, question=q, file=value or None)
            else:
                Answer.objects.create(application=app, question=q, text=value or "")
    return app


def on_application_created(request, app):
    r = app.recruitment
    lines = [f"Bonjour {app.full_name},", "", f"Nous avons bien reçu votre candidature pour « {r.title} »."]
    if app.topic_id:
        url = abs_url(request, "recruiting:test", r.public_id)
        deadline = timezone.localtime(app.test_deadline)
        lines += ["", f"{r.task_title} — thème choisi : {app.topic.title}", f"À rendre avant le {deadline:%d/%m/%Y à %H:%M}."]
        if app.topic.brief:
            lines += ["", "Consignes du thème :", app.topic.brief]
        if r.test_instructions:
            lines += ["", "Consignes générales :", r.test_instructions]
        lines += ["", f"Pour rendre votre travail, ouvrez ce lien et saisissez cet email : {url}"]
    _send(f"Candidature reçue — {r.title}", "\n".join(lines), app.email)
    # Jamais le nom ici : en mode anonyme, display_name donne « Candidat 004 ».
    url = reverse("recruiting:application", args=[r.pk, app.pk])
    notify(r.owner, f"Nouvelle candidature : {app.display_name} — {r.title}", url,
           subject=f"Nouvelle candidature — {r.title}",
           body=f"{app.display_name} vient de candidater à « {r.title} ».\n\nVoir la candidature : {abs_url(request, 'recruiting:application', r.pk, app.pk)}")


def on_test_submitted(request, app):
    r = app.recruitment
    _send(f"Travail reçu — {r.title}",
          f"Bonjour {app.full_name},\n\nVotre travail pour « {r.title} » ({r.task_title}) a bien été reçu. Merci !", app.email)
    url = reverse("recruiting:application", args=[r.pk, app.pk])
    notify(r.owner, f"Travail rendu : {app.display_name} — {r.title}", url,
           subject=f"Travail rendu — {r.title}",
           body=f"{app.display_name} a rendu son travail pour « {r.title} ».\n\nVoir : {abs_url(request, 'recruiting:application', r.pk, app.pk)}")


STATUS_MAILS = {
    Application.Status.SHORTLISTED: "Bonne nouvelle : votre candidature pour « {t} » a été présélectionnée. Nous reviendrons vers vous très prochainement.",
    Application.Status.SELECTED: "Félicitations : votre candidature pour « {t} » a été retenue. Nous vous contacterons pour la suite.",
    Application.Status.REJECTED: "Merci d'avoir candidaté à « {t} ». Après examen, nous ne pouvons pas donner suite à votre candidature. Nous vous souhaitons plein succès.",
}


def set_status(app, new_status, reveal, notify_candidate):
    app.status = new_status
    if reveal:
        app.identity_revealed = True
    app.save(update_fields=["status", "identity_revealed"])
    template = STATUS_MAILS.get(new_status)
    if notify_candidate and template:
        _send(f"Votre candidature — {app.recruitment.title}",
              f"Bonjour {app.full_name},\n\n" + template.format(t=app.recruitment.title), app.email)


def send_deadline_reminders():
    """À lancer par cron toutes les heures : `python manage.py send_reminders`."""
    now = timezone.now()
    qs = (Application.objects.filter(topic__isnull=False, submission__isnull=True, reminder_sent=False,
                                     test_deadline__gt=now, test_deadline__lte=now + timedelta(hours=24),
                                     recruitment__status=Recruitment.Status.OPEN, recruitment__test_enabled=True)
          .select_related("recruitment"))
    n = 0
    for app in qs:
        r = app.recruitment
        deadline = timezone.localtime(app.test_deadline)
        _send(f"Rappel : travail à rendre — {r.title}",
              f"Bonjour {app.full_name},\n\nIl vous reste moins de 24 h pour rendre votre travail pour « {r.title} » "
              f"(avant le {deadline:%d/%m/%Y à %H:%M}).\n\nRendre mon travail : {abs_url(None, 'recruiting:test', r.public_id)}",
              app.email)
        app.reminder_sent = True
        app.save(update_fields=["reminder_sent"])
        n += 1
    return n


# ---------- Équipe ----------

def send_invitation(request, inv):
    r = inv.recruitment
    notify(inv.invitee, f"{inv.invited_by.name} vous invite à consulter « {r.title} »", reverse("recruiting:notifications"),
           invitation=inv, subject=f"Invitation — {r.title}",
           body=f"{inv.invited_by.name} (@{inv.invited_by.username}) vous invite à consulter les réponses du recrutement « {r.title} ».\n\n"
                f"Acceptez ou refusez depuis vos notifications : {abs_url(request, 'recruiting:notifications')}")


def answer_invitation(request, inv, accept):
    r = inv.recruitment
    inv.status = Invitation.Status.ACCEPTED if accept else Invitation.Status.DECLINED
    inv.responded_at = timezone.now()
    inv.save(update_fields=["status", "responded_at"])
    inv.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
    who = f"{inv.invitee.name} (@{inv.invitee.username})"
    if accept:
        Member.objects.get_or_create(recruitment=r, user=inv.invitee)
        notify(inv.invited_by, f"{who} a accepté l'invitation — {r.title}", reverse("recruiting:team", args=[r.pk]),
               subject=f"Invitation acceptée — {r.title}", body=f"{who} a accepté votre invitation sur « {r.title} ».")
    else:
        notify(inv.invited_by, f"{who} a refusé l'invitation — {r.title}", reverse("recruiting:team", args=[r.pk]),
               subject=f"Invitation refusée — {r.title}", body=f"{who} a refusé votre invitation sur « {r.title} ».")


def member_removed(member):
    notify(member.user, f"Votre accès à « {member.recruitment.title} » a été retiré.")
