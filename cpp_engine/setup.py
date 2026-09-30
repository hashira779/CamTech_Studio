import os
import sys
from setuptools import setup, Extension
import pybind11

ext_modules = [
    Extension(
        "vida_cpp",
        ["vida_cpp.cpp"],
        include_dirs=[pybind11.get_include()],
        language="c++",
        extra_compile_args=["/O2", "/fp:fast", "/arch:AVX2"] # Aggressive optimizations for MSVC
    ),
]

setup(
    name="vida_cpp",
    version="1.0.0",
    author="VIDA Engine",
    description="Ultra-fast C++ rendering backend for VIDA",
    ext_modules=ext_modules,
)
