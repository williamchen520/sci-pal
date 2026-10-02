# Build Environment Installation Guide

This guide will help you set up the offline build environment for Sci-Pal on your local GPU machine.

## Prerequisites
- Ubuntu 22.04 / 24.04
- NVIDIA GPU with CUDA support (GTX 1660 or better)
- Python 3.10+
- Docker (for GROBID)

---

## Step 1: System Dependencies

First install required system packages:
```bash
sudo apt update
sudo apt install -y \
    python3-dev \
    python3-venv \
    libgl1-mesa-glx \
    libglib2.0-0 \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-eng
```

---

## Step 2: Create Build Virtual Environment

It's recommended to use a separate virtual environment for building:
```bash
cd /path/to/sci-pal
python3 -m venv venv_build
source venv_build/bin/activate
```

---

## Step 3: Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r build_db/requirements-build.txt
```

---

## Step 4: Install PyTorch with CUDA

MinerU needs PyTorch with CUDA support. Install the appropriate version for your CUDA version:

**For CUDA 12.1 (recommended for GTX 4060):**
```bash
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**Verify PyTorch CUDA works:**
```python
python3 -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0)}')"
```

You should see `CUDA available: True` and your GPU name.

---

## Step 5: Set up GROBID Server

GROBID is best run via Docker. Start the GROBID server:

```bash
docker pull lfoppiano/grobid:0.8.0
docker run -t --rm -p 8070:8070 lfoppiano/grobid:0.8.0
```

Verify GROBID is running:
```bash
curl http://localhost:8070/api/isalive
# Should return plain text response
```

**Keep this terminal open while building papers.**

---

## Step 6: Download MinerU Models

MinerU will download models automatically on first run. To pre-download:
```bash
python3 -c "from magic_pdf.cli.common import common_parse; print('MinerU ready')"
```

This will download ~2GB of models on first run.

---

## Step 7: Test the Build Pipeline

Test with a sample PDF:
```bash
python -m build_db.build_paper path/to/your/sample.pdf
```

You should see output like:
```
============================================================
Starting parse pipeline for: sample.pdf
Paper ID: paper_sample_abc123

📝 Step 1: Running primary parser (MinerU)...
...
✅ Parse pipeline complete!
  - Paragraphs: 45
  - Figures: 3
  - Citations: 20
============================================================
```

---

## Troubleshooting

### Issue: CUDA out of memory
**Solution:** Use smaller batch size or run on CPU (slower but works)
- Edit `build_db/parsers/mineru_parser.py` and set device to "cpu"

### Issue: GROBID connection refused
**Solution:** Make sure GROBID Docker container is running on port 8070

### Issue: MinerU model download fails
**Solution:** Set HuggingFace mirror:
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

---

## Notes
- Build environment is only for your local machine with GPU
- Production server only needs the lightweight runtime requirements
- The database file `data/research.db` is all you need to copy to production
