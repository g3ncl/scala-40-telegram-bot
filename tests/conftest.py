"""Shared test fixtures for Scala 40."""

import pytest

from src.db.memory import (
    InMemoryGameRepository,
    InMemoryLobbyRepository,
    InMemoryUserRepository,
)


@pytest.fixture
def game_repo():
    return InMemoryGameRepository()


@pytest.fixture
def lobby_repo():
    return InMemoryLobbyRepository()


@pytest.fixture
def user_repo():
    return InMemoryUserRepository()
