#!/bin/bash

# =====================================================================
# Keong-MAS Launcher Script for Unix-like Systems
# Author: Mudrikul Hikam
# Last Updated: May 24, 2025
# 
# This script performs the following tasks:
# 1. If Python folder exists, directly runs main.py
# 2. If Python folder doesn't exist:
#    - Downloads Python 3.12.10 standalone distribution for the OS
#    - Sets up pip in the distribution
#    - Installs required packages from requirements.txt
#    - Runs main.py
# =====================================================================

# =====================================================================
# The MIT License (MIT)
#
# Copyright (c) 2025 Mudrikul Hikam, Desainia Studio
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
# =====================================================================

# Set base directory to the location of this script
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# =====================================================================
# Determine OS and configure environment variables
# =====================================================================
PYTHON_VERSION="3.12.10"
RELEASE_TAG="20250409"
OS="$(uname -s)"

# Define the Python version to be consistent with Windows script
PYTHON_VERSION="3.12.10"
RELEASE_TAG="20250409"

case "${OS}" in
    Linux*)
        OS_DIR="Linux"
        INSTALL_DIR="Python/${OS_DIR}"
        PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/cpython-${PYTHON_VERSION}+${RELEASE_TAG}-x86_64-unknown-linux-gnu-install_only.tar.gz"
        # Set Linux-specific vars
        export XDG_RUNTIME_DIR="/run/user/$(id -u)"
        export QT_QPA_PLATFORM=xcb
        # System libraries path
        export LD_LIBRARY_PATH="/usr/lib/x86_64-linux-gnu:/usr/lib:${LD_LIBRARY_PATH}"
        ;;
    Darwin*)
        OS_DIR="MacOS"
        INSTALL_DIR="Python/${OS_DIR}"
        PYTHON_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${RELEASE_TAG}/cpython-${PYTHON_VERSION}+${RELEASE_TAG}-x86_64-apple-darwin-install_only.tar.gz"
        # Set macOS-specific environment variables
        export QT_MAC_WANTS_LAYER=1
        # Ensure macOS frameworks path is included
        export DYLD_FRAMEWORK_PATH="${BASE_DIR}/${INSTALL_DIR}/lib:${DYLD_FRAMEWORK_PATH}"
        export DYLD_LIBRARY_PATH="${BASE_DIR}/${INSTALL_DIR}/lib:${DYLD_LIBRARY_PATH}"
        ;;
    *)
        echo "Unsupported operating system: ${OS}"
        exit 1
        ;;
esac

PYTHON_PATH="${BASE_DIR}/${INSTALL_DIR}/bin/python3.12"
REQUIREMENTS_FILE="${BASE_DIR}/requirements.txt"

# =====================================================================
# Check if Python is already installed
# If it exists, we can update the app and install requirements
# If not, we need to set up the environment first
# =====================================================================
if [ -f "${PYTHON_PATH}" ]; then
    echo "Python installation found. Checking requirements..."
    
    # Check for requirements.txt and install if it exists
    if [ -f "${REQUIREMENTS_FILE}" ]; then
        echo "Installing requirements from requirements.txt..."
        "${PYTHON_PATH}" -m pip install -r "${REQUIREMENTS_FILE}" --no-warn-script-location
    else
        echo "Warning: requirements.txt not found. Skipping package installation."
    fi
else
    echo "Python installation not found. Setting up environment..."
    
    # =====================================================================
    # Define variables for setup process
    # =====================================================================
    PYTHON_ARCHIVE="/tmp/python-${PYTHON_VERSION}.tar.gz"
    
    # =====================================================================
    # Create Python directory
    # =====================================================================
    echo "Creating Python directory..."
    mkdir -p "${BASE_DIR}/${INSTALL_DIR}"
    
    # =====================================================================
    # Download and extract Python standalone distribution
    # =====================================================================
    echo "Downloading Python standalone distribution..."
    if command -v curl &> /dev/null; then
        curl -L "${PYTHON_URL}" -o "${PYTHON_ARCHIVE}" || { echo "curl download failed"; exit 1; }
    elif command -v wget &> /dev/null; then
        wget "${PYTHON_URL}" -O "${PYTHON_ARCHIVE}" || { echo "wget download failed"; exit 1; }
    else
        echo "Error: Neither curl nor wget is available. Cannot download Python."
        exit 1
    fi
    
    # Verify the downloaded file exists and has content
    if [ ! -s "${PYTHON_ARCHIVE}" ]; then
        echo "Downloaded Python archive is empty or does not exist."
        exit 1
    fi
    
    echo "Extracting Python..."
    # Create a temporary directory for safer extraction
    TEMP_EXTRACT_DIR="/tmp/python-extract-$$"
    mkdir -p "${TEMP_EXTRACT_DIR}"
    
    # Extract with error handling and progress feedback
    echo "Extracting to temporary location first..."
    tar -xzf "${PYTHON_ARCHIVE}" -C "${TEMP_EXTRACT_DIR}" || {
        echo "Extraction failed. The archive may be corrupted or incompatible."
        echo "Technical details:"
        file "${PYTHON_ARCHIVE}"
        du -sh "${PYTHON_ARCHIVE}"
        rm -rf "${TEMP_EXTRACT_DIR}"
        exit 1
    }
    
    # Move files to final location
    echo "Moving files to installation directory..."
    # Check if the extracted directory has a 'python' subdirectory that should be flattened
    if [ -d "${TEMP_EXTRACT_DIR}/python" ]; then
        echo "Extracting from nested python directory structure..."
        cp -r "${TEMP_EXTRACT_DIR}/python"/* "${BASE_DIR}/${INSTALL_DIR}/" || {
            echo "Failed to copy extracted files to installation directory."
            exit 1
        }
    else
        # Copy directly if no nested structure
        cp -r "${TEMP_EXTRACT_DIR}"/* "${BASE_DIR}/${INSTALL_DIR}/" || {
            echo "Failed to copy extracted files to installation directory."
            exit 1
        }
    fi
    
    # Clean up temporary files
    rm -rf "${TEMP_EXTRACT_DIR}"
    rm -f "${PYTHON_ARCHIVE}"
    
    # Verify Python executable exists after extraction
    if [ ! -f "${PYTHON_PATH}" ]; then
        echo "Python executable not found after extraction. Installation failed."
        echo "Expected path: ${PYTHON_PATH}"
        echo "Files in installation directory:"
        ls -la "${BASE_DIR}/${INSTALL_DIR}"
        exit 1
    fi
    
    echo "Python extraction completed successfully."
    
    # =====================================================================
    # Set up pip in the Python distribution
    # 1. Check if requirements.txt exists, create if not
    # 2. Download and run get-pip.py to install pip
    # 3. Install required packages from requirements.txt
    # =====================================================================
    echo "Setting up pip..."
    
    # Create requirements.txt if it doesn't exist
    if [ ! -f "${REQUIREMENTS_FILE}" ]; then
        echo "Creating empty requirements.txt file..."
        touch "${REQUIREMENTS_FILE}"
    fi
    
    # Download get-pip.py and install pip
    echo "Installing pip..."
    PIP_TEMP="/tmp/get-pip.py"
    if command -v curl &> /dev/null; then
        curl -L "https://bootstrap.pypa.io/get-pip.py" -o "${PIP_TEMP}" || {
            echo "Failed to download get-pip.py"
            exit 1
        }
    elif command -v wget &> /dev/null; then
        wget "https://bootstrap.pypa.io/get-pip.py" -O "${PIP_TEMP}" || {
            echo "Failed to download get-pip.py"
            exit 1
        }
    else
        echo "Error: Neither curl nor wget is available. Cannot download pip."
        exit 1
    fi
    
    # Install pip using the newly installed Python
    "${PYTHON_PATH}" "${PIP_TEMP}" --no-warn-script-location
    
    # Remove temporary get-pip.py file
    rm -f "${PIP_TEMP}"
    
    # Verify pip is installed correctly
    if ! "${PYTHON_PATH}" -m pip --version; then
        echo "Failed to install pip. Installation cannot continue."
        exit 1
    fi
    
    # Install required packages without mentioning pip upgrade separately
    if [ -f "${REQUIREMENTS_FILE}" ]; then
        echo "Installing required packages from requirements.txt..."
        # This will automatically use the latest pip without a separate message
        "${PYTHON_PATH}" -m pip install --upgrade pip --quiet --no-warn-script-location
        
        # Special handling for macOS PySide6 installation
        if [ "${OS}" = "Darwin" ]; then
            echo "Installing PySide6 with additional macOS dependencies..."
            # First make sure dependencies are installed
            "${PYTHON_PATH}" -m pip install wheel setuptools --upgrade --no-warn-script-location
            
            # Try installing PySide6 directly first
            if ! "${PYTHON_PATH}" -m pip install PySide6 --no-warn-script-location; then
                echo "Direct PySide6 installation failed, trying with extra options..."
                # Try with alternative install approach for macOS
                "${PYTHON_PATH}" -m pip install PySide6 --no-binary PySide6 --no-warn-script-location || {
                    echo "PySide6 installation failed. Please install macOS command line tools with 'xcode-select --install'"
                    echo "Then run this script again."
                    exit 1
                }
            fi
            
            # Continue with the rest of requirements
            grep -v "PySide6" "${REQUIREMENTS_FILE}" > /tmp/other_requirements.txt
            if [ -s /tmp/other_requirements.txt ]; then
                "${PYTHON_PATH}" -m pip install -r /tmp/other_requirements.txt --no-warn-script-location
            fi
            rm /tmp/other_requirements.txt
        else
            # Normal installation for non-macOS systems
            "${PYTHON_PATH}" -m pip install -r "${REQUIREMENTS_FILE}" --no-warn-script-location
        fi
    else
        echo "Warning: requirements.txt not found. Skipping package installation."
    fi
    
    echo "Setup complete!"
fi

# =====================================================================
# Launch the application
# =====================================================================
echo ""
echo "==================================================="
echo "        Keong-MAS Application Launcher             "
echo "==================================================="
echo "Setup complete. Running main.py..."
echo ""
exec "${PYTHON_PATH}" "${BASE_DIR}/main.py"
