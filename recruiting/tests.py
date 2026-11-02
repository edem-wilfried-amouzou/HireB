import re
import tempfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from . import services
from .models import Application, Invitation, Member, Notification, Question, Recruitment, TestTopic

TMP = tempfile.mkdtemp()
PWD = "unmotdepasse-solide-91"
PDF = b"%PDF-1.4 contenu"


def pdf(name="cv-ama.pdf"):
    return SimpleUploadedFile(name, PDF)


def mkuser(username, **kw):
    return User.objects.create_user(username, kw.pop("email", f"{username}@example.com"), PWD, name=kw.pop("name", username.title()), **kw)


@override_settings(PRIVATE_MEDIA_ROOT=TMP)
class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = mkuser("boss", name="Boss")
        self.r = Recruitment.objects.create(owner=self.owner, title="Dev Django", anonymous=True, test_enabled=True, test_hours=48)
        self.q = Question.objects.create(recruitment=self.r, label="Pourquoi vous ?", kind=Question.Kind.LONG)
        self.cv = Question.objects.create(recruitment=self.r, label="CV", kind=Question.Kind.FILE)
        self.topic = TestTopic.objects.create(recruitment=self.r, title="API REST", brief="Faites une API")

    def apply(self, email="ama@example.com", name="Ama K.", phone="+22890000000"):
        return self.client.post(reverse("recruiting:apply", args=[self.r.public_id]), {
            "full_name": name, "email": email, "phone": phone, f"q_{self.q.pk}": "Parce que.", "topic": self.topic.pk,
            f"q_{self.cv.pk}": pdf(),
        })


class AccountTests(Base):
    def test_signup_with_username_and_login_by_username_or_email(self):
        r = self.client.post(reverse("accounts:signup"), {"name": "Neo", "username": "Neo_1", "email": "NEO@x.com", "password": PWD})
        self.assertEqual(r.status_code, 302)
        self.client.logout()
        self.assertTrue(self.client.login(username="neo_1", password=PWD))
        self.client.logout()
        resp = self.client.post(reverse("accounts:login"), {"username": "NEO@x.com", "password": PWD})
        self.assertEqual(resp.status_code, 302)

    def test_duplicate_and_invalid_username(self):
        bad = self.client.post(reverse("accounts:signup"), {"name": "X", "username": "boss", "email": "x@x.com", "password": PWD})
        self.assertContains(bad, "déjà pris")
        bad = self.client.post(reverse("accounts:signup"), {"name": "X", "username": "a b", "email": "x@x.com", "password": PWD})
        self.assertContains(bad, "lettres minuscules")

    def test_profile_edit_keeps_username_and_changes_password(self):
        self.client.force_login(self.owner)
        self.client.post(reverse("accounts:profile"), {"save_profile": "1", "name": "Nouveau Nom", "email": "new@x.com", "phone": "123",
                                                       "username": "hacker"})
        self.owner.refresh_from_db()
        self.assertEqual((self.owner.name, self.owner.email, self.owner.username), ("Nouveau Nom", "new@x.com", "boss"))
        r = self.client.post(reverse("accounts:profile"), {"save_password": "1", "old_password": PWD,
                                                           "new_password1": "autre-mot-de-passe-77", "new_password2": "autre-mot-de-passe-77"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get(reverse("recruiting:dashboard")).status_code, 200)  # toujours connecté
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("autre-mot-de-passe-77"))

    def test_password_reset_email(self):
        self.client.post(reverse("accounts:password_reset"), {"email": "boss@example.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("spams", mail.outbox[0].body)

    def test_login_is_throttled(self):
        for _ in range(10):
            self.client.post(reverse("accounts:login"), {"username": "boss", "password": "faux"})
        self.assertEqual(self.client.post(reverse("accounts:login"), {"username": "boss", "password": "faux"}).status_code, 429)


class ApplicationTests(Base):
    def test_apply_numbers_candidates_and_emails(self):
        self.assertEqual(self.apply().status_code, 302)
        self.apply("kofi@example.com", "Kofi")
        self.assertEqual(list(Application.objects.values_list("number", flat=True)), [1, 2])
        candidate_mail = [m for m in mail.outbox if m.to == ["ama@example.com"]][0]
        self.assertIn("API REST", candidate_mail.body)
        self.assertIn("spam", candidate_mail.body)
        self.assertEqual(self.apply().status_code, 200)  # doublon refusé
        self.assertEqual(Application.objects.count(), 2)

    def test_anonymous_hides_everything(self):
        self.apply()
        app = Application.objects.get()
        self.client.force_login(self.owner)
        pages = [reverse("recruiting:application", args=[self.r.pk, app.pk]), reverse("recruiting:detail", args=[self.r.pk]),
                 reverse("recruiting:notifications"), reverse("recruiting:dashboard")]
        for url in pages:
            body = self.client.get(url).content.decode()
            for secret in ("Ama K.", "ama@example.com", "+22890000000", "cv-ama"):
                self.assertNotIn(secret, body, f"{secret} visible sur {url}")
        self.assertIn("Candidat 001", self.client.get(pages[0]).content.decode())
        # Les emails à l'équipe ne contiennent jamais l'identité non plus.
        for m in mail.outbox:
            if m.to == ["boss@example.com"]:
                self.assertNotIn("Ama", m.body + m.subject)
        self.assertTrue(Notification.objects.filter(user=self.owner, message__contains="Candidat 001").exists())
        self.client.post(pages[0], {"action": "shortlist"})
        body = self.client.get(pages[0]).content.decode()
        self.assertIn("Ama K.", body)
        self.assertIn("ama@example.com", body)

    def test_status_email_is_optional(self):
        self.apply()
        app = Application.objects.get()
        self.client.force_login(self.owner)
        url = reverse("recruiting:application", args=[self.r.pk, app.pk])
        mail.outbox.clear()
        self.client.post(url, {"action": "shortlist"})
        self.assertEqual(len(mail.outbox), 0)
        self.client.post(url, {"action": "select", "notify": "on"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["ama@example.com"])

    def test_not_anonymous_shows_everything_and_code(self):
        Recruitment.objects.filter(pk=self.r.pk).update(anonymous=False)
        self.apply()
        app = Application.objects.get()
        self.client.force_login(self.owner)
        body = self.client.get(reverse("recruiting:application", args=[self.r.pk, app.pk])).content.decode()
        for visible in ("Ama K.", "ama@example.com", "001"):
            self.assertIn(visible, body)

    def test_apply_page_separates_contact_and_answers(self):
        body = self.client.get(reverse("recruiting:apply", args=[self.r.public_id])).content.decode()
        self.assertIn("Vos coordonnées", body)
        self.assertIn("Vos réponses", body)
        contact, answers = body.split("Vos réponses")
        self.assertNotIn("évitez de citer votre nom", contact.lower())  # le conseil n'apparaît pas dans « Contact »
        self.assertIn("évitez de citer votre nom", answers.lower())
        self.assertIn(reverse("recruiting:test", args=[self.r.public_id]), body)  # bouton « soumettre mon travail »

    def test_close_blocks_apply_and_submission_and_reopen(self):
        self.apply()
        self.client.force_login(self.owner)
        self.client.post(reverse("recruiting:toggle", args=[self.r.pk]))
        self.client.logout()
        self.assertContains(self.client.get(reverse("recruiting:apply", args=[self.r.public_id])), "ne pouvez plus postuler")
        resp = self.client.post(reverse("recruiting:test", args=[self.r.public_id]), {"email": "ama@example.com", "file": pdf("t.pdf")})
        self.assertContains(resp, "clôturé")
        self.client.force_login(self.owner)
        self.client.post(reverse("recruiting:toggle", args=[self.r.pk]))
        self.r.refresh_from_db()
        self.assertTrue(self.r.is_accepting)

    def test_deadline_in_the_past_closes(self):
        Recruitment.objects.filter(pk=self.r.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
        self.assertContains(self.client.get(reverse("recruiting:apply", args=[self.r.public_id])), "ne pouvez plus postuler")


class SubmissionAndFilesTests(Base):
    def test_submission_flow_deadline_and_emails(self):
        self.apply()
        url = reverse("recruiting:test", args=[self.r.public_id])
        mail.outbox.clear()
        ok = self.client.post(url, {"email": "ama@example.com", "file": pdf("t.pdf")})
        self.assertEqual(ok.status_code, 302)
        self.assertEqual({tuple(m.to) for m in mail.outbox}, {("ama@example.com",), ("boss@example.com",)})
        self.assertContains(self.client.post(url, {"email": "ama@example.com", "file": pdf("t.pdf")}), "déjà été rendu")
        self.apply("late@example.com", "Late")
        Application.objects.filter(email="late@example.com").update(test_deadline=timezone.now() - timedelta(hours=1))
        self.assertContains(self.client.post(url, {"email": "late@example.com", "file": pdf("t.pdf")}), "dépassé")

    def test_upload_validation(self):
        url = reverse("recruiting:apply", args=[self.r.public_id])
        base = {"full_name": "X", "email": "x@x.com", f"q_{self.q.pk}": "a", "topic": self.topic.pk}
        for bad in (SimpleUploadedFile("evil.exe", b"MZ"), SimpleUploadedFile("fake.pdf", b"not a pdf"),
                    SimpleUploadedFile("a.docx", b"PK")):
            resp = self.client.post(url, {**base, f"q_{self.cv.pk}": bad})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(Application.objects.count(), 0)

    def test_preview_inline_only_and_protected(self):
        self.apply()
        ans = Application.objects.get().answers.get(question=self.cv)
        page, raw = (reverse("recruiting:preview", args=["answer", ans.pk]), reverse("recruiting:raw", args=["answer", ans.pk]))
        self.assertEqual(self.client.get(raw).status_code, 302)  # connexion requise
        stranger = mkuser("stranger")
        self.client.force_login(stranger)
        self.assertEqual(self.client.get(page).status_code, 404)
        self.assertEqual(self.client.get(raw).status_code, 404)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(page), "<iframe")
        resp = self.client.get(raw)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Disposition"].startswith("inline"))
        self.assertIn("candidat-001", resp["Content-Disposition"])
        self.assertNotIn("cv-ama", resp["Content-Disposition"])
        self.assertEqual(resp["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("attachment", resp["Content-Disposition"])

    def test_text_preview_is_escaped(self):
        self.apply()
        self.client.post(reverse("recruiting:test", args=[self.r.public_id]), {"email": "ama@example.com", "file": SimpleUploadedFile("n.txt", b"<script>alert(1)</script>")})
        sub = Application.objects.get().submission
        self.client.force_login(self.owner)
        body = self.client.get(reverse("recruiting:preview", args=["test", sub.pk])).content.decode()
        self.assertNotIn("<script>alert(1)", body)
        self.assertIn("&lt;script&gt;", body)

    def test_reminders_sent_once(self):
        self.apply()
        Application.objects.update(test_deadline=timezone.now() + timedelta(hours=5))
        mail.outbox.clear()
        self.assertEqual(services.send_deadline_reminders(), 1)
        self.assertEqual(services.send_deadline_reminders(), 0)
        self.assertEqual(mail.outbox[0].to, ["ama@example.com"])


class TeamTests(Base):
    def test_invite_by_username_notification_accept_and_read_only(self):
        self.apply()
        colleague = mkuser("colleague", name="Colleague")
        self.client.force_login(self.owner)
        team = reverse("recruiting:team", args=[self.r.pk])
        self.assertContains(self.client.post(team, {"username": "inconnu"}), "Aucun utilisateur")
        self.client.post(team, {"username": "@Colleague"})
        inv = Invitation.objects.get()
        self.assertEqual(inv.status, Invitation.Status.PENDING)
        self.assertTrue(Notification.objects.filter(user=colleague, invitation=inv).exists())
        self.assertTrue(any(m.to == ["colleague@example.com"] for m in mail.outbox))
        self.client.force_login(colleague)
        self.assertContains(self.client.get(reverse("recruiting:notifications")), "Accepter")
        self.assertContains(self.client.get(reverse("recruiting:dashboard")), "dot")  # pastille non lues
        resp = self.client.post(reverse("recruiting:invitation_respond", args=[inv.pk]), {"action": "accept"})
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Member.objects.filter(user=colleague, recruitment=self.r).exists())
        self.assertTrue(Notification.objects.filter(user=self.owner, message__contains="a accepté").exists())
        app = Application.objects.get()
        url = reverse("recruiting:application", args=[self.r.pk, app.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"action": "shortlist"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("recruiting:edit", args=[self.r.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse("recruiting:dashboard")), "Créé par Boss")

    def test_decline_then_reinvite_and_cannot_answer_for_someone_else(self):
        colleague, other = mkuser("colleague"), mkuser("other")
        self.client.force_login(self.owner)
        team = reverse("recruiting:team", args=[self.r.pk])
        self.client.post(team, {"username": "colleague"})
        inv = Invitation.objects.get()
        self.client.force_login(other)
        self.assertEqual(self.client.post(reverse("recruiting:invitation_respond", args=[inv.pk]), {"action": "accept"}).status_code, 404)
        self.client.force_login(colleague)
        self.client.post(reverse("recruiting:invitation_respond", args=[inv.pk]), {"action": "decline"})
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invitation.Status.DECLINED)
        self.assertFalse(Member.objects.exists())
        self.client.force_login(self.owner)
        self.client.post(team, {"username": "colleague"})
        inv.refresh_from_db()
        self.assertEqual(inv.status, Invitation.Status.PENDING)

    def test_cannot_invite_owner_or_member(self):
        self.client.force_login(self.owner)
        team = reverse("recruiting:team", args=[self.r.pk])
        self.assertContains(self.client.post(team, {"username": "boss"}), "déjà accès")

    def test_email_notifications_can_be_disabled(self):
        User.objects.filter(pk=self.owner.pk).update(email_notifications=False)
        self.apply()
        self.assertFalse(any(m.to == ["boss@example.com"] for m in mail.outbox))
        self.assertTrue(Notification.objects.filter(user=self.owner).exists())  # l'alerte interne reste


class PagesAndResponsiveTests(Base):
    CSS = Path(settings.BASE_DIR / "static/css/app.css").read_text(encoding="utf-8")

    def test_create_recruitment_with_questions_and_topics(self):
        self.client.force_login(self.owner)
        data = {
            "title": "Designer", "description": "", "status": "open", "test_hours": 24, "test_enabled": "on", "task_title": "Design",
            "questions-TOTAL_FORMS": 1, "questions-INITIAL_FORMS": 0, "questions-MIN_NUM_FORMS": 0, "questions-MAX_NUM_FORMS": 1000,
            "questions-0-label": "Portfolio ?", "questions-0-kind": "short", "questions-0-required": "on", "questions-0-position": 0,
            "topics-TOTAL_FORMS": 1, "topics-INITIAL_FORMS": 0, "topics-MIN_NUM_FORMS": 0, "topics-MAX_NUM_FORMS": 1000,
            "topics-0-title": "Logo", "topics-0-brief": "Dessinez",
        }
        resp = self.client.post(reverse("recruiting:create"), data)
        self.assertEqual(resp.status_code, 302)
        r = Recruitment.objects.get(title="Designer")
        self.assertEqual((r.questions.count(), r.topics.count()), (1, 1))

    def all_pages(self):
        self.apply()
        app = Application.objects.get()
        return [("landing", []), ("accounts:login", []), ("accounts:signup", []), ("accounts:password_reset", []),
                ("recruiting:apply", [self.r.public_id]), ("recruiting:test", [self.r.public_id]), ("recruiting:thanks", [self.r.public_id]),
                ("recruiting:dashboard", []), ("recruiting:create", []), ("recruiting:detail", [self.r.pk]), ("recruiting:edit", [self.r.pk]),
                ("recruiting:team", [self.r.pk]), ("recruiting:application", [self.r.pk, app.pk]), ("recruiting:notifications", []),
                ("accounts:profile", []), ("recruiting:preview", ["answer", app.answers.get(question=self.cv).pk])]

    def test_every_page_renders_with_viewport_meta(self):
        self.client.force_login(self.owner)
        anon = self.client_class()  # connexion/inscription redirigent un utilisateur déjà connecté
        for name, args in self.all_pages():
            client = anon if name in ("accounts:login", "accounts:signup") else self.client
            resp = client.get(reverse(name, args=args))
            self.assertEqual(resp.status_code, 200, name)
            self.assertIn('name="viewport" content="width=device-width, initial-scale=1', resp.content.decode(), name)

    def test_no_fixed_pixel_widths_in_templates(self):
        for path in Path(settings.BASE_DIR / "templates").rglob("*.html"):
            self.assertIsNone(re.search(r'style="[^"]*width:\s*\d+px', path.read_text(encoding="utf-8")), path)

    def test_css_is_mobile_first(self):
        media = re.findall(r"@media\s*\(([^)]*)\)", self.CSS)
        self.assertTrue(any("min-width: 640px" in m for m in media))
        self.assertTrue(any("min-width: 900px" in m for m in media))
        self.assertFalse([m for m in media if "max-width" in m], "Pas de @media max-width : base mobile + min-width uniquement")
        for token in ("env(safe-area-inset-bottom)", "min-height: 44px", ".appnav", "font-size: 1rem"):
            self.assertIn(token, self.CSS)

    def test_csp_header(self):
        resp = self.client.get(reverse("landing"))
        self.assertIn("frame-ancestors 'self'", resp["Content-Security-Policy"])
