"""Convert models/food_model.keras to models/food_model.onnx so the API runs on onnxruntime
(no TensorFlow needed on the server, which matters on Windows machines where App Control
blocks TensorFlow's DLLs).

Run this on Google Colab or Kaggle, not on that Windows machine:

    pip install -U "tensorflow>=2.20" tf2onnx onnx onnxruntime
    python convert_to_onnx.py food_model.keras food_model.onnx

It checks that both models give the same probabilities before you download the .onnx file.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
import tensorflow as tf


def convert(src, dst):
    model = tf.keras.models.load_model(src, compile=False)
    try:
        model.export(dst, format="onnx")  # Keras >= 3.8
    except Exception as e:
        print(f"Keras ONNX export failed ({e}); using SavedModel + tf2onnx")
        with tempfile.TemporaryDirectory() as tmp:
            saved = os.path.join(tmp, "saved_model")
            model.export(saved, format="tf_saved_model")
            subprocess.run([sys.executable, "-m", "tf2onnx.convert", "--saved-model", saved,
                            "--output", dst, "--opset", "17"], check=True)
    return model


def check(model, dst):
    import onnxruntime as ort
    session = ort.InferenceSession(dst, providers=["CPUExecutionProvider"])
    x = np.random.default_rng(0).random((2, 224, 224, 3), dtype=np.float32)  # images are scaled to 0-1
    diff = np.abs(model.predict(x, verbose=0) - session.run(None, {session.get_inputs()[0].name: x})[0]).max()
    print(f"max difference Keras vs ONNX: {diff:.2e}")
    assert diff < 1e-3, "ONNX model does not match the Keras model"


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "food_model.keras"
    dst = sys.argv[2] if len(sys.argv) > 2 else "food_model.onnx"
    check(convert(src, dst), dst)
    print(f"Saved {dst} ({os.path.getsize(dst) / 1e6:.0f} MB) -> copy it to backend/models/")
