import logging
import os
import shutil
from typing import List, Optional, Tuple
from zipfile import ZipFile

import cv2
import exifread
import numpy as np
import rawpy
from PIL import Image
from turbojpeg import TJPF_BGR, TurboJPEG

try:
    turbo_jpeg = TurboJPEG()
except RuntimeError as e:
    logging.error(f"Encountered error {e} when attempting to load TurboJPEG.")
    raise e


RAW_EXTENSIONS = {".dng", ".cr2", ".nef", ".arw"}
JPEG_EXTENSIONS = {".jpg", ".jpeg"}
OTHER_IMAGE_EXTENSIONS = {".png", ".tif", ".tiff"}
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | JPEG_EXTENSIONS | OTHER_IMAGE_EXTENSIONS


class FileClient:
    """Class to handle file operations such as creating, removing and zipping directories."""

    def __init__(self, media_folder: str, session_id: str,) -> None:
        self.media_folder = media_folder
        self.session_id = session_id
        self.upload_dir = os.path.join(self.media_folder, self.session_id)

    def create_dir(self) -> None:
        """Create new dir in media_folder with name session_id."""
        os.makedirs(self.upload_dir, exist_ok=True)

    def remove_directory(self) -> None:
        """Delete everything cached for this session. Safe to call when there is nothing left."""
        for zip_path in (
            os.path.join(self.media_folder, f"{self.session_id}.zip"),
            # Older versions staged uploads through this archive; still cleaned up for their caches.
            os.path.join(self.media_folder, f"nonjpg_{self.session_id}.zip"),
        ):
            try:
                os.remove(zip_path)
                logging.info(f"Zipfile '{zip_path}' successfully removed.")
            except FileNotFoundError:
                logging.info(f"No file {zip_path} to remove.")

        shutil.rmtree(self.upload_dir, ignore_errors=True)
        logging.info(f"Directory '{self.upload_dir}' successfully removed.")

    def zip_dir(self, image_files: List[str], prefix: str = None) -> str:
        zip_filename: str = f"{prefix}_{self.session_id}.zip" if prefix else f"{self.session_id}.zip"
        write_zip(image_files, os.path.join(self.media_folder, zip_filename))
        return zip_filename


def write_zip(image_files: List[str], zip_path: str) -> None:
    """Write image_files into a zip at zip_path, leaving no half-written file behind on failure."""
    partial_path = f"{zip_path}.part"
    try:
        with ZipFile(partial_path, "w") as archive:
            for file in image_files:
                archive.write(file, os.path.basename(file))
        os.replace(partial_path, zip_path)
    except Exception:
        if os.path.exists(partial_path):
            os.remove(partial_path)
        raise


def generate_jpg_path(dng_path: str) -> str:
    directory, filename = os.path.split(dng_path)
    jpg_path = os.path.join(directory, os.path.splitext(filename)[0] + ".jpg")
    return jpg_path


def generate_preview_path(img_path: str) -> str:
    stem, extension = os.path.splitext(img_path)
    return f"{stem}_preview{extension}"


def generate_thumbnail_path(img_path: str) -> str:
    stem, extension = os.path.splitext(img_path)
    return f"{stem}_thumbnail{extension}"


def cache_stem(input_path: str) -> str:
    """Filename stem for the cached versions of a source image.

    The source extension is part of the stem: a camera writing IMG_1.dng next to IMG_1.jpg is the
    normal case, and both images have to end up with previews of their own.
    """
    name, extension = os.path.splitext(os.path.basename(input_path))
    return f"{name}_{extension.lstrip('.')}" if extension else name


def get_orientation(image_path):
    with open(image_path, "rb") as in_file:
        orientation = exifread.process_file(in_file).get("Image Orientation", None)
    if orientation is None:
        logging.info("Orientation: not present")
    else:
        logging.info(f"Orientation: {orientation} - Value: {orientation.values[0]}")
    return orientation


def load_jpeg_fast(image_path):
    with open(image_path, "rb") as f:
        img_array = turbo_jpeg.decode(f.read(), pixel_format=TJPF_BGR)
    return img_array


def get_extension(img_path: str) -> str:
    return os.path.splitext(img_path)[1].lower()


def load_raw(img_path: str) -> np.ndarray:
    """Decode a RAW file (DNG, CR2, NEF, ARW) to an 8-bit BGR array."""
    with rawpy.imread(img_path) as raw:
        image = raw.postprocess()
    return cv2.cvtColor(image, cv2.COLOR_RGB2BGR)  # rawpy returns RGB, OpenCV works in BGR


def load_generic_image(img_path: str) -> np.ndarray:
    """Decode PNG/TIFF (and anything else OpenCV or Pillow understands) to an 8-bit BGR array."""
    image = cv2.imread(img_path, cv2.IMREAD_COLOR)
    if image is None:  # cv2 returns None rather than raising, e.g. for non-ASCII paths on Windows
        with Image.open(img_path) as pil_image:
            image = cv2.cvtColor(np.array(pil_image.convert("RGB")), cv2.COLOR_RGB2BGR)
    return image


def load_image(img_path: str) -> np.ndarray:
    if not os.path.exists(img_path):
        raise FileNotFoundError(img_path)

    extension = get_extension(img_path)
    if extension in RAW_EXTENSIONS:
        return load_raw(img_path)
    if extension in JPEG_EXTENSIONS:
        return load_jpeg_fast(img_path)
    return load_generic_image(img_path)


def save_image(img: np.ndarray, save_path: str) -> None:
    """ Wrapper for cv2 imwrite to avoid imports in app. """
    cv2.imwrite(save_path, img)


def resize_image(image: np.ndarray, height: int = 224, width: int = 224):
    """ Syntactic sugar for resizing image to specified resolution. """
    assert image.shape[-1] == 3
    return cv2.resize(image, (width, height))


def transpose_image(image, orientation):
    """See Orientation in https://www.exif.org/Exif2-2.PDF for details."""
    if orientation is None or not orientation.values:
        return image
    val = orientation.values[0]
    if val == 2:
        return np.fliplr(image)
    elif val == 3:
        return np.rot90(image, 2)
    elif val == 4:
        return np.flipud(image)
    elif val == 5:
        return np.rot90(np.flipud(image), -1)
    elif val == 6:
        return np.rot90(image, -1)
    elif val == 7:
        return np.rot90(np.flipud(image))
    elif val == 8:
        return np.rot90(image)
    # Orientation 1 means "already upright"; anything else is a tag we do not know how to act on.
    if val != 1:
        logging.info(f"Unknown EXIF orientation {val}, leaving the image as it is.")
    return image


def prepare_image(
    input_path: str, preview_max_resolution: int = 1000, thumbnail_max_resolution: int = 224,
    output_dir: str = None,
) -> tuple[str, str, str, np.ndarray]:
    """ Load image from file and create smaller version of it used for preview & thumbnail. """
    image = load_image(input_path)
    stem = cache_stem(input_path)

    if get_extension(input_path) in JPEG_EXTENSIONS:  # for jpegs, we have to apply the correct transformation
        orientation = get_orientation(input_path)
        image = transpose_image(image, orientation)
        display_path = input_path
    else:  # if image is non-jpg, add the jpg twin for ease of processing
        if output_dir:
            display_path = os.path.join(output_dir, stem + ".jpg")
        else:
            display_path = generate_jpg_path(input_path)
        save_image(image, display_path)

    # Generate thumbnail and preview image paths
    if output_dir:
        preview_path = os.path.join(output_dir, stem + "_preview.jpg")
        thumbnail_path = os.path.join(output_dir, stem + "_thumbnail.jpg")
    else:
        preview_path = generate_preview_path(display_path)
        thumbnail_path = generate_thumbnail_path(display_path)

    preview_height, preview_width = fit_image_dimensions(image, preview_max_resolution, preview_max_resolution)
    thumbnail_height, thumbnail_width = fit_image_dimensions(image, thumbnail_max_resolution, thumbnail_max_resolution)

    preview_img = resize_image(image, height=preview_height, width=preview_width)
    preview_pil = Image.fromarray(cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB))

    thumbnail_img = resize_image(image, height=thumbnail_height, width=thumbnail_width)
    thumbnail_pil = Image.fromarray(cv2.cvtColor(thumbnail_img, cv2.COLOR_BGR2RGB))

    preview_pil.save(preview_path)
    thumbnail_pil.save(thumbnail_path)

    return display_path, thumbnail_path, preview_path, image


def fit_image_dimensions(image: np.ndarray, max_height: int = 1000, max_width: int = 1000):
    """ Resize the image to a smaller resolution if max_resolution is exceeded. Maintain aspect ratio. """
    max_violating_dimension = np.argmax((image.shape[0] - max_height, image.shape[1] - max_width))
    resize_factor = (max_height, max_width)[max_violating_dimension] / image.shape[max_violating_dimension]
    resize_factor = min(resize_factor, 1.0)  # an image smaller than the limit is left alone, not blown up

    new_height = max(int(image.shape[0] * resize_factor), 1)
    new_width = max(int(image.shape[1] * resize_factor), 1)

    return new_height, new_width


