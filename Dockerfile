# Dogear in a container, for libraries, schools, and volunteer groups: the web page for
# making books (`dogear serve`), with the default voice already inside so the first book
# needs no download. Build and run it as docker/README.md describes.

# uv, pinned, only to install Dogear's locked dependencies.
FROM ghcr.io/astral-sh/uv:0.13.1@sha256:4a1f3666816dafadd20ceb71eac9a7d56d7ef30279f7d64048519ab901ada336 AS uv

FROM python:3.13-slim-trixie@sha256:2d44738ebf4ce5f63b9d9ea871e9c7cfdc0426f7b0c97cac915fd88ded1d86bb

# The programs Dogear runs: ffmpeg for audio, eSpeak NG for words the voice's dictionary
# lacks, Tesseract for scanned PDFs. Calibre (Kindle books) is left out: it would more than
# double the image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg espeak-ng tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 dogear

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/dogear/venv
WORKDIR /opt/dogear/src

# Dependencies first, so changing Dogear's own code doesn't reinstall them.
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    uv sync --frozen --no-dev --no-editable

ENV PATH=/opt/dogear/venv/bin:$PATH \
    DOGEAR_CONFIG=/etc/dogear/config.toml
COPY docker/config.toml /etc/dogear/config.toml

# The default voice, downloaded and checked against its pinned SHA-256 now. Other voices
# download into the same folder on first use, so it belongs to the user Dogear runs as.
RUN install -d -o dogear -g dogear /opt/dogear/models /data
USER dogear
RUN dogear download

# Uploaded books, finished audiobooks, and the speech cache live here. Keep it on a volume
# so they outlast the container.
VOLUME /data
WORKDIR /data
EXPOSE 8765
ENTRYPOINT ["dogear"]
CMD ["serve", "--lan", "--no-browser"]
