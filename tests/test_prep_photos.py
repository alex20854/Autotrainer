import prep_photos as pp


class FakeExif(dict):
    """Stands in for PIL.Image.Exif: 0th-IFD entries in the dict, Exif IFD via get_ifd."""
    def __init__(self, base=None, ifd=None):
        super().__init__({271: "Apple"} if base is None else base)
        self._ifd = ifd or {}

    def get_ifd(self, tag):
        return self._ifd if tag == pp.EXIF_IFD else {}


class FakeImage:
    def __init__(self, exif):
        self._exif = exif

    def getexif(self):
        return self._exif


def test_offset_time_original_is_carried_into_exif_time():
    im = FakeImage(FakeExif(ifd={pp.DATETIME_ORIGINAL: "2026:09:09 06:37:45",
                                 pp.OFFSET_TIME_ORIGINAL: "-07:00"}))
    assert pp.exif_datetime(im) == "2026-09-09T06:37:45-07:00"


def test_no_offset_stays_naive_local():
    im = FakeImage(FakeExif(ifd={pp.DATETIME_ORIGINAL: "2026:08:08 20:41:02"}))
    assert pp.exif_datetime(im) == "2026-08-08T20:41:02"


def test_malformed_offset_is_ignored():
    im = FakeImage(FakeExif(ifd={pp.DATETIME_ORIGINAL: "2026:08:08 20:41:02",
                                 pp.OFFSET_TIME_ORIGINAL: "   "}))
    assert pp.exif_datetime(im) == "2026-08-08T20:41:02"


def test_datetime_fallback_uses_its_own_offset_tag():
    im = FakeImage(FakeExif(base={271: "Apple", 306: "2026:08:08 20:41:02"},
                            ifd={pp.OFFSET_TIME: "+02:00"}))
    assert pp.exif_datetime(im) == "2026-08-08T20:41:02+02:00"


def test_no_exif_returns_none():
    assert pp.exif_datetime(FakeImage(FakeExif(base={}))) is None
