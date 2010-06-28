import shutil

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.core.exceptions import ObjectDoesNotExist

from versions.repo import versions
from versions.exceptions import VersionDoesNotExist, VersionsException
from versions.tests.models import Artist, Album, Song, Lyrics, Venue

class VersionsTestCase(TestCase):
    def setUp(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(settings.VERSIONS_REPOSITORY_ROOT, ignore_errors=True)

class VersionsModelTestCase(VersionsTestCase):
    def test_unmanaged_edits(self):
        queen = Artist(name='Queen')
        queen.save()
        self.assertEquals(len(Artist.objects.revisions(queen)), 1)

        prince = Artist(name='Prince')
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
        # Start a managed versioning session.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()
        self.assertEquals(len(Artist.objects.revisions(queen)), 0)

        prince = Artist(name='Prince')
        prince.save()
        self.assertEquals(len(Artist.objects.revisions(prince)), 0)

        prince.name = 'The Artist Formerly Known As Prince'
        prince.save()

        self.assertEquals(len(Artist.objects.revisions(prince)), 0)

        prince.name = 'Prince'
        prince.save()

        self.assertEquals(len(Artist.objects.revisions(prince)), 0)

        # Finish the versioning session.
        versions.finish()

        # Verify that we have only commited once for all of the edits.
        self.assertEquals(len(Artist.objects.revisions(prince)), 1)
        self.assertEquals(len(Artist.objects.revisions(queen)), 1)

        # Verify that both edits to Queen and Prince were tracked in the same revision.
        self.assertEquals(Artist.objects.revisions(prince), Artist.objects.revisions(queen))

    def test_related_model_edits(self):
        # Start a managed versioning transaction.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()

        a_kind_of_magic = Album(artist=queen, title='A Kind of Magic')
        a_kind_of_magic.save()

        dont_lose_your_head = Song(album=a_kind_of_magic, title="Don't Lose Your Head")
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versionsing transaction.
        versions.start()

        princes_of_the_universe = Song(album=a_kind_of_magic, title='Princes of the Universe')
        princes_of_the_universe.save()

        dont_lose_your_head.seconds = 278
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        second_revision = versions.finish().values()[0]

        # Start a managed versionsing transaction.
        versions.start()

        princes_of_the_universe.seconds = 212
        princes_of_the_universe.save()

        friends_will_be_friends = Song(album=a_kind_of_magic, title='Friends Will Be Friends')
        friends_will_be_friends.save()

        # Finish the versioning transaction.
        third_revision = versions.finish().values()[0]

        # the a_kind_of_magic album was not modified after the initial commit. Verify that we can retrieve the a_kind_of_magic model from the various revisions
        first_a_kind_of_magic = Album.objects.version(first_revision).get(pk=a_kind_of_magic.pk)
        second_a_kind_of_magic = Album.objects.version(second_revision).get(pk=a_kind_of_magic.pk)
        third_a_kind_of_magic = Album.objects.version(third_revision).get(pk=a_kind_of_magic.pk)

        # Verify that the data is the same.
        self.assertEqual(versions.data(first_a_kind_of_magic)['field'], versions.data(second_a_kind_of_magic)['field'])
        self.assertEqual(versions.data(second_a_kind_of_magic)['field'], versions.data(third_a_kind_of_magic)['field'])

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
        prince = Artist(name='Prince')
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
        # Start a managed versioning transaction.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()

        a_kind_of_magic = Album(artist=queen, title='A Kind of Magic')
        a_kind_of_magic.save()

        dont_lose_your_head = Song(album=a_kind_of_magic, title="Don't Lose Your Head")
        dont_lose_your_head.save()

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versionsing transaction.
        versions.start()

        princes_of_the_universe = Song(album=a_kind_of_magic, title='Princes of the Universe')
        princes_of_the_universe.save()

        dont_lose_your_head.delete()

        # Finish the versioning transaction.
        second_revision = versions.finish().values()[0]

        # Start a managed versionsing transaction.
        versions.start()

        friends_will_be_friends = Song(album=a_kind_of_magic, title='Friends Will Be Friends')
        friends_will_be_friends.save()

        # Finish the versioning transaction.
        third_revision = versions.finish().values()[0]

        self.assertEqual(list(Album.objects.version(first_revision).get(pk=a_kind_of_magic.pk).songs.all()), [dont_lose_your_head])
        self.assertEqual(list(Album.objects.version(second_revision).get(pk=a_kind_of_magic.pk).songs.all()), [princes_of_the_universe])
        self.assertEqual(list(Album.objects.version(third_revision).get(pk=a_kind_of_magic.pk).songs.all()), [princes_of_the_universe, friends_will_be_friends])

    def test_disabled_functions(self):
        queen = Artist(name='Queen')
        queen.save()

        prince = Artist(name='Price')
        prince.save()

        self.assertEqual(Artist.objects.count(), 2)

        self.assertRaises(VersionsException, Artist.objects.version('tip').count)
        self.assertRaises(VersionsException, Artist.objects.version('tip').aggregate)
        self.assertRaises(VersionsException, Artist.objects.version('tip').annotate)
        self.assertRaises(VersionsException, Artist.objects.version('tip').values_list)

    def test_many_to_many_fields(self):
        fan1 = User(username='fan1', email='fan1@example.com')
        fan1.save()

        fan2 = User(username='fan2', email='fan2@example.com')
        fan2.save()

        fan3 = User(username='fan3', email='fan3@example.com')
        fan3.save()

        # Start a managed versioning transaction.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()

        queen.fans.add(fan1)

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versioning transaction.
        versions.start()

        queen.fans = [fan2, fan3]

        # Finish the versioning transaction.
        second_revision = versions.finish().values()[0]

        self.assertEqual(list(Artist.objects.version(first_revision).get(pk=queen.pk).fans.all()), [fan1])
        self.assertEqual(list(Artist.objects.version(second_revision).get(pk=queen.pk).fans.all()), [fan2, fan3])

    def test_many_to_many_versioned_update(self):
        fan1 = User(username='fan1', email='fan1@example.com')
        fan1.save()

        fan2 = User(username='fan2', email='fan2@example.com')
        fan2.save()

        Artist(name='Queen').save()

        # Start a managed versioning transaction.
        versions.start()

        queen = Artist.objects.version('tip').get(name='Queen')
        queen.fans.add(fan1)

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versioning transaction.
        versions.start()

        queen.fans = [fan2]

        # Finish the versioning transaction.
        second_revision = versions.finish().values()[0]

        self.assertEqual(list(Artist.objects.version(first_revision).get(pk=queen.pk).fans.all()), [fan1])
        self.assertEqual(list(Artist.objects.version(second_revision).get(pk=queen.pk).fans.all()), [fan2])

    def test_reverse_foreign_keys(self):
        # Start a managed versioning transaction.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()

        a_kind_of_magic = Album(artist=queen, title='A Kind of Magic')
        a_kind_of_magic.save()

        journey_album = Album(artist=queen, title='Journey')
        journey_album.save()

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versioning transaction.
        versions.start()

        journey = Artist(name='Journey')
        journey.save()

        journey_album.artist = journey
        journey_album.save()

        # Finish the versioning transaction.
        second_revision = versions.finish().values()[0]

        self.assertEqual(list(Artist.objects.version(first_revision).get(pk=queen.pk).albums.all()), [a_kind_of_magic, journey_album])
        self.assertEqual(list(Artist.objects.version(second_revision).get(pk=queen.pk).albums.all()), [a_kind_of_magic])

class PublishedModelTestCase(VersionsTestCase):
    def test_unpublished(self):
        # Start a managed versioning transaction.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()

        a_kind_of_magic = Album(artist=queen, title='A Kind of Magic')
        a_kind_of_magic.save()

        dont_lose_your_head = Song(album=a_kind_of_magic, title="Don't Lose Your Head")
        dont_lose_your_head.save()

        original_lyrics = Lyrics(song=dont_lose_your_head, text="Dont lose your head")
        original_lyrics.versions_published = True
        original_lyrics.save()

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versioning transaction.
        versions.start()

        new_lyrics = """Dont lose your head
Dont lose your head
Dont lose your head
No dont lose you head
"""

        unpublished_lyrics = Lyrics.objects.version('tip').get(pk=original_lyrics.pk)
        unpublished_lyrics.versions_published = False
        unpublished_lyrics.text = new_lyrics
        unpublished_lyrics.save()

        second_revision = versions.finish().values()[0]

        # Ensure the database version still points to the old lyrics.
        self.assertEquals(Lyrics.objects.get(pk=original_lyrics.pk).text, "Dont lose your head")
        # Ensure that the revisions contain the correct information.
        self.assertEquals(Lyrics.objects.version(first_revision).get(pk=original_lyrics.pk).text, "Dont lose your head")
        self.assertEquals(Lyrics.objects.version(second_revision).get(pk=original_lyrics.pk).text, new_lyrics)

        # Start a managed versioning transaction.
        versions.start()

        new_lyrics = """Dont lose your head
Dont lose your head
Dont lose your head
Dont lose your head
No dont lose you head
Dont lose you head
Hear what I say
Dont lose your way - yeah
Remember loves stronger remember love walks tall
"""

        published_lyrics = Lyrics.objects.version('tip').get(pk=original_lyrics.pk)
        published_lyrics.versions_published = True
        published_lyrics.text = new_lyrics
        published_lyrics.save()

        third_revision = versions.finish().values()[0]

        # Ensure the database version still points to the old lyrics.
        self.assertEquals(Lyrics.objects.get(pk=original_lyrics.pk).text, new_lyrics)
        # Ensure that the revisions contain the correct information.
        self.assertEquals(Lyrics.objects.version(third_revision).get(pk=original_lyrics.pk).text, new_lyrics)

    def test_unpublished_new(self):
        # Start a managed versioning transaction.
        versions.start()

        queen = Artist(name='Queen')
        queen.save()

        a_kind_of_magic = Album(artist=queen, title='A Kind of Magic')
        a_kind_of_magic.save()

        dont_lose_your_head = Song(album=a_kind_of_magic, title="Don't Lose Your Head")
        dont_lose_your_head.save()

        original_lyrics = Lyrics(song=dont_lose_your_head, text="Dont lose your head")
        original_lyrics.save()

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        self.assertRaises(Lyrics.DoesNotExist, Lyrics.objects.get, pk=original_lyrics.pk)

    def test_unpublished_many_to_many(self):
        queen = Artist(name='Queen')
        queen.save()

        # Start a managed versioning transaction.
        versions.start()

        venue = Venue(name='Home')
        venue.versions_published = True
        venue.save()

        # Finish the versioning transaction.
        first_revision = versions.finish().values()[0]

        # Start a managed versioning transaction.
        versions.start()

        venue.versions_published = False
        venue.save()

        venue.artists.add(queen)

        # Finish the versioning transaction.
        second_revision = versions.finish().values()[0]

        self.assertEquals(list(Venue.objects.get(pk=1).artists.all()), [])

class VersionsOptionsTestCase(VersionsTestCase):
    def test_field_exclude(self):
        queen = Artist(name='Queen')
        queen.save()

        data = versions.data(queen)
        self.assertEqual(data['field'].keys(), ['name', 'versions_deleted'])

    def test_field_include(self):
        queen = Artist(name='Queen')
        queen.save()

        a_kind_of_magic = Album(artist=queen, title='A Kind of Magic')
        a_kind_of_magic.save()

        data = versions.data(a_kind_of_magic)
        self.assertEqual(data['field'].keys(), ['versions_deleted', 'title'])
