import os
import shutil

import pytest

# Qt without a screen (CI, tests) - must be set before a QApplication exists
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from eirekes_manager import i18n  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
AUDIO_FORMATS = ("mp3", "m4a", "flac", "wav")


@pytest.fixture(autouse=True)
def english():
    """Every test starts in English (tr() keeps a global language)."""
    i18n.set_language("en")
    yield
    i18n.set_language("en")


def copy_fixture(name, folder, new_name=None):
    dst = os.path.join(str(folder), new_name or name)
    shutil.copy(os.path.join(FIXTURES, name), dst)
    return dst


@pytest.fixture(params=AUDIO_FORMATS)
def audio_file(request, tmp_path):
    """A silent audio file (every supported format) in a temp folder."""
    return copy_fixture(f"silence.{request.param}", tmp_path)


@pytest.fixture
def mp3_file(tmp_path):
    return copy_fixture("silence.mp3", tmp_path)


@pytest.fixture
def small_catalog_path():
    return os.path.join(FIXTURES, "artists_small.json")


@pytest.fixture
def catalog(small_catalog_path, tmp_path):
    from eirekes_manager.core.artist_catalog import ArtistCatalog
    return ArtistCatalog(small_catalog_path, str(tmp_path / "user" / "artists_user.json"))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def cover_jpg(tmp_path, qapp):
    """A small red JPEG made with Qt."""
    from PyQt6.QtGui import QImage, QColor
    img = QImage(16, 16, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    path = str(tmp_path / "cover.jpg")
    assert img.save(path, "JPEG")
    return path
