from django.core.management.base import BaseCommand

from recruiting.services import send_deadline_reminders


class Command(BaseCommand):
    help = "Envoie un rappel aux candidats dont le délai de rendu expire dans moins de 24 h."

    def handle(self, *args, **options):
        self.stdout.write(f"{send_deadline_reminders()} rappel(s) envoyé(s).")
