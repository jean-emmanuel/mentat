from sys import version_info
if version_info[0] != 3:
    print('Error: Python 3 is required')
del version_info

__version__ = '1.0.0-alpha'

from .engine import Engine
from .module import Module
from .route import Route
