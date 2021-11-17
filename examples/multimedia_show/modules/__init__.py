from mentat.module import Module
from mentat.engine import Engine
from .klick import Klick
from .pedalboard import Pedalboard
from .nonmixer import NonMixer

from os.path import dirname

engine = Engine('JoeLeMentat', 5555, dirname(__file__) + '/../')

nonmixer = NonMixer('non', 'osc', 11143)

klick1 = Klick('klick-1', 'osc', 12000)
klick2 = Klick('klick-2', 'osc', 13000)

pedalboard = Pedalboard('pedalboard', 'osc', None)

kbd = Module('kbd', 'midi')
mon = Module('mon', 'midi')
