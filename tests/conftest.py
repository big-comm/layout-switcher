# SPDX-License-Identifier: MIT
"""Shared pytest fixtures for layout-switcher tests."""

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory and return its Path."""
    return tmp_path
