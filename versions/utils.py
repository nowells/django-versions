import os
from django.core.exceptions import ImproperlyConfigured
from django.utils.importlib import import_module

def load_backend(backend_name):
    try:
        return import_module('.base', backend_name)
    except ImportError, e_user:
        raise
        # The versions backend wasn't found. Display a helpful error message
        # listing all possible (built-in) database backends.
        backend_dir = os.path.join(os.path.dirname(__file__), 'backends')
        try:
            available_backends = [f for f in os.listdir(backend_dir)
                                  if os.path.isdir(os.path.join(backend_dir, f))
                                  and not f.startswith('.')]
        except EnvironmentError:
            available_backends = []
        available_backends.sort()
        if backend_name not in available_backends:
            error_msg = ("%r isn't an available versions backend. \n" +
                         "Try using versions.backends.XXX, where XXX is one of:\n    %s\n" +
                         "Error was: %s") % \
                         (backend_name, ", ".join(map(repr, available_backends)), e_user)
            raise ImproperlyConfigured(error_msg)
        else:
            raise # If there's some other error, this must be an error in Django itself.
