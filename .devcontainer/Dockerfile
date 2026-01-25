FROM debian:bookworm-slim

# Avoid warnings by switching to noninteractive
ENV DEBIAN_FRONTEND=noninteractive

# Set up user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# Install base dependencies
RUN apt-get update && apt-get install -y \
    # Essential build tools
    build-essential \
    gcc \
    g++ \
    make \
    # Python build dependencies
    libbz2-dev \
    libffi-dev \
    liblzma-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    zlib1g-dev \
    # Database clients
    postgresql-client \
    redis-tools \
    # Version control and tools
    git \
    curl \
    wget \
    vim \
    nano \
    ca-certificates \
    gnupg \
    # Utilities
    sudo \
    less \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python 3.13 from source
RUN cd /tmp \
    && wget https://www.python.org/ftp/python/3.13.1/Python-3.13.1.tgz \
    && tar -xzf Python-3.13.1.tgz \
    && cd Python-3.13.1 \
    && ./configure --enable-optimizations --with-lto \
    && make -j$(nproc) \
    && make altinstall \
    && cd / \
    && rm -rf /tmp/Python-3.13.1* \
    && ln -s /usr/local/bin/python3.13 /usr/local/bin/python \
    && ln -s /usr/local/bin/python3.13 /usr/local/bin/python3 \
    && ln -s /usr/local/bin/pip3.13 /usr/local/bin/pip

# Install uv (fast Python package manager)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Create non-root user
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Install uv for the user
USER $USERNAME
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"

# Set working directory
WORKDIR /workspace

# Switch back to dialog for any ad-hoc use
ENV DEBIAN_FRONTEND=dialog

# Keep container running
CMD ["sleep", "infinity"]