# syntax=docker/dockerfile:1.4
FROM python:3.11 AS builder

# Set build arguments
ARG PYTHON_VERSION=3.11
ARG NUMPY_VERSION=1.24.2

# Set up environment
ENV PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  PIP_NO_CACHE_DIR=1 \
  PIP_DISABLE_PIP_VERSION_CHECK=1 \
  DEBIAN_FRONTEND=noninteractive \
  PYTHONPATH="${PYTHONPATH}:/build"

WORKDIR /build

# Install system dependencies and ta-lib
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  wget \
  curl \
  git \
  ca-certificates \
  cmake \
  automake \
  libtool \
  && wget https://netcologne.dl.sourceforge.net/project/ta-lib/ta-lib/0.4.0/ta-lib-0.4.0-src.tar.gz \
  && tar -xzf ta-lib-0.4.0-src.tar.gz \
  && cd ta-lib/ \
  && echo "Updating config.guess and config.sub for ARM64 support" \
  && wget -q -O config.guess 'https://git.savannah.gnu.org/gitweb/?p=config.git;a=blob_plain;f=config.guess;hb=HEAD' \
  && wget -q -O config.sub 'https://git.savannah.gnu.org/gitweb/?p=config.git;a=blob_plain;f=config.sub;hb=HEAD' \
  && chmod +x config.guess config.sub \
  && ./configure --prefix=/usr \
  && make \
  && make install \
  && cd .. \
  && rm -rf ta-lib ta-lib-0.4.0-src.tar.gz \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Use pip for package installation
RUN pip install --upgrade pip setuptools wheel

# Prepare virtual environment
RUN python -m venv /venv \
  && . /venv/bin/activate \
  && pip install --upgrade pip setuptools wheel

# Copy all application code
COPY . /build/

# Install core dependencies with pip
RUN . /venv/bin/activate \
  && pip install numpy==1.23.5 \
  && pip install pandas==1.5.3 \
  && pip install TA-Lib==0.4.32 \
  && pip install --ignore-installed llvmlite \
  && pip install pybind11 \
  && echo "Installing alternative for pandas_ta..." \
  && pip install git+https://github.com/twopirllc/pandas-ta.git@development \
  && pip install -r requirements.txt \
  && pip install st-pages \
  && pip install --no-deps universal-portfolios \
  && cd vectorbt && pip install -e . \
  && echo "Verifying installations..." \
  && python -c "import numpy; print(f'numpy version: {numpy.__version__}')" \
  && python -c "import pandas; print(f'pandas version: {pandas.__version__}')" \
  && python -c "import pandas_ta; print('pandas_ta imported successfully')"

# Install jupyter and kernel
RUN . /venv/bin/activate \
  && pip install jupyter ipykernel \
  && python -m ipykernel install --user --name=python3 --display-name "Python 3"

# Start fresh with a clean image
FROM python:3.11

# Set metadata
LABEL maintainer="Your Name <your.email@example.com>"
LABEL description="AlgoPy Trading Framework"
LABEL version="1.0"

WORKDIR /app

# Copy virtual environment and files from builder
COPY --from=builder /venv /venv
COPY --from=builder /build /app
COPY --from=builder /usr/lib/libta_lib* /usr/lib/
COPY --from=builder /usr/include/ta-lib /usr/include/ta-lib

# Set environment variables
ENV PATH="/venv/bin:$PATH" \
  PYTHONUNBUFFERED=1 \
  PYTHONDONTWRITEBYTECODE=1 \
  STREAMLIT_SERVER_PORT=8501 \
  STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
  XDG_CACHE_HOME=/home/algopy/.cache \
  PYTHONPATH="${PYTHONPATH}:/app"

# Install only runtime dependencies and prepare user
RUN apt-get update && apt-get install -y --no-install-recommends \
  curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* \
  && useradd -m -u 1000 algopy \
  && mkdir -p /home/algopy/.cache \
  && chown -R algopy:algopy /app /home/algopy

# Change to non-root user
USER algopy

# Expose port and add healthcheck
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8501/ || exit 1

# Run streamlit
CMD ["streamlit", "run", "Dashboard/main_dash.py"]