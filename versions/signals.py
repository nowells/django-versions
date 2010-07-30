from django.dispatch.dispatcher import Signal

pre_stage = Signal(providing_args=["instance"])

