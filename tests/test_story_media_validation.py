import unittest

from app.utils.files import allowed_file, choose_media_extension, detect_media_kind


class StoryMediaValidationTest(unittest.TestCase):
    def test_detects_video_mime_over_fake_extension(self):
        self.assertEqual(detect_media_kind('fake.jpg', 'video/mp4'), 'video')

    def test_allows_video_by_mime_even_when_name_is_wrong(self):
        self.assertTrue(allowed_file('fake.jpg', {'jpg', 'mp4'}, 'video/mp4'))

    def test_uses_mime_extension_for_saving(self):
        self.assertEqual(choose_media_extension('fake.jpg', 'video/mp4'), '.mp4')


if __name__ == '__main__':
    unittest.main()
