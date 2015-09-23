import logging
import os
import sys

import py
import pytest


def pytest_addoption(parser):
    parser.addoption('--log-level', choices=['d', 'i', 'w', 'e'], default='w')
    parser.addoption('--log-file')


@pytest.fixture(scope='session')
def log_level(pytestconfig):
    return {
        'd': logging.DEBUG,
        'i': logging.INFO,
        'w': logging.WARN,
        'e': logging.ERROR,
    }[pytestconfig.getoption('log_level')]


@pytest.fixture(scope='session')
def log_file(pytestconfig):
    return pytestconfig.getoption('log_file')


@pytest.fixture(scope='session', autouse=True)
def config_logging(pytestconfig, log_level, log_file):
    logging.basicConfig(
        format='%(levelname)s : %(name)s : %(message)s',
        level=log_level,
        filename=log_file,  # trumps stream=
        stream=sys.stderr,
    )


@pytest.fixture(scope='session')
def fixtures():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
    return py.path.local(path)
