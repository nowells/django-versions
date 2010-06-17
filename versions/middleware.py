from versions.repo import Versions

class VersionsMiddleware(Versions):
    def process_request(self, request):
        self.start()

    def process_exception(self, request, exception):
        self.finish(exception=True)

    def process_response(self, request, response):
        self.finish()
        return response
