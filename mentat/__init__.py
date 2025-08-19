"""
Mentat
HUB / Conductor for OSC / MIDI capable softwares
"""

from .engine import Engine
from .module import Module
from .route import Route

__version__ = '1.8.4'

__all__ = [
    'Engine',
    'Module',
    'Route'
]
