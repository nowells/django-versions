import shutil

from django.conf import settings
from django.test import TestCase

from versions import Versions
from versions.tests.models import Artist

class VersionsTestCase(TestCase):
    def setUp(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

class TestModelSaveVersioning(VersionsTestCase):
    def test_unmanaged_edits(self):
        queen = Artist()
        queen.name = 'Queen'
        queen.save()
        self.assertEquals(len(Artist.objects.revisions(queen)), 1)

        prince = Artist()
        prince.name = 'Price'
        prince.save()
        self.assertEquals(len(Artist.objects.revisions(prince)), 1)

        prince.name = 'The Artist Formerly Known As Prince'
        prince.save()
        self.assertEquals(len(Artist.objects.revisions(prince)), 2)

        prince.name = 'Prince'
        prince.save()
        self.assertEquals(len(Artist.objects.revisions(prince)), 3)

    def test_managed_edits(self):
        vc = Versions()
        # Start a managed versioning session.
        vc.start()

        queen = Artist()
        queen.name = 'Queen'
        queen.save()
        self.assertEquals(len(Artist.objects.revisions(queen)), 0)

        prince = Artist()
        prince.name = 'Price'
        prince.save()
        self.assertEquals(len(Artist.objects.revisions(prince)), 0)

        prince.name = 'The Artist Formerly Known As Prince'
        prince.save()

        self.assertEquals(len(Artist.objects.revisions(prince)), 0)

        prince.name = 'Prince'
        prince.save()

        self.assertEquals(len(Artist.objects.revisions(prince)), 0)

        # Finish the versioning session.
        vc.finish()

        # Verify that we have only commited once for all of the edits.
        self.assertEquals(len(Artist.objects.revisions(prince)), 1)
        self.assertEquals(len(Artist.objects.revisions(queen)), 1)

        # Verify that both edits to Queen and Prince were tracked in the same commit.
        self.assertEquals(Artist.objects.revisions(prince), Artist.objects.revisions(queen))
