from versions.base import repositories

class VersionsMiddleware(object):
    def process_request(self, request):
        repositories.start()
        if hasattr(request, 'user') and hasattr(request.user, 'get_full_name') and hasattr(request.user, 'email') and hasattr(request.user, 'username'):
            user_text = request.user.get_full_name() and request.user.get_full_name() or request.user.username
            if request.user.email:
                user_text = '%s <%s>' % (user_text, request.user.email)
            repositories.user = user_text

    def process_exception(self, request, exception):
        repositories.finish(exception=True)

    def process_response(self, request, response):
        repositories.finish()
        return response
