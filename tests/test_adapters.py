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

    def test_transport_adapter_ordering(self):
        mgr = adapters.Manager()
        mgr.register("http://git", adapters.HTTPAdapter())
        mgr.register("http://github", adapters.HTTPAdapter())
        mgr.register("http://github.com", adapters.HTTPAdapter())
        mgr.register("http://github.com/about/", adapters.HTTPAdapter())
        order = [
            "http://github.com/about/",
            "http://github.com",
            "http://github",
            "http://git",
            "https://",
            "http://",
        ]
        assert order == mgr.prefixes
        mgr.register("http://gittip", adapters.HTTPAdapter())
        mgr.register("http://gittip.com", adapters.HTTPAdapter())
        mgr.register("http://gittip.com/about/", adapters.HTTPAdapter())
        order = [
            "http://github.com/about/",
            "http://gittip.com/about/",
            "http://github.com",
            "http://gittip.com",
            "http://github",
            "http://gittip",
            "http://git",
            "https://",
            "http://",
        ]
        assert order == mgr.prefixes

    def test_find_matching_mixed_case(self):
        mixed_case_prefix = "hTtPs://eXamPle.CoM/MixEd_CAse_PREfix"
        url_matching_prefix = mixed_case_prefix + "/full_url"

        mgr = adapters.Manager()
        my_adapter = adapters.HTTPAdapter()
        mgr.register(mixed_case_prefix, my_adapter)

        assert mgr.find(url_matching_prefix) is my_adapter
