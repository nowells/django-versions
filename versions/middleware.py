from versions.repo import Versions

class VersionsMiddleware(Versions):
    def process_request(self, request):
        self.start()
        if hasattr(request, 'user') and hasattr(request.user, 'get_full_name') and hasattr(request.user, 'email') and hasattr(request.user, 'username'):
            user_text = request.user.get_full_name() and request.user.get_full_name() or request.user.username
            if request.user.email:
                user_text = '%s <%s>' % (user_text, request.user.email)
            self.user = user_text

    def process_exception(self, request, exception):
        self.finish(exception=True)

    def process_response(self, request, response):
        self.finish()
        return response
