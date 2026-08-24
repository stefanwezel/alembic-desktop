import datetime
import logging
import os
import random
import sys
import uuid
from typing import List, Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort
import utils
from dotenv import find_dotenv, load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

log_level = os.getenv("LOG_LEVEL", "ERROR").upper()
logging.basicConfig(level=log_level)

IMAGE_EXTENSIONS = utils.SUPPORTED_EXTENSIONS

# Sessions created before the sweep protocol allowed empty sides carry a synthetic "endofline" row.
# Nothing creates one any more, but existing databases still contain them, so they stay filtered out.
ENDOFLINE = "endofline"


def _get_onnx_model_path() -> str:
    """Resolve the ONNX model path for both dev and PyInstaller frozen modes."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "onnx_checkpoints", "efficientnet_b0.onnx")


def create_app():
    app = Flask(__name__)
    debug_mode = app.debug

    logging.info(f"Mode is set to {'development' if debug_mode else 'production'}")

    if app.debug:
        env_file = find_dotenv(".env.dev")
    else:
        env_file = find_dotenv(".env.prod")

    load_dotenv(env_file)

    app.secret_key = os.getenv("APP_SECRET_KEY", "desktop-secret")
    app.config["MODE"] = os.getenv("MODE")

    media_folder = os.getenv("MEDIA_FOLDER", os.path.expanduser("~/.alembic/cache"))
    os.makedirs(media_folder, exist_ok=True)
    app.config["MEDIA_FOLDER"] = media_folder

    db_path = os.path.expanduser("~/.alembic/alembic.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"

    model_path = _get_onnx_model_path()
    sess_options = ort.SessionOptions()
    sess_options.inter_op_num_threads = 1
    sess_options.intra_op_num_threads = 2
    app.config["ONNX_SESSION"] = ort.InferenceSession(model_path, sess_options=sess_options)
    logging.info(f"ONNX model loaded from {model_path}")

    return app


app = create_app()
CORS(app)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__: str = "users"
    id: int = db.Column(db.Integer, primary_key=True)
    email: str = db.Column(db.String(255), nullable=False, unique=True)
    nickname: str = db.Column(db.String(255))

    def __repr__(self) -> str:
        return f"User('{self.nickname}', '{self.email}')"


class Session(db.Model):
    __tablename__ = "sessions"
    id: str = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True)
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name: str = db.Column(db.String(255))
    creation_time: datetime.datetime = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now)
    last_access_time: datetime.datetime = db.Column(db.DateTime, nullable=False, default=datetime.datetime.now)
    last_viewed_left: str = db.Column(db.String(36), nullable=True)
    last_viewed_right: str = db.Column(db.String(36), nullable=True)
    has_been_downloaded: bool = db.Column(db.Boolean, default=False)

    def __repr__(self) -> str:
        return f"Session({self.id}', '{self.name}')"


class Embedding(db.Model):
    __tablename__ = "embeddings"
    id: str = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True)
    thumbnail_path: str = db.Column(db.String(255), nullable=False)
    preview_path: str = db.Column(db.String(255), nullable=False)
    display_path: str = db.Column(db.String(255), nullable=False)
    download_path: str = db.Column(db.String(255), nullable=False)
    session_id: str = db.Column(db.String(36), db.ForeignKey("sessions.id"), nullable=False)
    embedding_blob: bytes = db.Column(db.LargeBinary, nullable=False)
    status: str = db.Column(db.String(20), nullable=False, default="unreviewed")

    def set_embedding(self, vec: np.ndarray):
        self.embedding_blob = vec.astype(np.float32).tobytes()

    def get_embedding(self) -> np.ndarray:
        return np.frombuffer(self.embedding_blob, dtype=np.float32)

    def __repr__(self) -> str:
        return f"Embedding('{self.display_path}', '{self.download_path}', '{self.session_id}', '{self.status}')"


class AppMetadata(db.Model):
    __tablename__ = "app_metadata"
    key: str = db.Column(db.String(64), primary_key=True)
    value: str = db.Column(db.String(255), nullable=False)


CURRENT_SCHEMA_VERSION = "2"


def add_user(email: str, nickname="") -> User:
    new_user = User(email=email, nickname=nickname)
    db.session.add(new_user)
    db.session.commit()
    return new_user


def add_session_for_user(email: str) -> Session:
    user = User.query.filter_by(email=email).one()
    num_existing_sessions = len(get_sessions_for_user(email))

    new_session = Session(user_id=user.id)
    new_session.name = f"Session {num_existing_sessions+1}"
    new_session.creation_time = datetime.datetime.now()
    db.session.add(new_session)
    db.session.commit()
    return new_session


def get_sessions_for_user(email: str) -> List[Session]:
    try:
        user = User.query.filter_by(email=email).one()
        logging.info(f"User: {user}")
        sessions = Session.query.filter_by(user_id=user.id).order_by(Session.creation_time.desc()).all()
        return sessions
    except Exception as e:
        logging.info(f"Something went wrong when attempting to fetch sessions for user {email}")
        raise e


def add_embedding(
    session_id: str,
    thumbnail_path: str,
    preview_path: str,
    display_path: str,
    download_path: str,
    embedding: np.ndarray,
) -> None:
    """ Add single embedding to table. """
    try:
        new_embedding = Embedding(
            session_id=session_id,
            thumbnail_path=thumbnail_path,
            preview_path=preview_path,
            display_path=display_path,
            download_path=download_path,
        )
        new_embedding.set_embedding(embedding)
        db.session.add(new_embedding)
        db.session.commit()

    except Exception as e:
        logging.info(f"Something went wrong when adding embedding for {session_id}")
        raise e


def remove_session_from_db(session_id: str) -> None:
    session = get_session(session_id)
    if session is None:
        return

    for embedding in Embedding.query.filter_by(session_id=session.id).all():
        db.session.delete(embedding)
    db.session.delete(session)
    db.session.commit()


def get_images_to_keep(session_id: str) -> List[str]:
    """ Get set of images where status is 'reviewed_keep'. """
    embeddings = Embedding.query.filter(
        Embedding.session_id == session_id,
        Embedding.status == "reviewed_keep",
        Embedding.download_path != ENDOFLINE,
    ).all()
    return [embedding.download_path for embedding in embeddings]


def get_random_starting_image(session_id: str) -> Optional[Embedding]:
    unreviewed_images = Embedding.query.filter(
        Embedding.session_id == session_id, Embedding.status == "unreviewed", Embedding.display_path != ENDOFLINE,
    ).all()
    if unreviewed_images:
        return random.choice(unreviewed_images)
    else:
        return None


def get_embedding(embedding_id: str) -> Optional[Embedding]:
    return Embedding.query.filter_by(id=embedding_id).first()


def get_session(session_id: str) -> Optional[Session]:
    return Session.query.filter_by(id=session_id).first()


def load_unreviewed_vectors(session_id: str) -> Tuple[List[str], np.ndarray]:
    """Every unreviewed image of a session as (ids, vectors), the vectors stacked into one array.

    Only the id and the blob are fetched: materialising whole rows built an ORM object per image,
    which dominated the cost of a click on a large session.
    """
    rows = (
        db.session.query(Embedding.id, Embedding.embedding_blob)
        .filter(
            Embedding.session_id == session_id,
            Embedding.status == "unreviewed",
            Embedding.preview_path != ENDOFLINE,
        )
        .all()
    )
    if not rows:
        return [], np.empty((0, 0), dtype=np.float32)

    ids = [row[0] for row in rows]
    vectors = np.frombuffer(b"".join(row[1] for row in rows), dtype=np.float32).reshape(len(rows), -1)
    return ids, vectors


def nearest_id(ids: List[str], vectors: np.ndarray, query_vec: np.ndarray, excluded) -> Optional[str]:
    """Id of the vector closest to query_vec in L2, skipping `excluded`. None when none is left."""
    if not ids:
        return None

    distances = np.square(vectors - query_vec).sum(axis=1)
    for index, image_id in enumerate(ids):
        if image_id in excluded:
            distances[index] = np.inf

    nearest = int(np.argmin(distances))
    return ids[nearest] if np.isfinite(distances[nearest]) else None


def get_nearest_neighbor(session_id: str, query_image_id: str, exclude_ids=None) -> Optional[Embedding]:
    """Get the nearest unreviewed neighbor to the query image using numpy L2 distance.

    `exclude_ids` lets callers skip images besides the query (e.g. the other
    currently-displayed image during a speculative prefetch).
    Returns None when the session holds no further image to show.
    """
    query_emb = get_embedding(query_image_id)
    if query_emb is None:
        return None

    ids, vectors = load_unreviewed_vectors(session_id)
    excluded = set(exclude_ids or []) | {query_image_id}
    nearest = nearest_id(ids, vectors, query_emb.get_embedding(), excluded)
    return get_embedding(nearest) if nearest is not None else None


def resolve_visible_id(image_id: Optional[str]) -> Optional[str]:
    """Map an image id to None when it cannot be displayed (missing row, or a legacy sentinel)."""
    if not image_id:
        return None
    embedding = Embedding.query.filter_by(id=image_id).first()
    if embedding is None or embedding.preview_path == ENDOFLINE:
        return None
    return image_id


def update_image_status(update_image_id: Optional[str], set_status_to: str = "reviewed_discard") -> None:
    if update_image_id is None:  # empty side of the pair, nothing to review
        return
    try:
        embedding = Embedding.query.filter_by(id=update_image_id).one()
        if embedding.preview_path == ENDOFLINE:  # legacy sentinel row, not a real image
            logging.error(f"Refusing to review the endofline placeholder {update_image_id}.")
            return
        embedding.status = set_status_to
        db.session.commit()
    except Exception as e:
        logging.error(f"Encountered exception {e} when trying to update {update_image_id}.")


def update_last_viewed(session_id: str, last_viewed_left: str, last_viewed_right: str) -> None:
    """ Stores image ids last displayed on the decision page. """
    try:
        session = Session.query.filter_by(id=session_id).one()
        session.last_viewed_left = last_viewed_left
        session.last_viewed_right = last_viewed_right
        db.session.commit()

    except Exception as e:
        logging.error(e)


def get_percentage_reviewed(session_id: str) -> int:
    """ This is used to display session progress on the overview page. """
    count_all = len(
        Embedding.query.filter(Embedding.session_id == session_id, Embedding.preview_path != ENDOFLINE).all()
    )
    count_reviewed = len(
        Embedding.query.filter(
            Embedding.session_id == session_id,
            Embedding.status.in_(["reviewed_keep", "reviewed_discard"]),
            Embedding.preview_path != ENDOFLINE,
        ).all()
    )
    try:
        percentage_reviewed = (count_reviewed / count_all) * 100
        return int(percentage_reviewed)

    except ZeroDivisionError:
        return 0


def preprocess_for_onnx(image: np.ndarray) -> np.ndarray:
    """Preprocess an image for EfficientNet B0 ONNX inference.

    Input: HWC BGR uint8 numpy array (any resolution).
    Output: (1, 3, 224, 224) float32 array, ImageNet-normalized.
    """
    img = cv2.resize(image, (224, 224))
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    img = (img - mean) / std
    img = img.transpose((2, 0, 1))
    img = np.expand_dims(img, axis=0)
    return img


def process_onnx_embedding(embedding: np.ndarray) -> np.ndarray:
    """Post-process ONNX output to 384-dim vector using numpy/cv2.

    Replicates the torch-based process_embedding() from embedding_api without the torch dependency.
    """
    embedding = np.transpose(embedding, (0, 2, 1, 3))
    slice_2d = embedding[0, 0, :, :]
    resized = cv2.resize(slice_2d, (1, 384), interpolation=cv2.INTER_LINEAR)
    vec = resized[:, 0]
    return vec.astype(np.float32)


def generate_embedding(image: np.ndarray) -> np.ndarray:
    """Generate a 384-dim embedding using EfficientNet B0 ONNX model."""
    ort_session = app.config["ONNX_SESSION"]
    preprocessed = preprocess_for_onnx(image)
    input_name = ort_session.get_inputs()[0].name
    ort_output = ort_session.run(None, {input_name: preprocessed})[0]
    vec = process_onnx_embedding(ort_output)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "Alembic API"})


@app.route("/serve_image")
def serve_image():
    img_id = request.args.get("img_id")
    version = request.args.get("version")

    embedding = get_embedding(img_id)

    if embedding is None:
        return jsonify({"error": "image_not_found"}), 404

    if embedding.preview_path == ENDOFLINE:
        return jsonify({"error": "end_of_line"}), 404

    if version == "thumbnail":
        return send_file(embedding.thumbnail_path)
    if version == "preview":
        return send_file(embedding.preview_path)
    elif version == "display":
        return send_file(embedding.display_path)
    else:
        logging.error(f"Invalid image version {version} requested.")
        return jsonify({"error": "invalid_version"}), 400


def _next_pair_response(session_id: str, id_left: str, id_right: str):
    """Persist last-viewed and return the canonical next-pair payload."""
    update_last_viewed(session_id, id_left, id_right)
    return jsonify({"status": "next", "img_id_left": id_left, "img_id_right": id_right})


def _review_clicked_and_advance(set_status_to: str):
    """Review the clicked image, keep the other one on screen and refill the freed side.

    The freed side is None once the session runs out of images: the remaining image is
    then shown on its own until the user decides on it too, which completes the session.
    """
    clicked_id = request.json.get("clickedImageId")
    other_id = request.json.get("otherImageId")
    position = request.json.get("position")
    session_id = request.json.get("session_id")

    update_image_status(clicked_id, set_status_to=set_status_to)

    if other_id is None:  # the clicked image was the last one on screen
        return jsonify({"status": "completed"})

    nearest_neighbor = get_nearest_neighbor(session_id, other_id)
    nearest_id = nearest_neighbor.id if nearest_neighbor is not None else None

    # Clicked side gets replaced with nearest; other stays where it was.
    if position == "left":
        id_left, id_right = nearest_id, other_id
    else:
        id_left, id_right = other_id, nearest_id

    return _next_pair_response(session_id, id_left, id_right)


@app.route("/like_image", methods=["POST"])
def like_image():
    """ Save image as 'reviewed_keep' and display nearest neighbor. """
    return _review_clicked_and_advance("reviewed_keep")


@app.route("/drop_image", methods=["POST"])
def drop_image():
    """ Save image as 'reviewed_discard' and display nearest neighbor. """
    return _review_clicked_and_advance("reviewed_discard")


@app.route("/continue_from", methods=["POST"])
def continue_from():
    """ Save image as 'reviewed_keep', other image as 'reviewed_discard' and display nearest neighbor. """
    clicked_id = request.json.get("clickedImageId")
    other_id = request.json.get("otherImageId")
    position = request.json.get("position")
    session_id = request.json.get("session_id")

    update_image_status(clicked_id, set_status_to="reviewed_keep")
    update_image_status(other_id, set_status_to="reviewed_discard")

    nearest_neighbor = get_nearest_neighbor(session_id, clicked_id)

    if nearest_neighbor is None:  # both displayed images are reviewed and nothing is left
        return jsonify({"status": "completed"})

    # Clicked stays on its side; nearest appears opposite.
    if position == "left":
        id_left, id_right = clicked_id, nearest_neighbor.id
    else:
        id_left, id_right = nearest_neighbor.id, clicked_id

    return _next_pair_response(session_id, id_left, id_right)


@app.route("/next_candidates", methods=["GET"])
def next_candidates():
    """Return the two images most likely to appear after the user's next action.

    Given the current (left, right) pair, computes:
      - next_if_stays_left  = nearestOf(left)  excluding right  — covers continue-from-left, like-right, drop-right.
      - next_if_stays_right = nearestOf(right) excluding left   — covers continue-from-right, like-left, drop-left.
    Returns null for either side when nothing is left to prefetch (frontend skips it).
    """
    session_id = request.args.get("session_id")
    id_left = request.args.get("id_left")
    id_right = request.args.get("id_right")

    if not id_left or not id_right:  # one side is already empty, there is nothing to warm up
        return jsonify({"next_if_stays_left": None, "next_if_stays_right": None})

    try:
        query_left = get_embedding(id_left)
        query_right = get_embedding(id_right)
        if query_left is None or query_right is None:
            return jsonify({"next_if_stays_left": None, "next_if_stays_right": None})

        # Both answers come out of one fetch; the candidate set is the same for either side.
        ids, vectors = load_unreviewed_vectors(session_id)
        on_screen = {id_left, id_right}
        if_stays_left = nearest_id(ids, vectors, query_left.get_embedding(), on_screen)
        if_stays_right = nearest_id(ids, vectors, query_right.get_embedding(), on_screen)
    except Exception as e:
        logging.error(f"next_candidates failed: {e}")
        return jsonify({"next_if_stays_left": None, "next_if_stays_right": None})

    return jsonify({"next_if_stays_left": if_stays_left, "next_if_stays_right": if_stays_right})


@app.route("/has_been_downloaded", methods=["GET"])
def has_been_downloaded():
    session_id = request.args.get("session_id")
    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "session_not_found"}), 404

    return jsonify({"has_been_downloaded": session.has_been_downloaded})


@app.route("/open_session", methods=["GET"])
def open_session():
    """Helper function to let 'sweep' know that it was just opened."""
    session_id = request.args.get("session_id")

    session = get_session(session_id)
    if session is None:
        return jsonify({"error": "session_not_found"}), 404

    # Drop ids that cannot be displayed any more (never viewed, or a legacy endofline sentinel).
    img_id_left = resolve_visible_id(session.last_viewed_left)
    img_id_right = resolve_visible_id(session.last_viewed_right)

    if img_id_left is None and img_id_right is None:
        # Newly created session, or a stored pair that no longer resolves to real images.
        random_starting_image = get_random_starting_image(session_id)
        if random_starting_image is None:
            # Session has no reviewable images (e.g. every file failed to import).
            logging.error(f"Session {session_id} has no usable images to open.")
            return jsonify({"error": "no_images"}), 422
        nearest_neighbor = get_nearest_neighbor(session_id, random_starting_image.id)
        img_id_left = random_starting_image.id
        img_id_right = nearest_neighbor.id if nearest_neighbor is not None else None
        logging.info(f"Starting from random image {img_id_left} and nearest neighbor {img_id_right}")
    else:
        logging.info(f"Starting from last viewed images {img_id_left} and {img_id_right}")

    update_last_viewed(session_id, img_id_left, img_id_right)
    return jsonify({"session": session_id, "img_id_left": img_id_left, "img_id_right": img_id_right})


@app.route("/end_session", methods=["GET"])
def end_session():
    logging.info("Button clicked - returning to session overview...")
    return jsonify({"status": "ok"})


@app.route("/overview")
def overview():
    """Renders an overview page listing sessions for a given user."""
    with app.app_context():
        sessions_list = get_sessions_for_user("desktop@localhost")

    session_names = {}
    session_thumbnails = {}
    session_progress_percentage = {}

    for session in sessions_list:
        embeddings = (
            Embedding.query.filter(Embedding.session_id == session.id, Embedding.preview_path != ENDOFLINE)
            .limit(3)
            .all()
        )
        session_names[session.id] = session.name
        session_thumbnails[session.id] = [str(embedding.id) for embedding in embeddings]
        session_progress_percentage[session.id] = get_percentage_reviewed(session.id)

    return jsonify({
        "sessions": [
            {
                "id": str(sess.id),
                "name": session_names[sess.id],
                "thumbnails": session_thumbnails[sess.id],
                "progress": session_progress_percentage[sess.id]
            }
            for sess in sessions_list
        ]
    })


@app.route("/completed", methods=["GET"])
def completed():
    return jsonify({"status": "completed"})


@app.route("/create_session_from_directory", methods=["POST"])
def create_session_from_directory():
    directory = request.json.get("directory") or ""
    # A typed path may be "~/photos"; the folder picker always hands over an absolute one.
    directory = os.path.abspath(os.path.expanduser(directory.strip()))

    if not os.path.isdir(directory):
        return jsonify({"error": "invalid_directory"}), 400

    session = add_session_for_user("desktop@localhost")
    cache_dir = os.path.join(app.config["MEDIA_FOLDER"], str(session.id))
    file_client = utils.FileClient(media_folder=app.config["MEDIA_FOLDER"], session_id=str(session.id))
    file_client.create_dir()

    count = 0
    failed_count = 0
    for filename in sorted(os.listdir(directory)):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        filepath = os.path.join(directory, filename)
        try:
            display_path, thumbnail_path, preview_path, numpy_img = utils.prepare_image(
                filepath, output_dir=cache_dir
            )
            embedding = generate_embedding(numpy_img)
            add_embedding(str(session.id), thumbnail_path, preview_path, display_path, filepath, embedding)
            count += 1
        except Exception as e:
            failed_count += 1
            logging.error(f"Failed to process {filepath}: {e}")

    if count == 0:
        # Nothing usable in there - don't leave an empty session behind for the user to clean up.
        logging.error(f"No supported images imported from {directory}, discarding session {session.id}.")
        remove_session_from_db(str(session.id))
        file_client.remove_directory()
        return jsonify({"error": "no_supported_images", "failed_count": failed_count}), 400

    return jsonify({"session_id": str(session.id), "image_count": count, "failed_count": failed_count})


def check_destination(destination: str) -> Optional[str]:
    """Return an error code if the export cannot be written to `destination`, None if it can."""
    if not os.path.isabs(destination):
        return "destination_not_absolute"
    parent = os.path.dirname(destination)
    if not os.path.isdir(parent):
        return "destination_directory_missing"
    if not os.access(parent, os.W_OK):
        return "destination_not_writable"
    return None


def mark_downloaded(session_id: str) -> None:
    session = get_session(session_id)
    if session is None or get_percentage_reviewed(session_id) != 100:
        return
    session.has_been_downloaded = True
    db.session.commit()


@app.route("/download", methods=["GET", "POST"])
def download_subset():
    """Export all images with status 'reviewed_keep'.

    The desktop app posts a `destination` picked with the native save dialog and the archive is
    written straight there. A full-resolution export does not fit in the webview's memory, so
    handing it back over HTTP is only for a frontend opened in a plain browser.
    """
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id") or request.args.get("session_id")
    destination = payload.get("destination")
    file_client = utils.FileClient(media_folder=app.config["MEDIA_FOLDER"], session_id=session_id)

    if not os.path.exists(file_client.upload_dir):
        return jsonify({"error": "session_not_found"}), 404

    subset = get_images_to_keep(session_id)
    if not subset:
        return jsonify({"error": "no_images_selected"}), 400

    if destination is not None:
        error = check_destination(destination)
        if error:
            return jsonify({"error": error}), 400
        try:
            utils.write_zip(subset, destination)
        except OSError as e:
            # A source file moved or the target filled up mid-write - both are the user's to fix.
            logging.error(f"Could not export session {session_id} to {destination}: {e}")
            return jsonify({"error": "export_failed", "detail": str(e)}), 500
        mark_downloaded(session_id)
        return jsonify({"status": "written", "path": destination, "image_count": len(subset)})

    zip_filename = file_client.zip_dir(subset)
    mark_downloaded(session_id)
    return send_from_directory(app.config["MEDIA_FOLDER"], zip_filename, as_attachment=True)


@app.route("/drop_session/<string:session_id>")
def drop_session(session_id):
    """Remove entries in 'embeddings' and 'sessions', remove related files."""
    if get_session(session_id) is None:
        return jsonify({"error": "session_not_found"}), 404

    remove_session_from_db(session_id)
    logging.info(f"Session {session_id} successfully removed from database.")

    client = utils.FileClient(media_folder=app.config["MEDIA_FOLDER"], session_id=session_id)
    client.remove_directory()

    return jsonify({"status": "deleted", "session_id": session_id})


@app.route("/rename_session/<session_id>", methods=["POST"])
def rename_session(session_id):
    data = request.json

    try:
        session = Session.query.filter_by(id=session_id).one()
        new_name = data.get("new_name")
        session.name = new_name
        db.session.commit()
        return jsonify({"success": True, "new_name": new_name})
    except Exception as e:
        logging.error(f"Something went wrong when trying to rename session {session_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 404


def prune_orphaned_cache() -> List[str]:
    """Delete cached files belonging to sessions that no longer exist.

    A schema bump wipes every session row but leaves ~/.alembic/cache/<session_id>/ in place, and
    an import interrupted halfway can strand a directory too. Nothing in the UI reaches those
    files afterwards, so they would sit there growing across upgrades.
    """
    media_folder = app.config["MEDIA_FOLDER"]
    if not os.path.isdir(media_folder):
        return []

    live_ids = {str(session.id) for session in Session.query.all()}
    cached_ids = set()
    for entry in os.listdir(media_folder):
        if os.path.isdir(os.path.join(media_folder, entry)):
            cached_ids.add(entry)
        elif entry.endswith(".zip"):
            cached_ids.add(entry[: -len(".zip")].removeprefix("nonjpg_"))

    orphans = sorted(cached_ids - live_ids)
    for session_id in orphans:
        logging.info(f"Removing cached files for session {session_id}, which no longer exists.")
        utils.FileClient(media_folder=media_folder, session_id=session_id).remove_directory()
    return orphans


with app.app_context():
    db.create_all()

    # Migrate incompatible embeddings when schema version changes
    try:
        version_row = AppMetadata.query.filter_by(key="schema_version").first()
        if version_row is None or version_row.value != CURRENT_SCHEMA_VERSION:
            logging.warning("Incompatible embedding format detected. Clearing existing sessions.")
            Embedding.query.delete()
            Session.query.delete()
            db.session.commit()
            if version_row is None:
                db.session.add(AppMetadata(key="schema_version", value=CURRENT_SCHEMA_VERSION))
            else:
                version_row.value = CURRENT_SCHEMA_VERSION
            db.session.commit()
            logging.info(f"Database migrated to schema version {CURRENT_SCHEMA_VERSION}.")
    except Exception:
        pass  # Table might not exist yet on first run

    try:
        orphans = prune_orphaned_cache()
        if orphans:
            logging.warning(f"Removed cached files for {len(orphans)} session(s) that no longer exist.")
    except Exception as e:
        logging.error(f"Could not prune the media cache: {e}")

    try:
        add_user("desktop@localhost", "Desktop User")
    except Exception:
        pass  # User already exists
