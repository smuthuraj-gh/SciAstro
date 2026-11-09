"""Swiss Ephemeris access.

pyswisseph is used when it is installed (Linux, e.g. Streamlit Community Cloud). On Windows, where pyswisseph has
no prebuilt wheel, the Swiss Ephemeris DLL is called through ctypes instead (SWE_DLL, default C:\\sweph\\bin\\swedll64.dll).
Both read the .se1 files in ../ephe.
"""
from __future__ import annotations

import ctypes
import os
import threading
from pathlib import Path

EPHE_PATH = str(Path(__file__).resolve().parent.parent / "ephe")

GREG_CAL = 1
FLG_SWIEPH = 2
FLG_SPEED = 256
FLG_EQUATORIAL = 2048
CALC_FLAGS = FLG_SWIEPH | FLG_EQUATORIAL | FLG_SPEED
# The Swiss Ephemeris keeps its state in globals: two page loads calling it at once can crash the server (an access
# violation), so one call at a time
_ONE_AT_A_TIME = threading.Lock()

try:
    import swisseph as _swe

    _swe.set_ephe_path(EPHE_PATH)
    BACKEND = "pyswisseph"

    def calc_ut(jd_ut: float, ipl: int) -> tuple[tuple[float, ...] | None, str]:
        """(RA, Dec, distance AU, and their daily speeds), or (None, error text)."""
        try:
            with _ONE_AT_A_TIME:
                x, _flags = _swe.calc_ut(jd_ut, ipl, CALC_FLAGS)
            return tuple(x), ""
        except _swe.Error as exc:  # pragma: no cover - depends on the files
            return None, str(exc)

    def julday(y: int, m: int, d: int, hour: float) -> float:
        with _ONE_AT_A_TIME:
            return _swe.julday(y, m, d, hour, GREG_CAL)

    def sidtime(jd_ut: float) -> float:
        """Apparent sidereal time at Greenwich, hours."""
        with _ONE_AT_A_TIME:
            return _swe.sidtime(jd_ut)

except ImportError:
    _dll = ctypes.CDLL(os.environ.get("SWE_DLL", r"C:\sweph\bin\swedll64.dll"))
    _dll.swe_set_ephe_path.argtypes = [ctypes.c_char_p]
    _dll.swe_set_ephe_path.restype = None
    _dll.swe_calc_ut.argtypes = [ctypes.c_double, ctypes.c_int32, ctypes.c_int32,
                                 ctypes.POINTER(ctypes.c_double), ctypes.c_char_p]
    _dll.swe_calc_ut.restype = ctypes.c_int32
    _dll.swe_julday.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_int]
    _dll.swe_julday.restype = ctypes.c_double
    _dll.swe_sidtime.argtypes = [ctypes.c_double]
    _dll.swe_sidtime.restype = ctypes.c_double
    _dll.swe_set_ephe_path(EPHE_PATH.encode("mbcs"))
    BACKEND = "swedll64 (ctypes)"

    def calc_ut(jd_ut: float, ipl: int) -> tuple[tuple[float, ...] | None, str]:
        x = (ctypes.c_double * 6)()
        err = ctypes.create_string_buffer(256)
        with _ONE_AT_A_TIME:
            failed = _dll.swe_calc_ut(jd_ut, ipl, CALC_FLAGS, x, err) < 0
        if failed:
            return None, err.value.decode("latin-1", "replace")
        return tuple(x), ""

    def julday(y: int, m: int, d: int, hour: float) -> float:
        with _ONE_AT_A_TIME:
            return _dll.swe_julday(y, m, d, hour, GREG_CAL)

    def sidtime(jd_ut: float) -> float:
        with _ONE_AT_A_TIME:
            return _dll.swe_sidtime(jd_ut)
