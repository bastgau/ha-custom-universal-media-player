FROM mcr.microsoft.com/devcontainers/python:3.14

# uv manages the project environment (see pyproject.toml). Copied from Astral's
# official image rather than installed through a third-party devcontainer feature.
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /usr/local/bin/

# Install dependencies needed by Home Assistant or its dependencies
RUN \
    apt-get update \
    && DEBIAN_FRONTEND=noninteractive \
        apt-get install -y --no-install-recommends \
            build-essential \
            clang \
            cmake \
            ffmpeg \
            gcc \
            git \
            libavcodec-dev \
            libavdevice-dev \
            libavfilter-dev \
            libavformat-dev \
            libavutil-dev \
            libffi-dev \
            liblzma-dev \
            libpcap-dev \
            libssl-dev \
            libswresample-dev \
            libswscale-dev \
            libturbojpeg0 \
            libudev-dev \
            libxml2 \
            libxmlsec1-dev \
            libyaml-dev \
            uuid-dev \
            webp \
            xz-utils \
            zlib1g-dev \
            vim

# go2rtc (a default_config dependency) refuses to start in a container without
# its binary on PATH. Version matches RECOMMENDED_VERSION in
# homeassistant/components/go2rtc/const.py.
ARG GO2RTC_VERSION=1.9.14
ARG TARGETARCH
RUN curl -fsSL -o /usr/local/bin/go2rtc \
        "https://github.com/AlexxIT/go2rtc/releases/download/v${GO2RTC_VERSION}/go2rtc_linux_${TARGETARCH}" \
    && chmod +x /usr/local/bin/go2rtc
