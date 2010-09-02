from django.dispatch import Signal

post_stage = Signal(providing_args=["instance"])
