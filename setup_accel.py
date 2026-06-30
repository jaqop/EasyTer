"""Optional native acceleration build for EasyTer.

Compiles bidi_fast.py to a C extension so its hot character/BiDi loops run
natively. Build is OPTIONAL - EasyTer falls back to the pure-Python bidi_fast.py
when the extension is not built. The .pyd, once built, shadows the .py on import.

Build:  python setup_accel.py build_ext --inplace
Clean:  remove bidi_fast.c and bidi_fast.*.pyd

Requires Cython + a C compiler (MSVC Build Tools on Windows).
"""
from setuptools import setup
from Cython.Build import cythonize

setup(
    name="easyter_accel",
    ext_modules=cythonize(
        "bidi_fast.py",
        # These funcs operate on Python str/list objects (not typed memoryviews),
        # so boundscheck/wraparound give nothing here and wraparound=False would make
        # units[-1] undefined. Keep only the language level.
        compiler_directives={"language_level": "3"},
    ),
    zip_safe=False,
)
