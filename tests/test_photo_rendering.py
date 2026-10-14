import unittest
from html.parser import HTMLParser

from mothdash.render import _photo_strip, _recent_cards, _profile_recent


class Images(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.images = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "img":
            self.images.append(dict(attrs))


def photo(number=1, **extra):
    return {
        "photo_url": f"https://inaturalist-open-data.s3.amazonaws.com/photos/{number}/medium.jpg",
        "label": 'Moth & "name"', "station_name": "Kingfisher Hollow",
        "url": f"https://www.inaturalist.org/observations/{number}",
        **extra,
    }


class PhotoRenderingTests(unittest.TestCase):
    def test_first_actual_hero_photo_is_eager_and_priority_even_after_empty_rows(self):
        rows = [photo(photo_url=None), photo(), photo(), photo(2)]
        images = Images(_photo_strip(rows)).images
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0].get("loading"), "eager")
        self.assertEqual(images[0].get("fetchpriority"), "high")
        self.assertEqual(images[1].get("loading"), "lazy")
        self.assertNotIn("fetchpriority", images[1])

    def test_generated_variants_expose_actual_portrait_widths_and_credit(self):
        row = photo(photo_variants=[
            {"url": "/assets/photos/a-120.webp", "width": 120, "height": 240},
            {"url": "/assets/photos/a-250.webp", "width": 250, "height": 500},
        ], photo_attribution="Jane & Joe (CC BY)")
        image = Images(_photo_strip([row])).images[0]
        self.assertEqual(image["src"], "/assets/photos/a-250.webp")
        self.assertEqual(image["srcset"], "/assets/photos/a-120.webp 120w, /assets/photos/a-250.webp 250w")
        self.assertIn("320px", image["sizes"])
        self.assertEqual(image["alt"], 'Moth & "name"')
        self.assertIn("Jane & Joe", image["title"])
        self.assertEqual((image["width"], image["height"]), ("250", "500"))

    def test_recent_thumbnails_use_upstream_small_without_rewriting_unknown_hosts(self):
        rows = [photo(), photo(2, photo_url="https://example.test/photos/2/medium.jpg")]
        images = Images(_recent_cards(rows)).images
        self.assertEqual(images[0]["src"], "https://inaturalist-open-data.s3.amazonaws.com/photos/1/small.jpg")
        self.assertEqual(images[1]["src"], "https://example.test/photos/2/medium.jpg")
        self.assertTrue(all(image.get("loading") == "lazy" for image in images))

    def test_thumbnail_srcset_uses_thumbnail_slot_not_hero_size(self):
        row = photo(photo_variants=[
            {"url": "/assets/photos/a.webp", "width": 240, "height": 240},
            {"url": "/assets/photos/b.webp", "width": 500, "height": 500},
        ])
        image = Images(_recent_cards([row])).images[0]
        self.assertIn("104px", image.get("sizes", ""))
        self.assertEqual(image["decoding"], "async")

    def test_profile_recent_uses_same_small_thumbnail_fallback(self):
        image = Images(_profile_recent([photo()])).images[0]
        self.assertTrue(image["src"].endswith("/small.jpg"))

    def test_malformed_upstream_url_does_not_abort_the_whole_page(self):
        url = "https://[broken/photos/1/medium.jpg"
        image = Images(_recent_cards([photo(photo_url=url)])).images[0]
        self.assertEqual(image["src"], url)


if __name__ == "__main__":
    unittest.main()
