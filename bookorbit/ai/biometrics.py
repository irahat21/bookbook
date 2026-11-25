"""BiometricEngine - face / voice matching with embeddings (SRS 4.7, R1, R2).

Two implementations share one interface:

* MockBiometricEngine (default, BIOMETRIC_MODE=mock) - MOCK. A "sample" is a
  file the user picks (PNG/JPG photo or WAV clip) instead of a webcam frame or
  microphone recording. It turns a sample into a unit vector like the real
  models would, then applies the real cosine thresholds of R2:
    - each "person" gets a fixed random base vector (seeded from their id);
    - each file adds a small random offset (seeded from the file's bytes).
  Two different samples of the same person therefore score ~0.92 (match) and
  different people score ~0.0 (no match). The person id comes from a PNG text
  tag written by seed.py, or for any other photo from the file's hash. For
  voice the "person" is the clip's dominant pitch (rounded to 10 Hz).
* RealBiometricEngine (BIOMETRIC_MODE=real) - YOLOv8-face + FaceNet +
  Resemblyzer. Written in Phase 3 but NOT installed or tested; without its
  packages / weights it raises ModelUnavailable and get_engine falls back to
  the labelled mock.
"""
import hashlib
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

from bookorbit import rules
from bookorbit.ai import media
from bookorbit.errors import ModelUnavailable, NoFaceError, NoVoiceError, TemplateMissingError

FACE, VOICE = "FACE", "VOICE"
FACE_DIM, VOICE_DIM = 512, 256      # FaceNet / Resemblyzer vector sizes (SRS 4.7)
SAMPLE_NOISE = 0.3                   # per-file offset -> same-person cosine ~ 1/(1+0.3^2) = 0.92


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _unit_vector(seed_text: str, dim: int) -> np.ndarray:
    seed = int.from_bytes(hashlib.sha256(seed_text.encode()).digest()[:8], "big")
    v = np.random.default_rng(seed).standard_normal(dim)
    return v / np.linalg.norm(v)


class BiometricEngine:
    """Shared logic: enroll / verify only depend on the two embedding methods."""

    is_mock = False
    mode_label = ""

    def __init__(self, fs):
        self.fs = fs
        self.template_dir = Path(fs.dir) / "biometrics"

    # --- model-specific, overridden ----------------------------------------
    def detect_face(self, image):
        raise NotImplementedError

    def face_embedding(self, crop) -> np.ndarray:
        raise NotImplementedError

    def voice_embedding(self, audio) -> np.ndarray:
        raise NotImplementedError

    # --- shared ------------------------------------------------------------
    def embed(self, method: str, sample) -> np.ndarray:
        if method == FACE:
            return self.face_embedding(self.detect_face(sample))
        return self.voice_embedding(sample)

    def enroll(self, user_id: str, method: str, sample) -> str:
        """Compute and save the template; returns the .npy path (UC-01 step 5)."""
        v = self.embed(method, sample)  # raises NoFaceError / NoVoiceError
        self.template_dir.mkdir(parents=True, exist_ok=True)
        rel = f"biometrics/{user_id}_{method.lower()}.npy"   # relative to data/
        np.save(self.fs.resolve(rel), v)
        self.fs.append("biometrics", {
            "template_id": self.fs.next_id("biometrics", "T"), "user_id": user_id,
            "method": method, "vector_path": rel, "enrolled_at": now()})
        return rel

    def verify(self, user_id: str, method: str, sample) -> tuple[bool, float]:
        """(match?, cosine score) against the stored template (R2)."""
        t = next((r for r in self.fs.load("biometrics")
                  if r["user_id"] == user_id and r["method"] == method), None)
        path = self.fs.resolve(t["vector_path"]) if t else None
        if path is None or not path.exists():
            raise TemplateMissingError(
                f"No {method.lower()} template on file - use the other method or contact a Super-User")
        try:
            stored = np.load(path)
        except Exception as exc:  # corrupt file (UC-02 E6)
            raise TemplateMissingError("Stored template is corrupt - contact a Super-User") from exc
        live = self.embed(method, sample)
        score = cosine(stored, live)
        threshold = rules.FACE_THRESHOLD if method == FACE else rules.VOICE_THRESHOLD
        return score >= threshold, score


class MockBiometricEngine(BiometricEngine):
    """MOCK: samples are files; see the module docstring for how it works."""

    is_mock = True
    mode_label = "MOCK biometrics: choose a photo / WAV file instead of using the camera / microphone"

    def detect_face(self, image: bytes):
        if not isinstance(image, (bytes, bytearray)) or not media.is_image(image):
            raise NoFaceError("Make sure only your face is visible (the file is not a JPG/PNG photo)")
        tags = media.read_png_text(image)
        faces = int(tags.get("faces", "1"))  # demo files from seed.py carry a face count
        if faces == 0:
            raise NoFaceError("No face found - make sure only your face is visible")
        if faces > 1:
            raise NoFaceError("Several faces found - make sure only your face is visible")
        person = tags.get("person") or hashlib.sha256(image).hexdigest()
        return person, bytes(image)          # the "crop"

    def face_embedding(self, crop) -> np.ndarray:
        person, raw = crop
        base = _unit_vector("face:" + person, FACE_DIM)
        noise = _unit_vector("file:" + hashlib.sha256(raw).hexdigest(), FACE_DIM)
        v = base + SAMPLE_NOISE * noise
        return v / np.linalg.norm(v)

    def voice_embedding(self, audio: bytes) -> np.ndarray:
        try:
            samples, rate = media.decode_wav(bytes(audio))
        except (wave.Error, EOFError, TypeError, ValueError) as exc:
            raise NoVoiceError("Could not read the audio - please record again") from exc
        if len(samples) / rate < rules.MIN_VOICE_SECONDS:
            raise NoVoiceError("Recording too short - please speak for at least 2 seconds")
        spectrum = np.abs(np.fft.rfft(samples))
        freqs = np.fft.rfftfreq(len(samples), 1 / rate)
        pitch = int(round(freqs[int(np.argmax(spectrum[1:])) + 1] / 10.0) * 10)
        base = _unit_vector(f"voice:{pitch}", VOICE_DIM)
        noise = _unit_vector("file:" + hashlib.sha256(bytes(audio)).hexdigest(), VOICE_DIM)
        v = base + SAMPLE_NOISE * noise
        return v / np.linalg.norm(v)


class RealBiometricEngine(BiometricEngine):
    """YOLOv8-face + FaceNet + Resemblyzer (SRS 4.7). WRITTEN, NOT TESTED: the packages
    (requirements-real.txt) and the YOLOv8 face weights are not installed in this prototype.

    Capture stays file-based like the MOCK (the user picks a photo / WAV file), but the
    embeddings come from the real models, so the R2 thresholds apply to real vectors.
    Any missing package or weights file raises ModelUnavailable -> get_engine falls back
    to the labelled MOCK."""

    mode_label = "Real biometrics: YOLOv8-face + FaceNet + Resemblyzer"

    def __init__(self, fs, face_weights: str):
        super().__init__(fs)
        try:                                              # lazy: only in BIOMETRIC_MODE=real
            import torch
            from facenet_pytorch import InceptionResnetV1
            from resemblyzer import VoiceEncoder, preprocess_wav
            from ultralytics import YOLO
        except ImportError as e:
            raise ModelUnavailable(f"Real biometric packages are not installed ({e.name})") from e
        if not Path(face_weights).exists():
            raise ModelUnavailable(f"YOLOv8 face weights not found: {face_weights}")
        self.torch = torch
        self.detector = YOLO(face_weights)
        self.facenet = InceptionResnetV1(pretrained="vggface2").eval()
        self.voice = VoiceEncoder()
        self.preprocess_wav = preprocess_wav

    def detect_face(self, image: bytes):
        """Exactly one face, else NoFaceError (UC-01 E3, UC-02 E5)."""
        import io
        from PIL import Image
        if not isinstance(image, (bytes, bytearray)) or not media.is_image(bytes(image)):
            raise NoFaceError("Make sure only your face is visible (the file is not a JPG/PNG photo)")
        img = Image.open(io.BytesIO(bytes(image))).convert("RGB")
        boxes = self.detector(img, verbose=False)[0].boxes.xyxy.tolist()
        if not boxes:
            raise NoFaceError("No face found - make sure only your face is visible")
        if len(boxes) > 1:
            raise NoFaceError("Several faces found - make sure only your face is visible")
        x1, y1, x2, y2 = (int(v) for v in boxes[0])
        return img.crop((x1, y1, x2, y2))

    def face_embedding(self, crop) -> np.ndarray:
        x = np.asarray(crop.resize((160, 160)), dtype=np.float32)
        x = (x - 127.5) / 128.0                           # FaceNet's expected input range
        t = self.torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0)
        with self.torch.no_grad():
            v = self.facenet(t)[0].numpy().astype(float)  # 512 numbers
        return v / np.linalg.norm(v)

    def voice_embedding(self, audio: bytes) -> np.ndarray:
        try:
            samples, rate = media.decode_wav(bytes(audio))
        except (wave.Error, EOFError, TypeError, ValueError) as exc:
            raise NoVoiceError("Could not read the audio - please record again") from exc
        if len(samples) / rate < rules.MIN_VOICE_SECONDS:
            raise NoVoiceError("Recording too short - please speak for at least 2 seconds")
        v = self.voice.embed_utterance(self.preprocess_wav(samples, source_sr=rate)).astype(float)  # 256
        return v / np.linalg.norm(v)


def get_engine(fs, mode: str = "mock", face_weights: str = "") -> BiometricEngine:
    """Return the configured engine, falling back to the labelled MOCK when models are missing."""
    if mode == "real":
        try:
            return RealBiometricEngine(fs, face_weights)
        except ModelUnavailable as e:
            mock = MockBiometricEngine(fs)
            mock.mode_label = f"MOCK biometrics (real models unavailable: {e})"
            return mock
    return MockBiometricEngine(fs)
