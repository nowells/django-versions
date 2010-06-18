import shutil

from django.conf import settings
from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist

from versions import Versions, VersionDoesNotExist, VersionsException
from versions.tests.models import Artist, Albumn, Song

class VersionsTestCase(TestCase):
    def setUp(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

class ModelVersionsTestCase(VersionsTestCase):
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

        dont_lose_your_head = Song()
        dont_lose_your_head.albumn = a_kind_of_magic
        dont_lose_your_head.title = u"Don't Lose Your Head"
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        first_revision = vc.finish().values()[0]

        # Start a managed versionsing transaction.
        vc.start()

        princes_of_the_universe = Song()
        princes_of_the_universe.albumn = a_kind_of_magic
        princes_of_the_universe.title = u'Princes of the Universe'
        princes_of_the_universe.save()

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

        # the a_kind_of_magic albumn was not modified after the initial commit. Verify that we can retrieve the a_kind_of_magic model from the various revisions
        first_a_kind_of_magic = Albumn.objects.version(first_revision).get(pk=a_kind_of_magic.pk)
        second_a_kind_of_magic = Albumn.objects.version(second_revision).get(pk=a_kind_of_magic.pk)
        third_a_kind_of_magic = Albumn.objects.version(third_revision).get(pk=a_kind_of_magic.pk)

        # Verify that the data is the same.
        self.assertEqual(vc.data(first_a_kind_of_magic), vc.data(second_a_kind_of_magic))
        self.assertEqual(vc.data(second_a_kind_of_magic), vc.data(third_a_kind_of_magic))

        # Verify that princes_of_the_universe does not exist at the first_revision (it was created on the second revision)
        self.assertRaises(ObjectDoesNotExist, first_a_kind_of_magic.songs.get, pk=princes_of_the_universe.pk)

        # Verify that retrieving the object from the reverse relationship and directly from the Song objects yield the same result.
        self.assertEqual(second_a_kind_of_magic.songs.get(pk=princes_of_the_universe.pk).__dict__, Song.objects.version(second_revision).get(pk=princes_of_the_universe.pk).__dict__)

        # Verify that retrieval of the object from the reverse relationship return the correct revisions of the objects.
        second_princes_of_the_universe = second_a_kind_of_magic.songs.get(pk=princes_of_the_universe.pk)
        self.assertEqual(second_princes_of_the_universe.seconds, None)

        third_princes_of_the_universe = third_a_kind_of_magic.songs.get(pk=princes_of_the_universe.pk)
        self.assertEqual(third_princes_of_the_universe.seconds, 212)

        # Verify that the first revision of a_kind_of_magic has one song
        self.assertEquals(len(first_a_kind_of_magic.songs.all()), 1)

        # Verify that the second revision of a_kind_of_magic has two songs
        self.assertEquals(len(second_a_kind_of_magic.songs.all()), 2)

        # Verify that the third revision of a_kind_of_magic has three songs
        self.assertEquals(len(third_a_kind_of_magic.songs.all()), 3)

    def test_revision_retrieval(self):
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

    def test_deletion(self):
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

        dont_lose_your_head = Song()
        dont_lose_your_head.albumn = a_kind_of_magic
        dont_lose_your_head.title = u"Don't Lose Your Head"
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        first_revision = vc.finish().values()[0]

        # Start a managed versionsing transaction.
        vc.start()

        princes_of_the_universe = Song()
        princes_of_the_universe.albumn = a_kind_of_magic
        princes_of_the_universe.title = u'Princes of the Universe'
        princes_of_the_universe.save()

        dont_lose_your_head.delete()

        # Finish the versioning transaction.
        second_revision = vc.finish().values()[0]

        # Start a managed versionsing transaction.
        vc.start()

        friends_will_be_friends = Song()
        friends_will_be_friends.albumn = a_kind_of_magic
        friends_will_be_friends.title = 'Friends Will Be Friends'
        friends_will_be_friends.save()

        # Finish the versioning transaction.
        third_revision = vc.finish().values()[0]

        self.assertEqual([ x.title for x in Albumn.objects.version(first_revision).get(pk=a_kind_of_magic.pk).songs.all() ], ["Don't Lose Your Head"])
        self.assertEqual([ x.title for x in Albumn.objects.version(second_revision).get(pk=a_kind_of_magic.pk).songs.all() ], ["Princes of the Universe"])
        self.assertEqual([ x.title for x in Albumn.objects.version(third_revision).get(pk=a_kind_of_magic.pk).songs.all() ], ["Princes of the Universe", "Friends Will Be Friends"])

    def test_disabled_functions(self):
        queen = Artist()
        queen.name = 'Queen'
        queen.save()

        prince = Artist()
        prince.name = 'Price'
        prince.save()

        self.assertEqual(Artist.objects.count(), 2)

        self.assertRaises(VersionsException, Artist.objects.version('tip').count)
        self.assertRaises(VersionsException, Artist.objects.version('tip').aggregate)
        self.assertRaises(VersionsException, Artist.objects.version('tip').annotate)
        self.assertRaises(VersionsException, Artist.objects.version('tip').values_list)
