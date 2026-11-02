"""Test visuel optionnel (navigateur réel) : aucun débordement horizontal à toutes les largeurs.

    pip install playwright && playwright install chromium
    python manage.py runserver            # dans un autre terminal
    python tests_e2e/test_responsive.py http://127.0.0.1:8000
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
PAGES = ["/", "/connexion/", "/inscription/"]  # ajoutez /r/<public_id>/ pour une offre existante
WIDTHS = [(360, 740), (390, 844), (768, 1024), (1024, 768), (1440, 900)]

with sync_playwright() as p:
    browser = p.chromium.launch()
    failures = []
    for w, h in WIDTHS:
        page = browser.new_page(viewport={"width": w, "height": h})
        for path in PAGES:
            page.goto(BASE + path)
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            if overflow > 0:
                failures.append(f"{path} @ {w}px : +{overflow}px de débordement")
        page.close()
    browser.close()
print("\n".join(failures) or "OK : aucun débordement horizontal.")
sys.exit(1 if failures else 0)
