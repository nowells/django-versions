from django.db import models

class Changeset(models.Model):
    user = models.CharField(max_length=32, null=True)
    message = models.TextField(blank=True)
    time_create = models.DateTimeField(auto_now=True)

    def parent(self):
        try:
            return Changeset.objects.filter(pk__lt=self.pk).order_by('-pk')[:1].get()
        except Changeset.DoesNotExist:
            return Changeset(user=None, message='', pk=0)
    parent = property(parent)

    def parents(self):
        return [ self.parent ]
    parents = property(parents)

    def revision(self):
        return str(self.pk)
    revision = property(revision)

class Revision(models.Model):
    changeset = models.ForeignKey(Changeset, related_name='revisions')
    path = models.CharField(max_length=255, db_index=True)
    data = models.TextField()
