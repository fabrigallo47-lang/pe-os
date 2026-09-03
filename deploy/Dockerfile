# Extraction test rig: all three PDF models + the side-by-side UI, on GPU.
#
# Python 3.13, not 3.14: paddlepaddle publishes no cp314 wheel, and that
# single fact is what made PaddleOCR-VL untestable locally. Granite and
# Docling are equally happy on 3.13, so one interpreter serves all three.
#
# Three venvs, because the three models demand three incompatible
# transformers majors -- this is not tidiness, it is the only way they
# coexist:
#     granite  transformers 5.16.1   (docling_core for DocTags)
#     docling  transformers 5.8.1    (docling 2.124.0 pins it down)
#     paddle   paddleocr 3.7.0       (its own runtime, no transformers)
FROM nvidia/cuda:12.6.2-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      software-properties-common ca-certificates curl git \
 && add-apt-repository -y ppa:deadsnakes/ppa && apt-get update \
 && apt-get install -y --no-install-recommends \
      python3.13 python3.13-venv python3.13-dev \
      libgl1 libglib2.0-0 poppler-utils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- granite venv: the VLM path used by tools/extract_v2_physical.py -------------
RUN python3.13 -m venv /venvs/granite \
 && /venvs/granite/bin/pip install --no-cache-dir -U pip \
 && /venvs/granite/bin/pip install --no-cache-dir \
      torch==2.14.0 torchvision==0.29.0 \
      transformers==5.16.1 docling_core==2.93.0 \
      pdfplumber==0.11.10 openpyxl==3.1.5 python-docx==1.2.0 \
      python-pptx==1.0.2 docx2python==3.7.1 email-reply-parser==0.5.12 \
      pypdfium2==5.13.0 pyyaml==6.0.3 einops

# --- docling venv: layout + TableFormer, pinned transformers ------------
RUN python3.13 -m venv /venvs/docling \
 && /venvs/docling/bin/pip install --no-cache-dir -U pip \
 && /venvs/docling/bin/pip install --no-cache-dir docling==2.124.0

# --- paddle venv: the only one needing paddlepaddle ---------------------
# GPU build here; the CPU wheel is what made this ~12s/chart locally.
RUN python3.13 -m venv /venvs/paddle \
 && /venvs/paddle/bin/pip install --no-cache-dir -U pip \
 && /venvs/paddle/bin/pip install --no-cache-dir \
      paddlepaddle-gpu==3.3.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/ \
 && /venvs/paddle/bin/pip install --no-cache-dir "paddleocr[doc-parser]==3.7.0"

COPY tools/ /app/tools/
COPY vault/ /app/vault/

# Model weights are NOT baked in (~4GB); they download to these volumes on
# first run and persist, so a rebuild does not re-fetch them.
ENV HF_HOME=/models/hf \
    PADDLE_PDX_CACHE_HOME=/models/paddlex \
    PE_OS_DOCLING_PYTHON=/venvs/docling/bin/python \
    PE_OS_UI_HOST=0.0.0.0
VOLUME ["/models"]

EXPOSE 4192
# PE_OS_UI_TOKEN must be supplied at run time; the UI refuses to bind
# 0.0.0.0 without it.
CMD ["/venvs/granite/bin/python", "tools/extraction_test_ui.py", "4192"]
