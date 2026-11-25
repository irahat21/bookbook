"""CoverIndex - search books by a photo of their cover (SRS 4.9, UC-04 step 4, E3-E5).

Every cover is turned into a vector (an "image embedding") and saved as
data/covers/<book_id>.npy. A search photo is embedded the same way; the covers whose
vectors point in the most similar direction (cosine similarity) are the best matches.

Two embedders, picked by COVER_MODE in .env:
* MockCoverEmbedder (mock) - MOCK, no neural network: a colour histogram (which colours,
  roughly how much of each) plus a tiny 8x12 thumbnail (where things are). It recognises
  cropped, brightened, slightly rotated or JPEG-compressed photos of OUR generated covers;
  it understands nothing about content.
* OpenClipEmbedder (real) - OpenCLIP ViT-B/32 as in the SRS. Written, NOT installed or
  tested (packages in requirements-real.txt). Missing -> falls back to the labelled MOCK.
"""
import io
import threading

import numpy as np

from bookorbit import rules
from bookorbit.ai import media
from bookorbit.errors import ModelUnavailable

MOCK_MODEL_ID = "mock-cover-hist-thumb-v1"
# UC-04 E4: a best similarity below this means "no match". rules.COVER_MIN_SIM (0.25) is the
# SRS value for OpenCLIP; the MOCK's numbers are on another scale. Measured on the seeded
# covers: photos of a cover score >= 0.80 with it, faces / noise / blank pages <= 0.62
# against every cover (ASSUMPTIONS A-33).
COVER_MIN_SIM_MOCK = 0.70
NOT_AN_IMAGE = "Please choose a JPG or PNG image"          # UC-04 E3


def open_image(data: bytes):
    """Decode PNG/JPEG bytes with Pillow; ValueError (UC-04 E3) for anything else."""
    from PIL import Image, UnidentifiedImageError
    if not isinstance(data, (bytes, bytearray)) or not media.is_image(bytes(data)):
        raise ValueError(NOT_AN_IMAGE)
    try:
        img = Image.open(io.BytesIO(bytes(data)))
        img.load()
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise ValueError(NOT_AN_IMAGE) from e
    return img.convert("RGB")


class MockCoverEmbedder:
    is_mock = True
    model_id = MOCK_MODEL_ID
    min_sim = COVER_MIN_SIM_MOCK
    LAYOUT_WEIGHT = 2.0          # thumbnail vs histogram; 2.0 separated covers from non-covers best

    def __init__(self, reason: str = "COVER_MODE=mock"):
        self.mode_label = f"MOCK cover search ({reason})"

    def embed(self, img) -> np.ndarray:
        from PIL import Image
        hsv = np.asarray(img.convert("HSV").resize((60, 90)), dtype=float) / 256
        hist, _ = np.histogramdd(hsv.reshape(-1, 3), bins=(12, 4, 4), range=[(0, 1)] * 3)
        hist = np.sqrt(hist.ravel() / hist.sum())                 # square root: big areas dominate less
        hist = self._centre(hist)
        thumb = self._centre(np.asarray(img.convert("RGB").resize((8, 12), Image.BILINEAR), dtype=float).ravel())
        v = np.concatenate([hist, self.LAYOUT_WEIGHT * thumb])
        return v / np.linalg.norm(v)

    @staticmethod
    def _centre(v: np.ndarray) -> np.ndarray:
        """Subtract the mean so that "every image has some colour" does not count as similar."""
        v = v - v.mean()
        n = np.linalg.norm(v)
        return v / n if n else v


class OpenClipEmbedder:
    """Real mode (SRS 4.9): OpenCLIP. NOT TESTED - open_clip_torch and torch are not
    installed in this prototype; the first run downloads the model weights."""
    is_mock = False
    min_sim = rules.COVER_MIN_SIM

    def __init__(self, model_name: str, pretrained: str):
        try:
            import open_clip            # noqa: F401  (lazy: only in COVER_MODE=real)
            import torch
        except ImportError as e:
            raise ModelUnavailable("OpenCLIP is not installed (see requirements-real.txt)") from e
        self.torch = torch
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
        self.model.eval()
        self.model_id = f"openclip:{model_name}:{pretrained}"
        self.mode_label = f"Cover search: OpenCLIP {model_name}"

    def embed(self, img) -> np.ndarray:
        with self.torch.no_grad():
            v = self.model.encode_image(self.preprocess(img).unsqueeze(0))[0].cpu().numpy().astype(float)
        return v / np.linalg.norm(v)


def get_cover_embedder(cfg: dict):
    if cfg.get("COVER_MODE", "mock").strip().lower() == "real":
        try:
            return OpenClipEmbedder(cfg["OPENCLIP_MODEL"], cfg["OPENCLIP_PRETRAINED"])
        except Exception as e:          # not installed, weights not downloadable, ...
            return MockCoverEmbedder(f"OpenCLIP unavailable: {e}")
    return MockCoverEmbedder()


class CoverIndex:
    def __init__(self, fs, embedder):
        self.fs = fs
        self.embedder = embedder
        self.ids: list[str] = []
        self.matrix = np.zeros((0, 1))
        self.ready = False               # UC-04 E5 until build() has finished
        self.error = ""
        self._lock = threading.Lock()

    @property
    def is_mock(self) -> bool:
        return self.embedder.is_mock

    @property
    def mode_label(self) -> str:
        return self.embedder.mode_label

    @property
    def min_sim(self) -> float:
        return self.embedder.min_sim

    def _model_file(self):
        return self.fs.dir / "covers" / "index_model.txt"

    def build(self) -> None:
        """Start-up (background thread): embed covers that have no vector yet, or all of them
        if the vectors were made by another model (ASSUMPTIONS A-33)."""
        try:
            with self._lock:
                mf = self._model_file()
                same_model = mf.exists() and mf.read_text().strip() == self.embedder.model_id
                ids, rows = [], []
                for b in self.fs.load("books"):
                    cover = self.fs.resolve(b.get("cover_path"))
                    if cover is None or not cover.exists():
                        continue
                    vec = self.fs.resolve(b.get("cover_vec_path"))
                    if not same_model or vec is None or not vec.exists():
                        try:
                            self.add(b["book_id"], cover.read_bytes(), keep=False)
                        except ValueError:                    # unreadable cover: skip that book
                            continue
                        vec = self.fs.resolve(f"covers/{b['book_id']}.npy")
                    ids.append(b["book_id"])
                    rows.append(np.load(vec))
                mf.parent.mkdir(parents=True, exist_ok=True)
                mf.write_text(self.embedder.model_id)
                self.ids = ids
                self.matrix = np.stack(rows) if rows else np.zeros((0, 1))
                self.ready, self.error = True, ""
        except Exception as e:           # a broken model must not crash start-up (E5)
            self.ready, self.error = False, str(e)

    def embed_bytes(self, data: bytes) -> np.ndarray:
        return self.embedder.embed(open_image(data))

    def add(self, book_id: str, image: bytes, keep: bool = True) -> str:
        """Embed and store one cover (also used by UC-15 Add New Books in Phase 4)."""
        v = self.embed_bytes(image)
        rel = f"covers/{book_id}.npy"
        np.save(self.fs.resolve(rel), v)
        self.fs.update("books", "book_id", book_id, {"cover_vec_path": rel})
        if keep:
            self.ids.append(book_id)
            self.matrix = v[None, :] if self.matrix.shape[0] == 0 else np.vstack([self.matrix, v])
        return rel

    def query(self, vector: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        if not self.ids:
            return []
        sims = self.matrix @ vector                      # cosine: all vectors are unit length
        top = np.argsort(-sims)[:k]
        return [(self.ids[i], float(sims[i])) for i in top]
