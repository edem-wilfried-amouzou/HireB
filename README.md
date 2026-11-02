# HireB (nom provisoire)

Plateforme de recrutement : offres avec questions, lien public de candidature, candidatures anonymes
(codes 001, 002…), travail à rendre avec délai, équipe invitée par nom d'utilisateur, notifications internes et email.

## Lancer
```bash
python -m venv .venv && source .venv/bin/activate      # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
rm -f db.sqlite3                  # ancienne base : le modèle utilisateur a changé (username)
python manage.py migrate
python manage.py runserver
```
Tests : `python manage.py test` (26 tests). Nom du produit : `SITE_NAME` dans `.env`.

## Emails
Sans `EMAIL_HOST`, ils s'affichent dans la console. Envoyés : confirmation de candidature, travail reçu, statut
(optionnel, case à cocher), invitation d'équipe, réponse à l'invitation, nouvelle candidature / travail rendu (équipe),
réinitialisation du mot de passe, rappel < 24 h avant l'échéance. Chaque email rappelle de vérifier les spams.
Rappels (cron toutes les heures) : `python manage.py send_reminders`. Chaque utilisateur peut couper ses emails dans son profil.

## Règles métier
- Anonymat : nom, email, téléphone et noms de fichiers masqués (équipe et notifications) jusqu'à « Présélectionner » / « Retenir ».
- Fichiers : formats PDF, PNG, JPG, TXT, MD, CSV (contenu vérifié). Consultation en ligne uniquement, aucun lien de téléchargement.
  Stockés dans `private_media/`, jamais servis directement.
- Équipe : lecture seule ; invitation par `@username`, accept/refus depuis les notifications.
- Profil : nom, email, téléphone, mot de passe modifiables ; le username est fixe.

## Production
`DJANGO_DEBUG=0`, `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `SITE_URL`, PostgreSQL, SMTP, puis `collectstatic`.
Limiteur de tentatives : cache Django (utilisez Redis/Memcached si plusieurs processus).

## Responsive
CSS mobile-first (base mobile, `min-width` 640 / 900 px). Test visuel optionnel : `tests_e2e/test_responsive.py` (Playwright).
