import shutil

from django.conf import settings
from django.test import TestCase

from versions import Versions, VersionDoesNotExist
from versions.tests.models import Artist, Albumn, Song

class VersionsTestCase(TestCase):
    def setUp(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

class ModelSaveTest(VersionsTestCase):
    def test_unmanaged_edits(self):
        queen = Artist()
        queen.name = 'Queen'
        queen.save()
        self.assertEquals(len(Artist.objects.revisions(queen)), 1)

        prince = Artist()
        prince.name = 'Price'
        prince.save()
        self.assertEquals(len(Artist.objects.revisions(prince)), 1)

        # Verify that the commit for Queen and Prince happened in different revisions.
        self.assertNotEqual(Artist.objects.revisions(prince), Artist.objects.revisions(queen))

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

        # Verify that both edits to Queen and Prince were tracked in the same revision.
        self.assertEquals(Artist.objects.revisions(prince), Artist.objects.revisions(queen))

    def test_related_model_edits(self):
        vc = Versions()
        # Start a managed versioning transaction.
        vc.start()

        queen = Artist()
        queen.name = u'Queen'
        queen.save()

        a_kind_of_magic = Albumn()
        a_kind_of_magic.artist = queen
        a_kind_of_magic.title = u'A Kind of Magic'
        a_kind_of_magic.save()

        princes_of_the_universe = Song()
        princes_of_the_universe.albumn = a_kind_of_magic
        princes_of_the_universe.title = u'Princes of the Universe'
        princes_of_the_universe.save()

        dont_lose_your_head = Song()
        dont_lose_your_head.albumn = a_kind_of_magic
        dont_lose_your_head.title = u"Don't Lose Your Head"
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        first_revision = vc.finish().values()[0]

        # Start a managed versionsing transaction.
        vc.start()

        dont_lose_your_head.seconds = 278
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        second_revision = vc.finish().values()[0]

        # Start a managed versionsing transaction.
        vc.start()

        princes_of_the_universe.seconds = 212
        princes_of_the_universe.save()

        friends_will_be_friends = Song()
        friends_will_be_friends.albumn = a_kind_of_magic
        friends_will_be_friends.title = 'Friends Will Be Friends'
        friends_will_be_friends.save()

        # Finish the versioning transaction.
        third_revision = vc.finish().values()[0]

        # Verify that friends_will_be_friends does not exist at the second_revision (it was created on the third revision)
        self.assertRaises(VersionDoesNotExist, Song.objects.version(second_revision).get, pk=friends_will_be_friends.pk)

        # the a_kind_of_magic albumn was not modified after the initial commit. Verify that we can retrieve the a_kind_of_magic model from the various revisions
        second_a_kind_of_magic = Albumn.objects.version(second_revision).get(pk=a_kind_of_magic.pk)
        third_a_kind_of_magic = Albumn.objects.version(third_revision).get(pk=a_kind_of_magic.pk)

        # Verify that the data is the same.
        self.assertEqual(vc.data(a_kind_of_magic), vc.data(a_kind_of_magic))

        second_princes_of_the_universe = second_a_kind_of_magic.songs.get(pk=princes_of_the_universe.pk)
        self.assertEqual(second_princes_of_the_universe.seconds, None)

        third_princes_of_the_universe = third_a_kind_of_magic.songs.get(pk=princes_of_the_universe.pk)
        self.assertEqual(third_princes_of_the_universe.seconds, 212)

        # Verify that the third revision of a_kind_of_magic has three songs
        self.assertEquals(len(third_a_kind_of_magic.songs.all()), 3)

        # Verify that the second revision of a_kind_of_magic has two songs
        self.assertEquals(len(a_kind_of_magic.songs.all()), 2)


    def test_revision_retreival(self):
        prince = Artist()
        prince.name = 'Prince'
        first_revision = prince.save()

        prince.name = 'The Artist Formerly Known As Prince'
        second_revision = prince.save()

        prince.name = 'Prince'
        third_revision = prince.save()

        first_prince = Artist.objects.version(first_revision).get(pk=prince.pk)
        self.assertEquals(first_prince.name, 'Prince')
        self.assertEquals(first_prince._versions_revision, first_revision)

        second_prince = Artist.objects.version(second_revision).get(pk=prince.pk)
        self.assertEquals(second_prince.name, 'The Artist Formerly Known As Prince')
        self.assertEquals(second_prince._versions_revision, second_revision)

        third_prince = Artist.objects.version(third_revision).get(pk=prince.pk)
        self.assertEquals(third_prince.name, 'Prince')
        self.assertEquals(third_prince._versions_revision, third_revision)
