# load local package
from sys import path
path.insert(0, '../')

import logging
logging.basicConfig(level=logging.INFO)

from mentat.engine import Engine

from modules import *

from routes.a import A
from routes.b import B

engine.add_module(klick1)
engine.add_module(klick2)
engine.add_module(pedalboard)
engine.add_module(nonmixer)
engine.add_module(kbd)

engine.add_route(A())
engine.add_route(B())

engine.set_route('A')

engine.autorestart()
engine.start()
