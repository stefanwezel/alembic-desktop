import os
import sys
import time

import numpy as np
import pytest

app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "app"))
sys.path.append(app_dir)
import utils


FILES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")


@pytest.fixture
def jpg_dir():
    return os.path.join(FILES_DIR, "jpgs")


@pytest.fixture
def dng_dir():
    return os.path.join(FILES_DIR, "dngs")


def test_load_image_jpg(jpg_dir):
    for file in os.listdir(jpg_dir):
        image = utils.load_image(os.path.join(jpg_dir, file))
        assert type(image) == np.ndarray
        assert len(image.shape) == 3
        assert image.shape[-1] == 3  # assume channel dimension is last


def test_load_image_dng(dng_dir):
    for file in os.listdir(dng_dir):
        image = utils.load_image(os.path.join(dng_dir, file))
        assert type(image) == np.ndarray
        assert len(image.shape) == 3
        assert image.shape[-1] == 3  # assume channel dimension is last


@pytest.mark.parametrize("filename", ["sample.png", "sample.tif", "sample.tiff"])
def test_load_image_non_jpeg_formats(tmpdir, filename):
    """PNG and TIFF are advertised as supported and must decode to BGR arrays (regression)."""
    from PIL import Image

    path = os.path.join(tmpdir, filename)
    Image.new("RGB", (80, 60), (10, 20, 30)).save(path)

    image = utils.load_image(path)

    assert type(image) == np.ndarray
    assert image.shape == (60, 80, 3)
    assert image.dtype == np.uint8
    assert tuple(image[0, 0]) == (30, 20, 10)  # RGB source arrives as BGR


def test_raw_extensions_route_to_rawpy():
    """Every advertised RAW format must be decoded by rawpy, not by the JPEG fast path."""
    assert utils.RAW_EXTENSIONS == {".dng", ".cr2", ".nef", ".arw"}
    assert utils.SUPPORTED_EXTENSIONS == {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".dng", ".cr2", ".nef", ".arw"}


def test_load_image_handles_mixed_case_extensions(dng_dir):
    for file in os.listdir(dng_dir):
        assert utils.get_extension(os.path.join(dng_dir, file.upper())) in utils.RAW_EXTENSIONS


def test_generate_jpg_path(dng_dir):
    for file in os.listdir(dng_dir):
        jpg_path = utils.generate_jpg_path(os.path.join(dng_dir, file))
        assert jpg_path.split(".")[-1] == "jpg"


def test_fit_image_dimensions():
    """Tests the `fit_image_dimensions` function with various image sizes and max dimensions while maintaining aspect ratio."""
    test_cases = [
        ((500, 250, 3), (200, 200)),
        ((250, 500, 3), (200, 200)),
        ((200, 200, 3), (200, 200)),
        ((100, 200, 3), (200, 200)),
        ((50, 50, 3), (50, 50)),
    ]

    for image_shape, (max_height, max_width) in test_cases:
        image = np.random.rand(*image_shape)
        new_height, new_width = utils.fit_image_dimensions(image, max_height, max_width)

        assert new_height <= max_height and new_width <= max_width
        assert new_width / new_height == image.shape[1] / image_shape[0]
        print(f"\nInput image shape: {image.shape} - Max height, width {max_height}, {max_width}")
        image = utils.resize_image(image, height=new_height, width=new_width)
        print(f"Output image shape: {image.shape}")


def test_resize_image(jpg_dir):
    for file in os.listdir(jpg_dir):
        image = utils.load_image(os.path.join(jpg_dir, file))
        image = utils.resize_image(image, height=50, width=100)
        assert image.shape[0] == 50 and image.shape[1] == 100
        image = utils.resize_image(image, height=224, width=224)
        assert image.shape[0] == image.shape[1] == 224


def test_prepare_image_jpg(jpg_dir, tmpdir):
    for file in os.listdir(jpg_dir):
        input_path = os.path.join(jpg_dir, file)
        display_path, thumbnail_path, preview_path, numpy_image = utils.prepare_image(
            input_path, output_dir=str(tmpdir)
        )

        assert display_path == input_path, "a jpeg is displayed straight from the source file"
        assert os.path.exists(thumbnail_path), f"Output image {thumbnail_path} not created."
        assert os.path.exists(preview_path), f"Output image {preview_path} not created."
        assert numpy_image.shape[-1] == 3


def test_get_orientation_missing_tag_does_not_crash(tmpdir):
    """A JPEG without an Orientation EXIF tag must not raise (regression)."""
    from PIL import Image

    path = os.path.join(tmpdir, "no_orientation.jpg")
    Image.new("RGB", (64, 48), (10, 20, 30)).save(path)

    assert utils.get_orientation(path) is None


def test_prepare_image_jpg_without_orientation(tmpdir):
    """JPEGs lacking an Orientation EXIF tag must still import successfully."""
    from PIL import Image

    input_path = os.path.join(tmpdir, "plain.jpg")
    Image.new("RGB", (640, 480), (10, 20, 30)).save(input_path)

    display_path, thumbnail_path, preview_path, numpy_image = utils.prepare_image(input_path, output_dir=str(tmpdir))

    assert os.path.exists(thumbnail_path), f"Output image {thumbnail_path} not created."
    assert os.path.exists(preview_path), f"Output image {preview_path} not created."
    assert numpy_image.shape[-1] == 3


def test_prepare_image_dng(dng_dir, tmpdir):
    for file in os.listdir(dng_dir):
        input_path = os.path.join(dng_dir, file)
        display_path, thumbnail_path, preview_path, numpy_image = utils.prepare_image(
            input_path, output_dir=str(tmpdir)
        )

        # A RAW file gets a jpeg twin in the cache; the source is never touched.
        assert os.path.dirname(display_path) == str(tmpdir)
        assert os.path.exists(display_path), f"Output image {display_path} not created."
        assert os.path.exists(thumbnail_path), f"Output image {thumbnail_path} not created."
        assert os.path.exists(preview_path), f"Output image {preview_path} not created."
        assert numpy_image.shape[-1] == 3
