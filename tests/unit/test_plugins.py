from __future__ import annotations

from typing import Any, Protocol

import pytest

from qualis.plugins import load_entry_points


class _GreeterPort(Protocol):
    def greet(self, name: str) -> str: ...


class _GoodGreeter:
    def greet(self, name: str) -> str:
        return f"hello {name}"


class _BadGreeter:
    """Missing the protocol's public surface entirely."""

    def shout(self, name: str) -> str:
        return name.upper()


class _FakeEntryPoint:
    def __init__(self, name: str, obj: Any) -> None:
        self.name = name
        self._obj = obj

    def load(self) -> Any:
        return self._obj


def _patch_entry_points(monkeypatch: pytest.MonkeyPatch, group: str, eps: list[Any]) -> None:
    import qualis.plugins as plugins_mod

    def fake_entry_points(*, group: str = "") -> list[Any]:
        return eps

    monkeypatch.setattr(plugins_mod.importlib.metadata, "entry_points", fake_entry_points)


class TestLoadEntryPoints:
    def test_loads_named_factories_for_group(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_entry_points(
            monkeypatch, "demo.group", [_FakeEntryPoint("good", _GoodGreeter)]
        )
        loaded = load_entry_points("demo.group", _GreeterPort)
        assert set(loaded) == {"good"}
        assert loaded["good"] is _GoodGreeter

    def test_rejects_objects_missing_protocol_surface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_entry_points(
            monkeypatch,
            "demo.group",
            [_FakeEntryPoint("good", _GoodGreeter), _FakeEntryPoint("bad", _BadGreeter)],
        )
        loaded = load_entry_points("demo.group", _GreeterPort)
        assert "good" in loaded
        assert "bad" not in loaded  # skipped with a warning, not fatal

    def test_group_agnostic_empty_group_is_empty_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_entry_points(monkeypatch, "another.group", [])
        assert load_entry_points("another.group", _GreeterPort) == {}

    def test_broken_entry_point_is_skipped_not_fatal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Exploding:
            name = "boom"

            def load(self) -> Any:
                raise ImportError("dependency missing")

        _patch_entry_points(
            monkeypatch,
            "demo.group",
            [_Exploding(), _FakeEntryPoint("good", _GoodGreeter)],
        )
        loaded = load_entry_points("demo.group", _GreeterPort)
        assert set(loaded) == {"good"}

    def test_factory_callable_accepted_without_surface_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def factory(settings: object) -> _GoodGreeter:
            return _GoodGreeter()

        _patch_entry_points(monkeypatch, "demo.group", [_FakeEntryPoint("fac", factory)])
        loaded = load_entry_points("demo.group", _GreeterPort)
        assert loaded["fac"] is factory

    def test_non_callable_object_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_entry_points(
            monkeypatch, "demo.group", [_FakeEntryPoint("junk", object())]
        )
        assert load_entry_points("demo.group", _GreeterPort) == {}
