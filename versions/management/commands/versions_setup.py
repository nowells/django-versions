from __future__ import with_statement

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, NoArgsCommand

from versions.base import revision
from versions.models import VersionsModel

class Command(NoArgsCommand):
    help = "Setup your django-versions repositories and create a baseline revision for all existing data in your models."

    requires_model_validation = True

    def handle_noargs(self, **options):
        from django.db.models.loading import get_models

        models = get_models(include_deferred=True)
        for model in models:
            if issubclass(model, VersionsModel):
                instance_count = model.objects.count()
                model_name = '%s.%s' % (model._meta.app_label, model._meta.module_name)
                print 'Creating baseline revisions for %s `%s` objects.' % (
                    instance_count,
                    model_name,
                    )

                for instance in model.objects.iterator():
                    with revision:
                        revision.message = 'Baseline creation of model data for `%s` objects.' % model_name
                        revision.stage(instance)
