from versions.base import revision

class VersionsMiddleware(object):
    def process_request(self, request):
        revision.start()
        if hasattr(request, 'user') and request.user.is_authenticated():
            revision.user = request.user

    def process_exception(self, request, exception):
        revision.invalidate()

    def process_response(self, request, response):
        while revision.is_active():
            revision.finish()
        return response
