"""End-to-end tests for the review sweep.

Regression cover for three defects:
  * a sweep driven by like/drop never reached the "completed" state,
  * the endofline placeholder could be reviewed, which put a bogus path into the export,
  * sessions created before this change still carry an endofline row and must stay usable.
"""

import io
import os
import sys
import tempfile
import zipfile

import numpy as np
import pytest
from PIL import Image

# app.py resolves its database and media cache from the home directory at import time.
_SANDBOX_HOME = tempfile.mkdtemp(prefix="alembic-tests-")
os.environ["HOME"] = _SANDBOX_HOME
os.environ["USERPROFILE"] = _SANDBOX_HOME

app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", "app"))
sys.path.append(app_dir)
import app as alembic_app  # noqa: E402


@pytest.fixture
def client():
    return alembic_app.app.test_client()


def make_image_folder(tmp_path, filenames):
    folder = tmp_path / "photos"
    folder.mkdir()
    rng = np.random.default_rng(1234)
    for filename in filenames:
        pixels = rng.integers(0, 255, (120, 160, 3), dtype=np.uint8)
        Image.fromarray(pixels).save(str(folder / filename))
    return str(folder)


def create_session(client, tmp_path, filenames):
    response = client.post("/create_session_from_directory", json={"directory": make_image_folder(tmp_path, filenames)})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["session_id"]


def sweep(client, session_id, route):
    """Review every image through `route`, always acting on a side that holds an image.

    Returns True if the sweep passed through the state where a single image is left on screen.
    """
    opened = client.get(f"/open_session?session_id={session_id}").get_json()
    id_left, id_right = opened["img_id_left"], opened["img_id_right"]
    saw_single_image = False

    for _ in range(20):
        assert not (id_left is None and id_right is None), "both sides empty - the user has nothing to act on"
        saw_single_image = saw_single_image or id_left is None or id_right is None

        if id_left is not None:
            clicked_id, other_id, position = id_left, id_right, "left"
        else:
            clicked_id, other_id, position = id_right, id_left, "right"

        data = client.post(
            route,
            json={
                "session_id": session_id,
                "position": position,
                "clickedImageId": clicked_id,
                "otherImageId": other_id,
            },
        ).get_json()

        if data["status"] == "completed":
            return saw_single_image

        assert data["status"] == "next"
        id_left, id_right = data["img_id_left"], data["img_id_right"]
        assert id_left is None or id_right is None or id_left != id_right

    raise AssertionError(f"sweep through {route} never completed")


@pytest.mark.parametrize("route", ["/like_image", "/drop_image", "/continue_from"])
def test_sweep_reaches_completed(client, tmp_path, route):
    session_id = create_session(client, tmp_path, [f"img{i}.jpg" for i in range(4)])

    sweep(client, session_id, route)

    with alembic_app.app.app_context():
        assert alembic_app.get_percentage_reviewed(session_id) == 100


@pytest.mark.parametrize("route", ["/like_image", "/drop_image"])
def test_last_image_is_shown_on_its_own(client, tmp_path, route):
    """The final image stays on screen alone (empty other side) so the user can still decide on it."""
    session_id = create_session(client, tmp_path, [f"img{i}.jpg" for i in range(4)])

    assert sweep(client, session_id, route) is True


def test_single_image_session_opens_with_one_empty_side(client, tmp_path):
    session_id = create_session(client, tmp_path, ["only.jpg"])

    opened = client.get(f"/open_session?session_id={session_id}").get_json()

    assert opened["img_id_left"] is not None
    assert opened["img_id_right"] is None


def test_export_after_full_sweep_contains_exactly_the_kept_files(client, tmp_path):
    filenames = [f"img{i}.jpg" for i in range(4)]
    session_id = create_session(client, tmp_path, filenames)

    sweep(client, session_id, "/like_image")

    response = client.get(f"/download?session_id={session_id}")
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert sorted(archive.namelist()) == sorted(filenames)


def add_legacy_endofline_row(session_id):
    """Recreate the sentinel row that older versions appended to every session."""
    with alembic_app.app.app_context():
        alembic_app.add_embedding(
            session_id,
            alembic_app.ENDOFLINE,
            alembic_app.ENDOFLINE,
            alembic_app.ENDOFLINE,
            alembic_app.ENDOFLINE,
            np.random.rand(384) * -1000,
        )
        return (
            alembic_app.Embedding.query.filter_by(session_id=session_id, preview_path=alembic_app.ENDOFLINE).one().id
        )


def test_legacy_sentinel_is_never_offered_as_an_image(client, tmp_path):
    session_id = create_session(client, tmp_path, [f"img{i}.jpg" for i in range(3)])
    sentinel_id = add_legacy_endofline_row(session_id)

    opened = client.get(f"/open_session?session_id={session_id}").get_json()
    assert sentinel_id not in (opened["img_id_left"], opened["img_id_right"])

    with alembic_app.app.app_context():
        for embedding in alembic_app.Embedding.query.filter_by(session_id=session_id):
            if embedding.id == sentinel_id:
                continue
            assert alembic_app.get_nearest_neighbor(session_id, embedding.id) is not sentinel_id

    sweep(client, session_id, "/like_image")


def test_legacy_sentinel_cannot_be_reviewed_and_stays_out_of_the_export(client, tmp_path):
    session_id = create_session(client, tmp_path, ["img0.jpg", "img1.jpg"])
    sentinel_id = add_legacy_endofline_row(session_id)

    with alembic_app.app.app_context():
        alembic_app.update_image_status(sentinel_id, set_status_to="reviewed_keep")
        assert alembic_app.get_embedding(sentinel_id).status == "unreviewed"

        # A database corrupted by the old code still exports cleanly.
        alembic_app.get_embedding(sentinel_id).status = "reviewed_keep"
        alembic_app.db.session.commit()
        assert alembic_app.ENDOFLINE not in alembic_app.get_images_to_keep(session_id)


def test_resume_ignores_a_stored_sentinel_id(client, tmp_path):
    session_id = create_session(client, tmp_path, ["img0.jpg", "img1.jpg"])
    sentinel_id = add_legacy_endofline_row(session_id)

    with alembic_app.app.app_context():
        real_id = alembic_app.get_random_starting_image(session_id).id
        alembic_app.update_last_viewed(session_id, sentinel_id, real_id)

    opened = client.get(f"/open_session?session_id={session_id}").get_json()

    assert opened["img_id_left"] is None
    assert opened["img_id_right"] == real_id


def test_folder_without_readable_images_is_rejected(client, tmp_path):
    folder = tmp_path / "documents"
    folder.mkdir()
    (folder / "notes.txt").write_text("not an image")
    (folder / "broken.jpg").write_bytes(b"still not an image")
    sessions_before = len(client.get("/overview").get_json()["sessions"])

    response = client.post("/create_session_from_directory", json={"directory": str(folder)})

    assert response.status_code == 400
    assert response.get_json()["error"] == "no_supported_images"
    assert len(client.get("/overview").get_json()["sessions"]) == sessions_before


def test_import_reports_files_it_could_not_read(client, tmp_path):
    directory = make_image_folder(tmp_path, ["good.jpg"])
    with open(os.path.join(directory, "broken.png"), "wb") as broken:
        broken.write(b"not a png")

    payload = client.post("/create_session_from_directory", json={"directory": directory}).get_json()

    assert payload["image_count"] == 1
    assert payload["failed_count"] == 1


def test_export_writes_the_archive_to_a_chosen_destination(client, tmp_path):
    filenames = [f"img{i}.jpg" for i in range(3)]
    session_id = create_session(client, tmp_path, filenames)
    sweep(client, session_id, "/like_image")
    destination = tmp_path / "exports" / "selection.zip"
    destination.parent.mkdir()

    response = client.post("/download", json={"session_id": session_id, "destination": str(destination)})

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["path"] == str(destination)
    with zipfile.ZipFile(destination) as archive:
        assert sorted(archive.namelist()) == sorted(filenames)


@pytest.mark.parametrize(
    "destination, expected_error",
    [
        ("relative/selection.zip", "destination_not_absolute"),
        ("/nonexistent-directory-for-tests/selection.zip", "destination_directory_missing"),
    ],
)
def test_export_rejects_unusable_destinations(client, tmp_path, destination, expected_error):
    session_id = create_session(client, tmp_path, ["img0.jpg", "img1.jpg"])
    sweep(client, session_id, "/like_image")

    response = client.post("/download", json={"session_id": session_id, "destination": destination})

    assert response.status_code == 400
    assert response.get_json()["error"] == expected_error


def test_a_failed_export_leaves_no_partial_archive_behind(client, tmp_path):
    session_id = create_session(client, tmp_path, ["img0.jpg", "img1.jpg"])
    sweep(client, session_id, "/like_image")
    with alembic_app.app.app_context():
        kept = alembic_app.get_images_to_keep(session_id)
    os.remove(kept[0])  # e.g. the source folder lived on a drive that has since been unplugged
    destination = tmp_path / "selection.zip"

    response = client.post("/download", json={"session_id": session_id, "destination": str(destination)})

    assert response.status_code == 500
    assert response.get_json()["error"] == "export_failed"
    assert not destination.exists()
    assert not (tmp_path / "selection.zip.part").exists()
