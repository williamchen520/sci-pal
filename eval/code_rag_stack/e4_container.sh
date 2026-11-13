#!/usr/bin/env bash
# Reproduce E4 L4 target tests in a fixed scanpy container.
set -euo pipefail

REPO="${1:-G:/repos/scanpy-1.12.5}"
IMAGE="${SCIPAL_E4_IMAGE:-scipal-base:py312}"

docker rm -f scipal-scanpy-l4 >/dev/null 2>&1 || true
docker run -d --name scipal-scanpy-l4 --entrypoint sleep \
  -v "${REPO}:/work:ro" -w /work "${IMAGE}" infinity >/dev/null

docker exec scipal-scanpy-l4 python -m pip install --no-cache-dir --only-binary=:all: \
  'scanpy==1.12.5' 'pytest==9.2.0' 'pandas==2.3.3'

docker exec scipal-scanpy-l4 python -m pytest -q --no-header \
  -o cache_dir=/tmp/pytest-cache \
  'tests/test_normalization.py::test_normalize_total' \
  'tests/test_score_genes.py::test_score_genes_sparse_vs_dense' \
  'tests/test_read_10x.py::test_read_10x_h5' \
  'tests/test_highly_variable_genes.py::test_runs' \
  'tests/test_pca.py::test_pca_shapes'
