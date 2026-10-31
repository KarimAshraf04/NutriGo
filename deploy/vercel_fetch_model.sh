#!/bin/sh
# Vercel build step: download the Swin model (89 MB, too big to upload reliably) from Hugging Face.
# It is the same file as backend/models/swin_food101/model_quantized.onnx; the sha256 check proves it.
set -e
OUT=backend/models/swin_food101/model_quantized.onnx
curl -fsSL -o "$OUT" https://huggingface.co/onnx-community/swin-finetuned-food101-ONNX/resolve/main/onnx/model_quantized.onnx
echo "a80994b195389eb16c6bfd65e55841e888bb09886e86dce0957e124ad44c64a8  $OUT" | sha256sum -c -
