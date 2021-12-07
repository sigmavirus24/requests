import pytest

from requests import adapters


class NamedAdapter(adapters.BaseAdapter):
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        super().__init__()

    def send(self, *args, **kwargs):
        pass

    def close(self):
        self.closed = True


class TestManager:
    def test_find_no_matching_adapters(self):
        mgr = adapters.Manager()
        # Empty
        with pytest.raises(adapters._NoMatchingAdapterError):
            mgr.find("https://example.com")

        mgr.register(
            "https://example.com", NamedAdapter("https://example.com")
        )
        mgr.register("http://example.com", NamedAdapter("http://example.com"))
        with pytest.raises(adapters._NoMatchingAdapterError):
            mgr.find("https://python.org")

    def test_register_sorts_by_specificity_of_prefix(self):
        mgr = adapters.Manager()

        mgr.register("http://", NamedAdapter("http"))
        mgr.register("https://example.com", NamedAdapter("example"))
        mgr.register("https://", NamedAdapter("https"))

        assert mgr.prefixes == ["https://example.com", "https://", "http://"]

    def test_find_finds_most_specific_adapter(self):
        mgr = adapters.Manager()

        mgr.register("http://", NamedAdapter("http"))
        mgr.register("https://example.com", NamedAdapter("example"))
        mgr.register("https://", NamedAdapter("https"))
        mgr.register("https://python.org", NamedAdapter("pythondotorg"))

        assert mgr.find("http://example.com").name == "http"
        assert mgr.find("https://example.com").name == "example"
        assert mgr.find("https://github.com").name == "https"
        assert mgr.find("https://python.org").name == "pythondotorg"
        assert mgr.find("https://docs.python.org").name == "https"

    def test_remove(self):
        mgr = adapters.Manager()

        # Empty
        try:
            mgr.remove("https://")
        except Exception as e:
            pytest.fail(
                "Unexpected exception removing a non-existent adapter", e
            )

        mgr.register("https://", NamedAdapter("https"))
        assert mgr.prefixes == ["https://"]
        mgr.remove("https://")
        assert mgr.prefixes == []

    def test_close(self):
        mgr = adapters.Manager()

        # Empty
        mgr.close()

        mgr.register("https://", NamedAdapter("https"))
        assert mgr.adapters["https://"].closed is False
        mgr.close()
        assert mgr.adapters["https://"].closed is True
