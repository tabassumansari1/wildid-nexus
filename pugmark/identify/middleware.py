from django.conf import settings


class TrustPreviewOriginMiddleware:
    """Accept the browser Origin when the app is opened through a preview proxy.

    Django checks Origin on unsafe requests. A local field kit has no fixed
    public hostname, so a well-formed http(s) Origin is trusted for this process.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get("HTTP_ORIGIN", "")
        if origin.startswith(("http://", "https://")) and origin not in settings.CSRF_TRUSTED_ORIGINS:
            settings.CSRF_TRUSTED_ORIGINS.append(origin)
        return self.get_response(request)
