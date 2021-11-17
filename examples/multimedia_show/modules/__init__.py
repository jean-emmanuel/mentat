from mentat.module import Module
from mentat.engine import Engine
from .klick import Klick
from .pedalboard import Pedalboard
from .nonmixer import NonMixer

engine = Engine('JoeLeTaxi', 5555, '/home/bordun/Dev/Mentat/example')

nonmixer = NonMixer('non', 'osc', 11143)

klick1 = Klick('klick-1', 'osc', 12000)
klick2 = Klick('klick-2', 'osc', 13000)

pedalboard = Pedalboard('pedalboard', 'osc', None)

pedalboard2 = Pedalboard('pedalboard-2', 'osc', None)
pedalboard3 = Pedalboard('pedalboard-3', 'osc', None)

kbd = Module('kbd', 'midi')
mon = Module('mon', 'midi')
