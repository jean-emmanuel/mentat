# add local package to import path
# not needed if package is installed
from sys import path
path.insert(0, '../../')

# configure logging
import logging
logging.basicConfig(level=logging.INFO)

# add modules
from modules import *
engine.add_module(klick1)
engine.add_module(klick2)
engine.add_module(pedalboard)
engine.add_module(nonmixer)
engine.add_module(kbd)

# add routes
from routes import *
engine.add_route(trackA)

# set default route
engine.set_route('A')

# enable autorestart upon file modification
engine.autorestart()

# start main loop
engine.start()
