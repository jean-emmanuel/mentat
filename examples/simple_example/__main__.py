# add local package to import path
# not needed if package is installed
from sys import path
from os.path import dirname
path.insert(0, dirname(__file__) + '/../../')

# import mentat
from mentat import Engine, Module, Route

# create engine
engine = Engine('Mentat', 5555, dirname(__file__) + '/../')

# create a module that will talk with a software
# listening on (and sending from) port 20000
mod = Module('a', 'osc', 20000)

# add some parameters to it
# whene their value change in mentat, a message is sent
mod.add_parameter('x', address='/x', types='f', default=0)
mod.add_parameter('y', address='/y', types='f')
mod.add_parameter('xy', address='/xy', types='ff')

# create mapping between them
mod.add_mapping(['x', 'y'], 'xy', lambda x, y: [x, y])
mod.add_mapping('xy', 'x', lambda xy: xy[0])
mod.add_mapping('xy', 'y', lambda xy: xy[1])

mod.add_meta_parameter('test', ['x', 'y'], getter=lambda x,y: x+y, setter=lambda t: [mod.set('x', t/2),mod.set('y', t/2)])

# add module to engine
engine.add_module(mod)

# print parameter changes
engine.add_event_callback(
    'parameter_changed',
    lambda module, param, value: engine.logger.info('parameter changed: %s.%s -> %s' % (module.name, param, value))
)

# create a simple route
class SimpleRoute(Route):

    def activate(self):
        self.logger.info('activated ! ')
        self.logger.info('try sending /foo or /bar on port 5555')

    def route(self, protocol, port, address, args):
        self.logger.info('received message from port %s: %s %s' % (port, address, args))

        if address == '/foo':
            mod.set('x', 1)

        if address == '/bar':
            mod.set('xy', 1, 2)

# add route to engine and activate it
engine.add_route(SimpleRoute('A'))
engine.set_route('A')

# enable autorestart upon file modification
engine.autorestart()

# start main loop
engine.start()
