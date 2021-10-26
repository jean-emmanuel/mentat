import logging
LOGGER = logging.getLogger(__name__)

import glob
import json

from .message import Message
from .parameter import Parameter

def submodule_method(method):
    """
    Decorator for Module methods that can be passed to submodules
    by passing the submodule's name as first argument instead
    of the usual first argument (ie parameter_name)
    """
    def decorated(self, *args, **kwargs):
        name = args[0]

        if name in self.submodules or name in self.aliases:

            if name in self.aliases:
                name = self.aliases[name]

            return getattr(self.submodules[name], method.__name__)(*args[1:], **kwargs)

        else:

            return method(self, *args, **kwargs)

    return decorated

class Module():

    def __init__(self, name, protocol=None, port=None):
        """
        Module(engine, name, protocol, port)
        Module(engine, name)

        Base Module constructor.
        Arguments protocol and port should be omitted only when the module is a submodule.

        :param name: module name
        :param protocol: 'osc' or 'midi'
        :param port:
            udp port number or unix socket path if protocol is 'osc'
            else midi port name (only used in alsa/jack)
            can be None module has no fixed input port
        """

        self.engine = None
        self.name = name
        self.protocol = protocol
        if protocol == 'osc' and type(port) is str and port[0] == '/':
            self.port = 'osc.unix://' + port
        else:
            self.port = port

        self.parameters = {}
        self.animations = []

        self.submodules = {}
        self.aliases = {}

        self.states = {}
        self.states_folder = ''

    def initialize(self, engine):
        """
        initialize()

        Called by the engine when started.
        """
        self.engine = engine
        for name in self.submodules:
            self.submodules[name].engine = engine

        self.states_folder = '%s/states/%s' % (self.engine.folder, self.name)
        for file in glob.glob('%s/*.json'):
            name = file.split('/')[-1].split('.')[0]
            self.load(name, preload=True)

    def add_submodule(self, module):
        """
        add_submodule(module)

        Add a submodule.
        Submodule's protocol and port can be omitted,
        they will be inherited from their parent.

        :param module: Module object
        """
        self.submodules[module.name] = module
        module.protocol = self.protocol
        module.port = self.port

    def add_parameter(self, name, address=None, types=None, static_args=[]):
        """
        add_parameter(parameter)
        add_parameter(name, address, types)
        add_parameter(name, address, types, static_args)

        Add parameter to module.

        :param parameter: parameter object
        :param name: name of parameter
        :param address: osc address of parameter
        :param types: osc typetags string, one letter per value, including static values
        :param static_args: list of static values before the ones that can be modified
        """
        if isinstance(name, Parameter):
            self.parameters[name.name] = parameter
        else:
            self.parameters[name] = Parameter(
                name, address, types, static_args
            )

    @submodule_method
    def get(self, *args):
        """
        get(parameter_name)
        get(submodule_name, param_name)

        Get value of parameter

        :param parameter_name: name of parameter
        :param submodule_name: name of submodule, name of parameter

        :return:
            List of values
        """
        name = args[0]

        if name in self.parameters:

            return self.parameters[name].get(*args)

        else:
            LOGGER.error('get: parameter "%s" not found' % name)

    @submodule_method
    def set(self, *args):
        """
        set(parameter_name, *args)
        set(submodule_name, param_nam, *args)

        Set value of parameter.
        Schedule a message if the new value differs from the one in memory.

        :param parameter_name: name of parameter
        :param submodule_name: name of submodule, name of parameter
        :param *args: value(s)
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            if parameter.animate_running:
                parameter.stop_animation()
            if parameter.set(*args[1:]) and self.port:
                message = Message(self.protocol, self.port, parameter.address, *parameter.args)
                self.engine.queue.append(message)

        else:
            LOGGER.error('set: parameter "%s" not found' % name)

    @submodule_method
    def animate(self, *args, **kwargs):
        """
        animate(parameter_name, start, end, duration, easing='linear'):
        animate(submodule_name, parameter_name, start, end, duration, easing='linear'):

        Animate parameter.

        :param parameter_name: name of parameter
        :param submodule_name: name of submodule
        :param start: starting value(s), can be None to use currnet value
        :param end: ending value(s)
        :param duration: animation duration
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            parameter.start_animation(self.engine.current_time, *args[1:], **kwargs)
            if name not in self.animations and parameter.animate_running:
                self.animations.append(name)

        else:
            LOGGER.error('animate: parameter "%s" not found' % name)

    @submodule_method
    def stop_animate(self, *args):
        """
        stop_animate(parameter_name)
        stop_animate(submodule_name, param_name)

        Stop parameter animation.

        :param parameter_name: name of parameter, can be '*' to stop all animations.
        :param submodule_name: name of submodule, name of parameter
        """
        name = args[0]

        if name == '*':

            for name in self.animations:
                self.parameters[name].stop_animation()

            self.animations = []

        elif name in self.animations:

            self.parameters[name].stop_animation()


    def update_animations(self):
        """
        update_animations()

        Update animated parameters. Called by the engine every ANIMATION_PERIOD.
        """
        for name in self.submodules:

            self.submodules[name].update_animations()

        for name in self.animations:

            parameter = self.parameters[name]
            if parameter.animate_running:
                if parameter.update_animation(self.engine.current_time) and self.port:
                    message = Message(self.protocol, self.port, parameter.address, *parameter.args)
                    self.engine.queue.append(message)
            else:
                self.animations.remove(name)

    def get_state(self):
        """
        get_state()

        Get state of all parameters and submodules' parameters.

        :return:
            List of lists that can be fed to set()
        """
        state = []

        for name in self.parameters:

            state.append([name, self.parameters[name].get()])

        for name in self.submodules:

            sstate = self.submodules[name].get_state()
            state = state + [[name] + x for x in sstate]

        return state

    def save(self, name):
        """
        save(name)

        Save current state (including submodules) to file.

        :param name: name of state save (without file extension)
        """
        file = '%s/%s.json' % (self.states_folder, name)
        self.states[name] = self.get_state()
        f = open(file, 'w')
        f.write(json.dumps(self.states[name]))
        f.close()
        LOGGER.info('%s: state "%s" saved to %s' % (self.name, name, file))

    def load(self, name, preload=False):
        """
        load(name)

        Load state from memory or from file if not preloaded already

        :param name: name of state save (without file extension)
        """
        if name not in self.states:

            file = '%s/%s.json' % (self.states_folder, name)
            f = open(file)
            self.state[name] = json.loads(f.read())
            f.close()
            LOGGER.info('%s: state "%s" preloaded from %s' % (self.name, name, file))

        if not preload:

            for data in self.state[name]:

                self.set(*data)
                LOGGER.info('%s: state "%s" loaded' % (self.name, name))


    def route(self, address, args):
        """
        route(address, args)

        Route messages received by the engine on the module's port.
        Does nothing by default, method should be overriden in subclasses.
        Not called on submodules.

        :param address: osc address
        :param args: list of values
        """
        pass

    def send(self, address, *args):
        """
        send(address, *args)

        Send message to the module's port.

        :param address: osc address
        :param *args: values
        """
        if self.port:
            self.engine.send(self.protocol, self.port, address, *args)
