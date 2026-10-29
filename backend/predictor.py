"""Food recognition for /api/predict.

Order of preference (set NUTRIGO_MODEL to force one: 'swin', 'onnx', 'keras', 'vit' or 'none'):
  0. backend/models/swin_food101/  (model_quantized.onnx or model.onnx + config.json + preprocessor_config.json)
       -> Swin-B fine-tuned on Food-101 (onnx-community/swin-finetuned-food101-ONNX, Apache-2.0):
          all 101 dishes, 91.4-92.1% on the Food-101 validation set, 88% top-1 / 94% top-3 on our
          101 Unsplash dish photos; runs on onnxruntime (no TensorFlow / PyTorch)
  1. backend/models/food_model.onnx + labels.json
       -> our ResNet50 converted with convert_to_onnx.py; runs on onnxruntime, so it works
          on Windows machines where App Control blocks TensorFlow's DLLs
  2. backend/models/food_model.keras + labels.json
       -> the same ResNet50 (11 Food-101 classes, 91.8% on the test split) on TensorFlow,
          images scaled by labels.json "rescale" (1/255)
  3. backend/models/food101_model.keras + labels.txt
       -> EfficientNetB0 from notebooks/train_food101.ipynb (101 classes, rescales inside)
  4. Hugging Face 'nateraw/food' ViT (101 classes; pip install transformers torch)
All return Food-101 class names (e.g. 'apple_pie'), which are our food_ids.
"""
import io
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.environ.get("NUTRIGO_MODEL_DIR", os.path.join(HERE, "models"))


class Predictor:
    name = "none"
    labels = []

    def available(self):
        return False

    def predict(self, image_bytes, k=5):
        raise RuntimeError("No recognition model loaded")


def read_labels(path):
    """labels.json {"class_names", "img_size", "rescale"} or labels.txt (one class per line)."""
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as fh:
            meta = json.load(fh)
        return meta["class_names"], tuple(meta.get("img_size", (224, 224))), meta.get("rescale")
    with open(path, encoding="utf-8") as fh:
        return [l.strip() for l in fh if l.strip()], (224, 224), None


class OnnxModel:
    """onnxruntime session with the same predict(x) call as a Keras model."""
    def __init__(self, path):
        import onnxruntime as ort
        self.session = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name

    def predict(self, x, verbose=0):
        return self.session.run(None, {self.input_name: x})[0]


class HFOnnxPredictor(Predictor):
    """Hugging Face image classifier exported to ONNX: config.json (id2label) + preprocessor_config.json
    (resize, rescale, mean/std normalise) + an ONNX file taking pixel_values [N, 3, H, W]."""
    MODEL_FILES = ("model_quantized.onnx", "model.onnx")  # the quantized one is 4x smaller, same accuracy

    def __init__(self, folder, model_file=None):
        import numpy as np
        with open(os.path.join(folder, "config.json"), encoding="utf-8") as fh:
            id2label = json.load(fh)["id2label"]
        with open(os.path.join(folder, "preprocessor_config.json"), encoding="utf-8") as fh:
            pre = json.load(fh)
        self.labels = [id2label[str(i)] for i in range(len(id2label))]
        size = pre.get("size", {"height": 224, "width": 224})
        self.img_size = (size["width"], size["height"])
        self.rescale = pre.get("rescale_factor", 1 / 255) if pre.get("do_rescale", True) else 1.0
        self.mean = np.array(pre.get("image_mean", [0.5] * 3), dtype="float32")
        self.std = np.array(pre.get("image_std", [0.5] * 3), dtype="float32")
        model_file = model_file or next(f for f in self.MODEL_FILES if os.path.exists(os.path.join(folder, f)))
        self.model = OnnxModel(os.path.join(folder, model_file))
        self.name = f"onnx:{os.path.basename(os.path.normpath(folder))} ({len(self.labels)} classes)"

    def available(self):
        return True

    def preprocess(self, image_bytes):
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize(self.img_size, Image.BICUBIC)
        x = (np.asarray(img, dtype="float32") * self.rescale - self.mean) / self.std
        return x.transpose(2, 0, 1)[None]

    def predict(self, image_bytes, k=5):
        import numpy as np
        logits = self.model.predict(self.preprocess(image_bytes))[0]
        probs = np.exp(logits - logits.max())
        probs /= probs.sum()
        top = probs.argsort()[::-1][:min(k, len(self.labels))]
        return [(self.labels[i], float(probs[i])) for i in top]


class KerasPredictor(Predictor):
    """Keras model, or anything with Keras' predict(x) such as OnnxModel."""
    def __init__(self, model_path, labels_path, model=None, kind="keras"):
        self.labels, self.img_size, self.rescale = read_labels(labels_path)
        if model is None:
            import tensorflow as tf
            model = tf.keras.models.load_model(model_path, compile=False)
        self.model = model
        self.name = f"{kind}:{os.path.splitext(os.path.basename(model_path))[0]} ({len(self.labels)} classes)"

    def available(self):
        return True

    def preprocess(self, image_bytes):
        import numpy as np
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize(self.img_size)
        x = np.asarray(img, dtype="float32")[None]
        return x * self.rescale if self.rescale else x  # EfficientNet rescales inside

    def predict(self, image_bytes, k=5):
        probs = self.model.predict(self.preprocess(image_bytes), verbose=0)[0]
        top = probs.argsort()[::-1][:min(k, len(self.labels))]
        return [(self.labels[i], float(probs[i])) for i in top]


class ViTPredictor(Predictor):
    name = "hf:nateraw/food (101 classes)"

    def __init__(self):
        from transformers import pipeline
        self.pipe = pipeline("image-classification", model="nateraw/food")
        self.labels = list(self.pipe.model.config.id2label.values())

    def available(self):
        return True

    def predict(self, image_bytes, k=5):
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return [(r["label"], float(r["score"])) for r in self.pipe(img, top_k=k)]


HF_ONNX_DIR = "swin_food101"
MODEL_CANDIDATES = [
    ("onnx", "food_model.onnx", "labels.json"),       # ResNet50, 11 classes, onnxruntime
    ("keras", "food_model.keras", "labels.json"),     # ResNet50, 11 classes (Kaggle run)
    ("keras", "food101_model.keras", "labels.txt"),   # EfficientNetB0, 101 classes (train_food101.ipynb)
]


def load_predictor():
    choice = os.environ.get("NUTRIGO_MODEL", "auto")
    if choice == "none":
        return Predictor()
    if choice in ("auto", "swin"):
        folder = os.path.join(MODEL_DIR, HF_ONNX_DIR)
        if any(os.path.exists(os.path.join(folder, f)) for f in HFOnnxPredictor.MODEL_FILES):
            try:
                return HFOnnxPredictor(folder)
            except Exception as e:  # pragma: no cover
                print(f"[predictor] could not load {HF_ONNX_DIR}: {e}")
    for kind, model_file, labels_file in MODEL_CANDIDATES:
        if choice not in ("auto", kind):
            continue
        m, l = os.path.join(MODEL_DIR, model_file), os.path.join(MODEL_DIR, labels_file)
        if os.path.exists(m) and os.path.exists(l):
            try:
                return KerasPredictor(m, l, model=OnnxModel(m) if kind == "onnx" else None, kind=kind)
            except Exception as e:  # pragma: no cover
                print(f"[predictor] could not load {model_file}: {e}")
    if choice in ("auto", "vit"):
        try:
            return ViTPredictor()
        except Exception as e:  # pragma: no cover
            print(f"[predictor] ViT not available ({e}); /api/predict will return 503")
    return Predictor()
