# syntax=docker/dockerfile:1
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 SAM2_BUILD_CUDA=0 HF_HOME=/models/huggingface
RUN apt-get update && apt-get install -y git ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/facebookresearch/sam2.git /opt/sam2 && pip install --no-cache-dir --no-build-isolation -e /opt/sam2
COPY --from=ghcr.io/astral-sh/uv:0.10.3 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_SYSTEM_PYTHON=1 \
    UV_NO_DEV=1
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv export --frozen --no-dev --no-hashes -o /tmp/requirements.txt \
    && uv pip install -r /tmp/requirements.txt
COPY pyproject.toml uv.lock ./
COPY app ./app
EXPOSE 8090
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8090"]
