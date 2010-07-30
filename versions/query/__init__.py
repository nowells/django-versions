import django

if django.VERSION < (1, 2):
    from django11 import *
else:
    from django12 import *

