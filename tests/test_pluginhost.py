# -*- coding: utf-8 -*-
"""Tests for the EasyTer Pro plugin host (pure-Python core, no Qt required)."""

import types

import pytest

from easyterpro import pluginhost


# ---------- helpers ----------

def make_module(register=None):
    """A fake plugin module: a namespace with an optional register(api) callable."""
    m = types.SimpleNamespace()
    if register is not None:
        m.register = register
    return m


def load_modules(modules, *, disabled=None, window=None):
    """Run pluginhost.load against an in-memory dict of {name: module}."""
    reg = pluginhost.Registry()
    pluginhost.load(
        window=window,
        names=list(modules.keys()),
        importer=lambda name: modules[name],
        disabled=disabled,
        registry=reg,
    )
    return reg


# ---------- Registry ----------

def test_registry_starts_empty():
    reg = pluginhost.Registry()
    assert reg.palette_actions == []
    assert reg.output_listeners == []
    assert reg.paint_hooks == []
    assert reg.loaded == []
    assert reg.failed == []


# ---------- load: registration ----------

def test_load_commits_palette_action():
    def register(api):
        api.add_palette_action("Say hi", lambda: None)

    reg = load_modules({"greeter": make_module(register)})
    assert reg.loaded == ["greeter"]
    assert len(reg.palette_actions) == 1
    label, cb = reg.palette_actions[0]
    assert label == "Say hi"
    assert callable(cb)


def test_load_commits_output_and_paint_hooks():
    def register(api):
        api.on_output(lambda text: None)
        api.add_paint_hook(lambda painter, widget: None)

    reg = load_modules({"p": make_module(register)})
    assert len(reg.output_listeners) == 1
    assert len(reg.paint_hooks) == 1


def test_load_skips_module_without_register():
    reg = load_modules({"notaplugin": make_module(register=None)})
    assert reg.loaded == []
    assert reg.palette_actions == []


# ---------- load: enable/disable ----------

def test_load_skips_disabled_plugin():
    def register(api):
        api.add_palette_action("X", lambda: None)

    mods = {"a": make_module(register), "b": make_module(register)}
    reg = load_modules(mods, disabled=["a"])
    assert reg.loaded == ["b"]
    assert len(reg.palette_actions) == 1


# ---------- load: error isolation ----------

def test_load_isolates_import_failure():
    def good_register(api):
        api.add_palette_action("ok", lambda: None)

    def importer(name):
        if name == "bad":
            raise ImportError("boom")
        return make_module(good_register)

    reg = pluginhost.Registry()
    pluginhost.load(
        names=["bad", "good"],
        importer=importer,
        registry=reg,
    )
    assert reg.loaded == ["good"]
    assert len(reg.palette_actions) == 1
    assert reg.failed and reg.failed[0][0] == "bad"


def test_load_rolls_back_on_register_failure():
    """A plugin that raises mid-register commits NONE of its registrations."""
    def register(api):
        api.add_palette_action("partial", lambda: None)
        api.on_output(lambda text: None)
        raise RuntimeError("half way")

    reg = load_modules({"flaky": make_module(register)})
    assert reg.loaded == []
    assert reg.palette_actions == []
    assert reg.output_listeners == []
    assert reg.failed and reg.failed[0][0] == "flaky"


def test_one_bad_plugin_does_not_block_others():
    def bad(api):
        raise RuntimeError("nope")

    def good(api):
        api.add_palette_action("good", lambda: None)

    reg = load_modules({"bad": make_module(bad), "good": make_module(good)})
    assert reg.loaded == ["good"]
    assert len(reg.palette_actions) == 1


# ---------- themes ----------

def test_add_theme_rejects_malformed_spec():
    reg = pluginhost.Registry()
    api = pluginhost.PluginAPI("t", reg)
    with pytest.raises(ValueError):
        api.add_theme("Bad", {"bg": "#000"})  # missing fg + ansi


def test_add_theme_installs_valid_theme(monkeypatch):
    installed = {}
    monkeypatch.setattr(pluginhost, "_install_theme",
                        lambda name, spec: installed.__setitem__(name, spec))
    spec = {"bg": "#000000", "fg": "#ffffff", "ansi": {"red": "#ff0000"}}

    def register(api):
        api.add_theme("Neon", spec)

    reg = load_modules({"themer": make_module(register)})
    assert reg.loaded == ["themer"]
    assert installed == {"Neon": spec}


def test_add_theme_not_installed_when_register_later_fails(monkeypatch):
    installed = {}
    monkeypatch.setattr(pluginhost, "_install_theme",
                        lambda name, spec: installed.__setitem__(name, spec))

    def register(api):
        api.add_theme("Neon", {"bg": "#000", "fg": "#fff", "ansi": {}})
        raise RuntimeError("boom after theme")

    reg = load_modules({"themer": make_module(register)})
    assert reg.loaded == []
    assert installed == {}   # rolled back: theme never installed


# ---------- safe_dispatch ----------

def test_safe_dispatch_calls_all():
    calls = []
    cbs = [lambda: calls.append(1), lambda: calls.append(2)]
    pluginhost.safe_dispatch(cbs)
    assert calls == [1, 2]


def test_safe_dispatch_continues_past_error():
    calls = []

    def boom():
        raise RuntimeError("x")

    cbs = [boom, lambda: calls.append("after")]
    pluginhost.safe_dispatch(cbs)
    assert calls == ["after"]


def test_safe_dispatch_auto_disables_failing_paint_hook():
    def boom(painter, widget):
        raise RuntimeError("paint fail")

    hooks = [boom]
    pluginhost.safe_dispatch(hooks, None, None, auto_disable=True)
    assert hooks == []   # the raising hook was removed


def test_safe_dispatch_no_auto_disable_keeps_callback():
    def boom():
        raise RuntimeError("x")

    cbs = [boom]
    pluginhost.safe_dispatch(cbs)   # auto_disable defaults False
    assert cbs == [boom]


# ---------- PluginAPI app helpers ----------

def test_write_to_active_routes_to_active_pane_backend():
    written = []
    backend = types.SimpleNamespace(write=written.append)
    pane = types.SimpleNamespace(backend=backend)
    container = types.SimpleNamespace(active_pane=pane)
    window = types.SimpleNamespace(_active_container=lambda: container)

    api = pluginhost.PluginAPI("p", pluginhost.Registry(), window=window)
    assert api.write_to_active("hi\r") is True
    assert written == ["hi\r"]


def test_active_terminal_none_without_window():
    api = pluginhost.PluginAPI("p", pluginhost.Registry(), window=None)
    assert api.active_terminal() is None
    assert api.write_to_active("x") is False


# ---------- integration: the real bundled plugins ----------

def test_bundled_sample_plugins_all_load():
    """Discovers and loads the actual easyterpro/plugins/ modules end to end."""
    reg = pluginhost.Registry()
    pluginhost.load(window=None, registry=reg)   # real discovery + import
    assert reg.failed == [], f"plugins failed to load: {reg.failed}"
    for name in ("sample_timestamp", "sample_theme",
                 "sample_activity", "sample_overlay"):
        assert name in reg.loaded
    # each capability landed in the registry
    assert any(label == "إدراج الطابع الزمنيّ" for label, _ in reg.palette_actions)
    assert len(reg.output_listeners) >= 1
    assert len(reg.paint_hooks) >= 1


def test_bundled_disabled_list_is_honored():
    reg = pluginhost.Registry()
    pluginhost.load(window=None, disabled=["sample_overlay"], registry=reg)
    assert "sample_overlay" in [n for n in ("sample_overlay",)]  # sanity
    assert "sample_overlay" not in reg.loaded
    assert "sample_timestamp" in reg.loaded
