# Dev container image. Root-only setup lives here because the container runs
# with no-new-privileges, which disables sudo at runtime.
#
# Everything is installed here (no dev container features, no postCreateCommand)
# so Docker caches each step. Steps are ordered from least to most frequently
# changed: editing a later step only rebuilds the steps after it.
#
# Toolchains only. Project dependencies (PyTorch, fontTools, npm packages, Gradle
# plugins, Android SDK platforms) are pinned by the project's own lockfiles and
# installed into the cache volumes declared in devcontainer.json.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

# System packages. Ubuntu 24.04's python3 is 3.12, so no Python build is needed.
# JDK 21 runs Gradle / the Android Gradle Plugin (Thumb-Key targets JVM 17 bytecode,
# which JDK 21 compiles fine). libgl1/libglib2.0-0: runtime libs for image tooling.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        zstd unzip python3 python3-venv python3-pip \
        openjdk-21-jdk-headless \
        libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Node.js 24 (LTS) from NodeSource, for the web/ TypeScript library and demo.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI from GitHub's apt repo. Authenticate with `gh auth login` or a
# GH_TOKEN in the --env-file secrets.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Android SDK command-line tools, checksum-verified. Only sdkmanager, platform-tools
# (adb) and the licenses are installed here; the Android Gradle Plugin downloads the
# exact platform/build-tools the Gradle build asks for into this vscode-owned SDK.
ARG ANDROID_CMDLINE_TOOLS_BUILD=16111833
ARG ANDROID_CMDLINE_TOOLS_SHA1=e025545c62a8e64c7559119566a569fb1dec5f60
ENV ANDROID_HOME=/opt/android-sdk
ENV ANDROID_SDK_ROOT=/opt/android-sdk
ENV PATH=$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH
RUN curl -fsSL -o /tmp/cmdline-tools.zip \
        "https://dl.google.com/android/repository/commandlinetools-linux-${ANDROID_CMDLINE_TOOLS_BUILD}_latest.zip" \
    && echo "${ANDROID_CMDLINE_TOOLS_SHA1}  /tmp/cmdline-tools.zip" | sha1sum -c - \
    && mkdir -p $ANDROID_HOME/cmdline-tools \
    && unzip -q /tmp/cmdline-tools.zip -d /tmp/cmdline-tools \
    && mv /tmp/cmdline-tools/cmdline-tools $ANDROID_HOME/cmdline-tools/latest \
    && rm -rf /tmp/cmdline-tools /tmp/cmdline-tools.zip \
    && yes | sdkmanager --licenses > /dev/null \
    && sdkmanager --install "platform-tools" > /dev/null \
    && chown -R vscode:vscode $ANDROID_HOME

# uv manages the Python environment from training/pyproject.toml + uv.lock, so
# `uv sync` reproduces the exact training environment. Pinned for cache stability.
RUN curl -LsSf https://astral.sh/uv/0.12.19/install.sh \
        | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

# Pre-create directories that named volumes are mounted over, so the volumes
# inherit vscode ownership on first use.
RUN mkdir -p /home/vscode/.claude /home/vscode/.cache /home/vscode/.gradle /data \
    && chown -R vscode:vscode /home/vscode/.claude /home/vscode/.cache \
        /home/vscode/.gradle /data

# Claude Code managed settings, applied only inside this container: sessions
# start in auto mode here while the host keeps its own default (Manual).
COPY managed-settings.json /etc/claude-code/managed-settings.json
