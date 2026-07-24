# -*- coding: utf-8 -*-
"""مضيف الإضافات (Plugin host) — يحمّل إضافات `easyterpro/plugins/` المرفقة ويعزلها.

كلّ إضافة وحدة تعرّف دالّة ‎`register(api)`‎ تستدعي طرائق الواجهة (PluginAPI):
add_palette_action / add_theme / on_output / add_paint_hook.

مبادئ التصميم:
- **العزل التامّ**: لا إضافة تُسقط التطبيق. فشل الاستيراد أو التسجيل أو أيّ خطّاف
  يُلتقط ويُسجَّل في ‎`~/.easyterpro/plugins.log`‎ ويُتابَع.
- **السحب من السجلّ**: الودجات تقرأ ‎`registry`‎ وقت النداء (لا ربط لحظة الإنشاء)،
  فترتيب التحميل مرن والتعطيل حيّ.
- **خالٍ من Qt عند الاستيراد**: استيراد render/config كسول داخل الطرائق فقط، حتّى
  يبقى هذا الملفّ قابلًا للاختبار دون واجهة رسوميّة.
"""

import os
import pkgutil
import traceback

_PLUGINS_PACKAGE = "easyterpro.plugins"
_LOG_PATH = os.path.join(os.path.expanduser("~"), ".easyterpro", "plugins.log")


# ---------------------------------------------------------------- logging ----

def _log(message):
    """يكتب سطرًا إلى سجلّ الإضافات. دفاعيّ تمامًا (لا يرمي أبدًا، ولا يطبع)."""
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(message.rstrip() + "\n")
    except Exception:
        pass


# --------------------------------------------------------------- registry ----

class Registry:
    """يجمع كلّ تسجيلات الإضافات. الودجات تقرأ منه وقت النداء."""

    def __init__(self):
        self.palette_actions = []   # [(label, callback)]
        self.output_listeners = []  # [callback(text)]
        self.paint_hooks = []       # [callback(painter, widget)]
        self.loaded = []            # [name] نجحت
        self.failed = []            # [(name, exception)]

    def clear(self):
        self.palette_actions.clear()
        self.output_listeners.clear()
        self.paint_hooks.clear()
        self.loaded.clear()
        self.failed.clear()


# النسخة المفردة المشتركة التي تقرأها الودجات
registry = Registry()


# ------------------------------------------------------------ theme sink -----

def _install_theme(name, spec):
    """يركّب ثيمًا في ‎render.THEMES‎ (استيراد كسول لتفادي Qt عند الاستيراد).

    مُفرَد ليتيح للاختبارات ترقيعه (monkeypatch) دون تحميل render/Qt."""
    from . import render
    render.THEMES[name] = spec


def _validate_theme(spec):
    """يتحقّق أنّ الثيم يحمل bg/fg نصّيّين وقاموس ansi. يرمي ValueError إن فسد."""
    if (not isinstance(spec, dict)
            or not isinstance(spec.get("bg"), str)
            or not isinstance(spec.get("fg"), str)
            or not isinstance(spec.get("ansi"), dict)):
        raise ValueError("theme spec requires str 'bg', str 'fg', and dict 'ansi'")


# --------------------------------------------------------------- the API -----

class PluginAPI:
    """الواجهة الممرَّرة إلى ‎register(api)‎. تجمع التسجيلات في مخزن مؤقّت لكلّ إضافة
    ولا تُثبَّت في ‎registry‎ إلّا إذا عادت ‎register()‎ بلا خطأ (تراجع نظيف)."""

    def __init__(self, name, reg, window=None):
        self.name = name
        self.window = window
        self._registry = reg
        # مخازن مؤقّتة (تُثبَّت في _commit فقط عند نجاح register)
        self._palette = []
        self._output = []
        self._paint = []
        self._themes = []

    # ---- تسجيل القدرات ----
    def add_palette_action(self, label, callback):
        """يضيف إجراءً إلى لوحة الأوامر (Ctrl+Shift+P)."""
        self._palette.append((label, callback))

    def on_output(self, callback):
        """يسجّل مستمعًا ‎callback(text)‎ يُستدعى لكلّ دفقة خرج من الطرفيّة."""
        self._output.append(callback)

    def add_paint_hook(self, callback):
        """يسجّل خطّاف رسم ‎callback(painter, widget)‎ يُستدعى آخر كلّ إطار رسم."""
        self._paint.append(callback)

    def add_theme(self, name, spec):
        """يضيف ثيمًا ‎{bg, fg, ansi{...}}‎. يرمي ValueError إن كان المواصفة فاسدة."""
        _validate_theme(spec)
        self._themes.append((name, spec))

    # ---- إعدادات الإضافة ----
    def setting(self, key, default=None):
        """يقرأ إعداد الإضافة من ‎config plugins.settings.<name>.<key>‎."""
        from .config import config
        return config().get("plugins", "settings", self.name, key, default=default)

    # ---- عمليّات على التطبيق ----
    def active_terminal(self):
        """يرجع ودجة الطرفيّة النشطة (TerminalWidget) أو None."""
        w = self.window
        if w is None or not hasattr(w, "_active_container"):
            return None
        try:
            c = w._active_container()
        except Exception:
            return None
        if c is None:
            return None
        pane = getattr(c, "active_pane", None)
        if pane is None and hasattr(c, "_first_pane"):
            try:
                pane = c._first_pane()
            except Exception:
                pane = None
        return pane

    def write_to_active(self, text):
        """يكتب نصًّا إلى صدفة اللوح النشط. يرجع True إن وُجد لوحٌ فاعل."""
        pane = self.active_terminal()
        if pane is not None and hasattr(pane, "backend"):
            try:
                pane.backend.write(text)
            except Exception:
                pass
            return True
        return False

    # ---- تثبيت داخليّ ----
    def _commit(self):
        """يثبّت المخازن المؤقّتة في السجلّ المشترك ويركّب الثيمات."""
        for name, spec in self._themes:
            _install_theme(name, spec)
        self._registry.palette_actions.extend(self._palette)
        self._registry.output_listeners.extend(self._output)
        self._registry.paint_hooks.extend(self._paint)


# --------------------------------------------------------------- dispatch ----

def safe_dispatch(callbacks, *args, auto_disable=False):
    """ينادي كلّ ردّ نداء بأمان. خطأٌ في أحدها لا يمنع البقيّة.

    إن ‎auto_disable‎ (لخطاطيف الرسم) أُزيل ردّ النداء الفاشل من القائمة لحماية
    معدّل الإطارات من فشلٍ متكرّر. يعمل على نسخةٍ أثناء التكرار."""
    for cb in list(callbacks):
        try:
            cb(*args)
        except Exception:
            _log("dispatch error:\n" + traceback.format_exc())
            if auto_disable:
                try:
                    callbacks.remove(cb)
                except ValueError:
                    pass


# ------------------------------------------------------------------ load -----

def _default_importer(name):
    import importlib
    return importlib.import_module(f"{_PLUGINS_PACKAGE}.{name}")


def _discover():
    """يعدّد أسماء وحدات ‎easyterpro/plugins/‎ (يتجاهل ما يبدأ بشرطة سفليّة)."""
    try:
        import importlib
        pkg = importlib.import_module(_PLUGINS_PACKAGE)
    except Exception:
        _log("discover error:\n" + traceback.format_exc())
        return []
    names = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.name.startswith("_"):
            names.append(info.name)
    return names


def load(window=None, *, names=None, importer=None, disabled=None, registry=registry):
    """يحمّل الإضافات ويسجّلها في ‎registry‎ بعزلٍ تامّ. يرجع السجلّ.

    - ‎names‎: أسماء الوحدات (افتراضيًّا يُكتشف من الحزمة).
    - ‎importer‎: ‎name -> module‎ (افتراضيًّا استيراد فعليّ؛ للحقن في الاختبار).
    - ‎disabled‎: أسماء تُتخطّى (من ‎config plugins.disabled‎).
    """
    if names is None:
        names = _discover()
    if importer is None:
        importer = _default_importer
    disabled = set(disabled or [])

    for name in names:
        if name in disabled:
            continue
        try:
            module = importer(name)
        except Exception as exc:
            registry.failed.append((name, exc))
            _log(f"import failed: {name}\n" + traceback.format_exc())
            continue

        register = getattr(module, "register", None)
        if not callable(register):
            continue  # ليست إضافة

        api = PluginAPI(name, registry, window)
        try:
            register(api)
        except Exception as exc:
            registry.failed.append((name, exc))
            _log(f"register failed: {name}\n" + traceback.format_exc())
            continue  # المخازن المؤقّتة تُهمَل → تراجع نظيف

        api._commit()
        registry.loaded.append(name)

    return registry
