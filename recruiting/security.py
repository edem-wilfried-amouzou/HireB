from django.core.cache import cache


def too_many(request, scope, limit, window):
    """Limiteur simple par IP (cache Django). Renvoie True si la limite est dépassée.

    Derrière un proxy, configurez-le pour que REMOTE_ADDR soit la vraie IP du client.
    """
    key = f"thr:{scope}:{request.META.get('REMOTE_ADDR', '?')}"
    if cache.add(key, 1, window):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, window)
        return False
