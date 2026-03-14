import logging
import os
import re
from typing import List, Optional, Tuple
from zipfile import ZipFile

import cv2
import exifread
import numpy as np
import rawpy
from PIL import ExifTags, Image
from skimage import io
from turbojpeg import TJPF_BGR, TJPF_RGB, TurboJPEG

try:
    turbo_jpeg = TurboJPEG()
except RuntimeError as e:
    logging.error(f"Encountered error {e} when attempting to load TurboJPEG.")
    raise e


class FileClient:
    """Class to handle file operations such as creating, removing and zipping directories."""

    def __init__(self, media_folder: str, session_id: str,) -> None:
        self.media_folder = media_folder
        self.session_id = session_id
        self.upload_dir = os.path.join(self.media_folder, self.session_id)

    def create_dir(self) -> None:
        """Create new dir in media_folder with name session_id."""
        new_dir: str = self.upload_dir
        assert not os.path.exists(new_dir)
        os.mkdir(new_dir)

    def remove_directory(self) -> None:
        dir_to_remove: str = self.upload_dir
        zip_to_remove: str = os.path.join(self.media_folder, f"{self.session_id}.zip")
        non_jpg_zip_to_remove: str = os.path.join(self.media_folder, f"nonjpg_{self.session_id}.zip")

        assert os.path.exists(dir_to_remove)

        try:
            os.remove(zip_to_remove)
            logging.info(f"Zipfile '{zip_to_remove}' successfully removed.")
        except FileNotFoundError as e:
            logging.error(f"No file {zip_to_remove} found: {e.strerror}")

        try:
            os.remove(non_jpg_zip_to_remove)
            logging.info(f"Non-jpg zipfile '{non_jpg_zip_to_remove}' successfully removed.")
        except FileNotFoundError as e:
            logging.info(
                f"No file {non_jpg_zip_to_remove} found. Assuming that all uploaded images are in jpeg format."
            )

        try:
            # Iterate over all files and subdirectories in the directory
            for root, dirs, files in os.walk(dir_to_remove, topdown=False):
                for file in files:
                    file_path = os.path.join(root, file)
                    os.remove(file_path)  # Remove each file

                for dir in dirs:
                    dir_path = os.path.join(root, dir)
                    os.rmdir(dir_path)  # Remove each subdirectory

            os.rmdir(dir_to_remove)  # After all files and subdirectories are removed, remove the empty directory itself
            logging.info(f"Directory '{dir_to_remove}' successfully removed.")
        except OSError as e:
            logging.info(f"Error: {dir_to_remove} : {e.strerror}")

    def zip_dir(self, image_files: List[str], prefix: str = None) -> str:
        zip_filename: str = f"{prefix}_{self.session_id}.zip" if prefix else f"{self.session_id}.zip"
        zip_filepath: str = os.path.join(self.media_folder, zip_filename)
        with ZipFile(zip_filepath, "w") as zip:
            for file in image_files:
                zip.write(file, os.path.basename(file))

        return zip_filename

    def remove_nonjpg_images(self, paths: List[str]) -> None:
        for p in paths:
            try:
                logging.info(f"Deleting: {p}")
                os.remove(p)
            except Exception as e:
                logging.error(f"Could not delete {p} - exception {e}")

    def unzip_nonjpg_dir(self, zip_file: str) -> str:
        logging.info("Unzipping nonjpg files!")
        assert os.path.exists(os.path.join(self.media_folder, zip_file))
        with ZipFile(os.path.join(self.media_folder, zip_file), "r") as zip_ref:
            zip_ref.extractall(self.upload_dir)


def generate_jpg_path(dng_path: str) -> str:
    directory, filename = os.path.split(dng_path)
    jpg_path = os.path.join(directory, os.path.splitext(filename)[0] + ".jpg")
    return jpg_path


def generate_preview_path(img_path: str) -> str:
    s = img_path.split(".")
    return f"{s[-2]}_preview.{s[-1]}"


def generate_thumbnail_path(img_path: str) -> str:
    s = img_path.split(".")
    return f"{s[-2]}_thumbnail.{s[-1]}"


def get_orientation(image_path):
    in_file = open(image_path, "rb")
    orientation = exifread.process_file(in_file).get("Image Orientation", None)
    logging.info(f"Orientation: {orientation} - Value: {orientation.values[0]}")
    return orientation


def load_jpeg_fast(image_path):
    with open(image_path, "rb") as f:
        img_array = turbo_jpeg.decode(f.read(), pixel_format=TJPF_BGR)
    return img_array


def load_image(img_path: str) -> np.ndarray:
    assert os.path.exists(img_path)

    if img_path.endswith(("dng", "DNG")):
        with rawpy.imread(img_path) as raw:
            image = raw.postprocess()
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)  # Convert the image to BGR format (OpenCV default)
    else:
        image = load_jpeg_fast(img_path)

    return image


def save_image(img: np.ndarray, save_path: str) -> None:
    """ Wrapper for cv2 imwrite to avoid imports in app. """
    cv2.imwrite(save_path, img)


def resize_image(image: np.ndarray, height: int = 224, width: int = 224):
    """ Syntactic sugar for resizing image to specified resolution. """
    assert image.shape[-1] == 3
    return cv2.resize(image, (width, height))


def transpose_image(image, orientation):
    """See Orientation in https://www.exif.org/Exif2-2.PDF for details."""
    if orientation == None:
        return image
    val = orientation.values[0]
    if val == 1:
        return image
    elif val == 2:
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


def prepare_image(
    input_path: str, preview_max_resolution: int = 1000, thumbnail_max_resolution: int = 224,
    output_dir: str = None,
) -> tuple[str, str, str, np.ndarray]:
    """ Load image from file and create smaller version of it used for preview & thumbnail. """
    image = load_image(input_path)
    stem = os.path.splitext(os.path.basename(input_path))[0]

    if input_path.lower().endswith(("jpg", "jpeg")):  # for jpegs, we have to apply the correct transformation
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

    new_height = int(image.shape[0] * resize_factor)
    new_width = int(image.shape[1] * resize_factor)

    return new_height, new_width


def extract_image_paths_from_url(url):
    """ Extracts the left and right image paths from the input string. """
    match = re.search(r"left=(.*?)/right=(.*)", url)
    if match:
        left_image_path = match.group(1)
        right_image_path = match.group(2)
        return left_image_path, right_image_path
    return None, None
