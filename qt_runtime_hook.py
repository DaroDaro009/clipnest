"""Give frozen PySide6 imports their bundled DLL directory before Qt's hook runs."""

import os
import sys
import ctypes


if os.name == "nt":
    qt_dir = os.path.join(sys._MEIPASS, "PySide6")
    shiboken_dir = os.path.join(sys._MEIPASS, "shiboken6")
    _clipnest_shiboken_directory = os.add_dll_directory(shiboken_dir)
    if os.path.isdir(qt_dir):
        _clipnest_qt_directory = os.add_dll_directory(qt_dir)
        os.environ["PATH"] = qt_dir + os.pathsep + shiboken_dir + os.pathsep + os.environ.get("PATH", "")
        for binary in ("Qt6Core.dll", "pyside6.abi3.dll"):
            ctypes.WinDLL(os.path.join(qt_dir, binary))
