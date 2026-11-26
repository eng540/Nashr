#!/bin/sh
# One explicit build command shared by Railway and Railpack, including redeploy.
set -eu
DEPS_DIR=${NASHR_DEPS_DIR:-/app/python-deps}
python -m pip install --no-cache-dir --disable-pip-version-check --no-binary=Pillow --target="$DEPS_DIR" .
export PYTHONPATH="$DEPS_DIR${PYTHONPATH:+:$PYTHONPATH}"
python -c 'import PIL, fastapi, uvicorn; print("Runtime dependency preflight:", PIL.__version__, PIL.__file__)'
python scripts/check_arabic_renderer.py
npm --prefix frontend ci
npm --prefix frontend run build
test -s frontend/dist/index.html
