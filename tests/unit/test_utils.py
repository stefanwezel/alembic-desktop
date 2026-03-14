import os
import sys
import time

import numpy as np
import pytest

app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "app"))
sys.path.append(app_dir)
import utils


@pytest.fixture
def jpg_dir():
    return "tests/unit/files/jpgs"


@pytest.fixture
def dng_dir():
    return "tests/unit/files/dngs"


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
        display_path, preview_path, thumbnail_path, numpy_image = utils.prepare_image(input_path)

        assert os.path.exists(thumbnail_path), f"Output image {thumbnail_path} not created."
        os.remove(thumbnail_path)
        assert not os.path.exists(thumbnail_path)

        assert os.path.exists(preview_path), f"Output image {preview_path} not created."
        os.remove(preview_path)
        assert not os.path.exists(preview_path)

        assert numpy_image.shape[-1] == 3


def test_prepare_image_dng(dng_dir, tmpdir):
    for file in os.listdir(dng_dir):
        input_path = os.path.join(dng_dir, file)
        display_path, preview_path, thumbnail_path, numpy_image = utils.prepare_image(input_path)

        assert os.path.exists(thumbnail_path), f"Output image {thumbnail_path} not created."
        os.remove(thumbnail_path)
        assert not os.path.exists(thumbnail_path)

        assert os.path.exists(preview_path), f"Output image {preview_path} not created."
        os.remove(preview_path)
        assert not os.path.exists(preview_path)

        assert os.path.exists(display_path), f"Output image {display_path} not created."
        os.remove(display_path)
        assert not os.path.exists(display_path)

        assert numpy_image.shape[-1] == 3
