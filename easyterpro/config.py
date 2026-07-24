# -*- coding: utf-8 -*-
"""نظام إعدادات بسيط: دمج الافتراضيّات مع ملفّ المستخدم (JSON)، حفظ، وإشعار بالتغيير.

مستوحى من ConfigProxy في Tabby، مبسَّط: ملفّ واحد قابل للتحرير، نسخة مفردة مشتركة.
"""

import json
import os

from PySide6.QtCore import QObject, Signal

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".easyterpro")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "theme": "EasyTer Dark",
    # BiDi/تشكيل على مستوى السطر: ممتاز لمخرجات الصدفة، لكن أطفئه لتطبيقات ملء
    # الشاشة (Claude Code / vim) التي تفعل تخطيطها الخاصّ فيتعارض معها (معالجة مزدوجة).
    "bidi": True,
    # ثيمات مخصّصة يضيفها/يعدّلها المستخدم (تَطغى على المدمجة بنفس الاسم):
    #   "custom_themes": {"اسمي": {"bg":"#..","fg":"#..","ansi":{"black":"#..", ... }}}
    "custom_themes": {},
    "font": {"family": "Consolas", "arabic_family": "Amiri", "size": 13},
    # شكل المؤشّر: block (مربّع) / beam (عمود) / underline (تحته) + وميض
    "cursor": {"style": "block", "blink": True},
    "default_profile": "PowerShell",
    # ملفّات صدفة مخصّصة يضيفها المستخدم؛ تُدمج مع المكتشَفة تلقائيًّا
    # كلّ عنصر: {"name": "...", "command": "..."}
    "profiles": [],
    # الإضافات (plugins) المرفقة: كلّها تُحمَّل افتراضيًّا. عطّل إضافة باسمها في
    # disabled، وخصّص إعداداتها تحت settings.<اسم الإضافة>.
    #   "plugins": {"disabled": ["sample_overlay"], "settings": {"myplugin": {...}}}
    "plugins": {"disabled": [], "settings": {}},
}


def _deep_merge(base, override):
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config(QObject):
    """إعدادات مشتركة. اقرأ بـget(...)، اكتب بـset(...). يحفظ تلقائيًّا ويُطلق changed."""

    changed = Signal()

    def __init__(self):
        super().__init__()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            self._data = _deep_merge(DEFAULTS, user)
        except FileNotFoundError:
            self._data = json.loads(json.dumps(DEFAULTS))  # نسخة عميقة
            self.save()   # اكتب ملفًّا افتراضيًّا أوّل مرّة ليحرّره المستخدم
        except Exception:
            self._data = json.loads(json.dumps(DEFAULTS))

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def get(self, *keys, default=None):
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def set(self, value, *keys):
        node = self._data
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self.save()
        self.changed.emit()

    @property
    def path(self):
        return CONFIG_PATH


# ---- نسخة مفردة مشتركة ----
_instance = None


def config():
    global _instance
    if _instance is None:
        _instance = Config()
    return _instance
