# -*- coding: utf-8 -*-
"""Tests for the tab-title-from-cwd plugin's pure title parser (no Qt)."""

from easyterpro.plugins import tab_title_cwd as plug


def test_extract_osc0_title_bel_terminated():
    assert plug.extract_title("\x1b]0;Windows\x07") == "Windows"


def test_extract_osc2_title_st_terminated():
    assert plug.extract_title("\x1b]2;Users\x1b\\") == "Users"


def test_extract_title_embedded_in_other_output():
    chunk = "some text\x1b]0;Admin\x07more\r\n"
    assert plug.extract_title(chunk) == "Admin"


def test_extract_last_title_when_multiple():
    chunk = "\x1b]0;First\x07junk\x1b]0;Second\x07"
    assert plug.extract_title(chunk) == "Second"


def test_extract_title_none_when_absent():
    assert plug.extract_title("no title here\r\n") is None


def test_extract_title_ignores_other_osc():
    # OSC 8 hyperlink must NOT be mistaken for a title
    assert plug.extract_title("\x1b]8;;file:C:/Users\x1b\\") is None


def test_extract_title_empty_string_is_none():
    # an explicit empty title should be treated as "no title" (don't blank the tab)
    assert plug.extract_title("\x1b]0;\x07") is None


# ---------- split routing (fakes, no Qt) ----------

class FakeSignal:
    def __init__(self):
        self._cbs = []

    def connect(self, cb):
        self._cbs.append(cb)

    def emit(self, *a):
        for cb in list(self._cbs):
            cb(*a)


class FakeBackend:
    def __init__(self):
        self.output_text = FakeSignal()


class FakePane:
    def __init__(self):
        self.backend = FakeBackend()
        self._parent = None

    def parentWidget(self):
        return self._parent


class FakeContainer:
    """Stands in for a SplitContainer: has _all_panes + active_pane."""
    def __init__(self, panes):
        self._panes = list(panes)
        self.active_pane = self._panes[0] if self._panes else None
        for p in self._panes:
            p._parent = self

    def _all_panes(self):
        return list(self._panes)

    def add_pane(self, pane):     # simulate a split adding a pane
        pane._parent = self
        self._panes.append(pane)

    def parentWidget(self):
        return None


class FakeTabs:
    def __init__(self, containers):
        self._containers = list(containers)
        self.titles = {}
        self.currentChanged = FakeSignal()

    def count(self):
        return len(self._containers)

    def widget(self, i):
        return self._containers[i]

    def indexOf(self, w):
        return self._containers.index(w) if w in self._containers else -1

    def setTabText(self, i, t):
        self.titles[i] = t

    def currentWidget(self):
        return self._containers[0] if self._containers else None


class FakeWindow:
    def __init__(self, tabs):
        self.tabs = tabs


def _make(panes_per_tab):
    containers = [FakeContainer(ps) for ps in panes_per_tab]
    tabs = FakeTabs(containers)
    win = FakeWindow(tabs)
    tracker = plug._TabTitleTracker(win)
    tracker.attach_all()
    return win, tabs, containers, tracker


def test_output_from_active_pane_sets_tab_title():
    p0 = FakePane()
    win, tabs, (c,), tracker = _make([[p0]])
    p0.backend.output_text.emit("\x1b]0;Windows\x07")
    assert tabs.titles.get(0) == "Windows"


def test_output_from_inactive_pane_is_ignored():
    p0, p1 = FakePane(), FakePane()
    win, tabs, (c,), tracker = _make([[p0, p1]])   # active_pane = p0
    p1.backend.output_text.emit("\x1b]0;Downloads\x07")
    assert 0 not in tabs.titles          # inactive pane must not retitle the tab


def test_focus_switch_updates_title_to_focused_pane_dir():
    p0, p1 = FakePane(), FakePane()
    win, tabs, (c,), tracker = _make([[p0, p1]])
    p0.backend.output_text.emit("\x1b]0;Alpha\x07")   # active p0 -> title Alpha
    p1.backend.output_text.emit("\x1b]0;Beta\x07")    # inactive, just remembered
    assert tabs.titles.get(0) == "Alpha"
    # user focuses p1: container marks it active, app fires focusChanged
    c.active_pane = p1
    tracker.on_focus_changed(p0, p1)
    assert tabs.titles.get(0) == "Beta"


def test_new_split_pane_is_attached_on_focus():
    p0 = FakePane()
    win, tabs, (c,), tracker = _make([[p0]])
    # simulate a split: a new pane is added and focused
    p1 = FakePane()
    c.add_pane(p1)
    c.active_pane = p1
    tracker.on_focus_changed(p0, p1)      # focusChanged wires the new pane up
    p1.backend.output_text.emit("\x1b]0;NewDir\x07")
    assert tabs.titles.get(0) == "NewDir"


# ---------- manual rename + pinning ----------

def test_manual_rename_sets_title_and_pins():
    p0 = FakePane()
    win, tabs, (c,), tracker = _make([[p0]])
    tracker._apply_rename(c, "My Work")
    assert tabs.titles.get(0) == "My Work"
    # a pinned tab must NOT be overwritten by auto-cwd
    p0.backend.output_text.emit("\x1b]0;Windows\x07")
    assert tabs.titles.get(0) == "My Work"


def test_rename_empty_resumes_auto_follow():
    p0 = FakePane()
    win, tabs, (c,), tracker = _make([[p0]])
    tracker._apply_rename(c, "Pinned")
    tracker._apply_rename(c, "   ")           # blank -> unpin, resume auto
    p0.backend.output_text.emit("\x1b]0;Windows\x07")
    assert tabs.titles.get(0) == "Windows"


def test_pinned_tab_ignores_focus_switch():
    p0, p1 = FakePane(), FakePane()
    win, tabs, (c,), tracker = _make([[p0, p1]])
    p1.backend.output_text.emit("\x1b]0;Beta\x07")   # remembered on p1
    tracker._apply_rename(c, "Fixed")
    c.active_pane = p1
    tracker.on_focus_changed(p0, p1)
    assert tabs.titles.get(0) == "Fixed"             # pinned, not switched to Beta
