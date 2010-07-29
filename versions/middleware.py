from versions.base import repositories

class VersionsMiddleware(object):
    def process_request(self, request):
        repositories.start()
        if hasattr(request, 'user') and request.user.is_authenticated():
            repositories.user = request.user

    def process_exception(self, request, exception):
        repositories.finish(exception=True)

    def process_response(self, request, response):
        repositories.finish()
        return response
