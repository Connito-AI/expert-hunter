import pytest


def pytest_addoption(parser):
    parser.addoption("--network", action="store_true",
                     help="also run the checks that stream datasets from the Hub")
    parser.addoption("--proposal", action="append", default=[],
                     help="limit the network check to this proposal (repeatable)")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--network"):
        return
    skip = pytest.mark.skip(reason="needs --network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
