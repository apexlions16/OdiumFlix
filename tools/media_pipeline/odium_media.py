#!/usr/bin/env python3
"""Bootstrap for the generated OdiumFlix lossless media worker source."""
from __future__ import annotations

import argparse, base64, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.parse, urllib.request, uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence
from odium_media_payload_00 import PART as _PART_00
from odium_media_payload_01 import PART as _PART_01
from odium_media_payload_02 import PART as _PART_02
from odium_media_payload_03 import PART as _PART_03
from odium_media_payload_04 import PART as _PART_04
from odium_media_payload_05 import PART as _PART_05
from odium_media_payload_06 import PART as _PART_06
from odium_media_payload_07 import PART as _PART_07
from odium_media_payload_08 import PART as _PART_08

_SOURCE = base64.b64decode("".join([_PART_00,_PART_01,_PART_02,_PART_03,_PART_04,_PART_05,_PART_06,_PART_07,_PART_08])).decode("utf-8")
exec(compile(_SOURCE, __file__, "exec"), globals(), globals())
