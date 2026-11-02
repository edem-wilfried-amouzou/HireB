import os

from django import forms
from django.conf import settings

SIGNATURES = {
    "pdf": (b"%PDF",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
}
TEXT_EXTS = {"txt", "md", "csv"}
CONTENT_TYPES = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}


def ext_of(name):
    return os.path.splitext(name or "")[1].lower().lstrip(".")


def preview_kind(name):
    """'pdf' | 'image' | 'text' | None (aperçu impossible)."""
    ext = ext_of(name)
    if ext == "pdf":
        return "pdf"
    if ext in ("png", "jpg", "jpeg"):
        return "image"
    if ext in TEXT_EXTS:
        return "text"
    return None


def validate_upload(f):
    """Extension autorisée, taille max, et contenu cohérent avec l'extension."""
    ext = ext_of(f.name)
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise forms.ValidationError(
            "Format non accepté. Formats autorisés : " + ", ".join(sorted(settings.ALLOWED_UPLOAD_EXTENSIONS)) + "."
        )
    if f.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise forms.ValidationError(f"Fichier trop lourd (maximum {settings.MAX_UPLOAD_MB} Mo).")
    head = f.read(4096)
    f.seek(0)
    if ext in SIGNATURES and not any(head.startswith(sig) for sig in SIGNATURES[ext]):
        raise forms.ValidationError("Le contenu du fichier ne correspond pas à son format.")
    if ext in TEXT_EXTS and b"\x00" in head:
        raise forms.ValidationError("Le contenu du fichier ne correspond pas à son format.")
