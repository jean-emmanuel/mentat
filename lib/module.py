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
        Module(engine, name, protocol)
        Module(engine, name)

        Base Module constructor.
        Arguments protocol and port should be omitted only when the module is a submodule.

        :param name: module name
        :param protocol: 'osc' or 'midi'
        :param port:
            udp port number or unix socket path if protocol is 'osc'
            can be None module has no fixed input port
        """

        self.engine = None

        self.name = name
        self.protocol = protocol
        if protocol == 'osc' and type(port) is str and port[0] == '/':
            self.port = 'osc.unix://' + port
        elif protocol == 'midi':
            self.port = name
        else:
            self.port = port

        self.parameters = {}
        self.animations = []

        self.parameters_callbacks = {}
        self.watched_modules = {}

        self.submodules = {}
        self.aliases = {}

        self.module_path = [name]

        self.states = {}
        self.states_folder = ''

    def initialize(self, engine, submodule=False):
        """
        initialize()

        Called by the engine when started.
        """
        self.engine = engine

        if submodule:
            # init for submodules only
            for name in self.submodules:
                self.submodules[name].module_path = self.module_path + module.module_path

        else:
            # init for 1st level modules only
            self.states_folder = '%s/states/%s' % (self.engine.folder, self.name)
            for file in glob.glob('%s/*.json'):
                name = file.split('/')[-1].split('.')[0]
                self.load(name, preload=True)

        # init submodules
        for name in self.submodules:
            self.submodules[name].initialize(self.engine, True)

        for module_path in self.watched_modules:
            # register watched modules callbacks
            parameter_names = self.watched_modules[module_path]
            module_path = module_path.split('/')
            module_name = module_path[0]
            if module_name in self.engine.modules:
                module = self.engine.modules[module_name]
                for name in parameter_names:
                    module.add_parameter_change_callback(
                        *module_path[1:],
                        name,
                        self.watched_module_changed
                    )

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
        if self.engine is not None:
            # if module is already initialized, initialize submodule
            module.initialize(self.engine, True)

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

            return self.parameters[name].get()

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
                self.notify_parameter_change(name)
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
                    self.notify_parameter_change(name)
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

    def watch_module(self, *args):
        """
        watch_module(submodule_name, param_name, callback)

        Watch changes of a module's parameter.
        Used by controller modules to collect feedback.

        :param module_name:
            name of module This argument can be suplied multiple time if
            targetted module is a submodule
        :param parameter_name:
            name of parameter, can be '*' to subscribe to all parameters
            including submodules'
        """
        module_path = '/'.join(args[:-1])
        parameter_name = args[-1]
        if module_path not in self.watched_modules:
            self.watched_modules[module_path] = []
        self.watched_modules[module_path].append(parameter_name)

    def watched_module_changed(self, module_path, name, args):
        """
        watched_module_changed(module_path, name, args)

        Called when the value of a watched module's parameter updates.
        To be overridden in subclasses.

        :param module_path: list of module names (from parent to submodule)
        :param name: name of parameter
        :param args: values
        """
        pass

    @submodule_method
    def add_parameter_change_callback(self, *args):
        """
        add_parameter_change_callback(parameter_name, callback)
        add_parameter_change_callback(submodule_name, param_name, callback)

        Register a callback function to be called whenever the value
        of a parameter changes. Used by controller modules to collect feedback.

        :param submodule_name:
            name of submodule
        :param parameter_name:
            name of parameter, can be '*' to subscribe to all parameters
            including submodules'
        :param callback:
            function or method
        """
        name = args[0]
        callback = args[1]

        if name == '*':
            for sname in self.submodules:
                self.submodules[sname].add_parameter_change_callback('*', callback)
            for pname in self.parameters:
                self.add_parameter_change_callback(pname, callback)

        if name not in self.parameters_callbacks:
            self.parameters_callbacks[name] = []

        self.parameters_callbacks[name].append(callback)

    def notify_parameter_change(self, name):
        """
        notify_parameter_change(name)

        Called when the value of a parameter changes.
        This calls registered callbacks for this parameter with three arguments:
            module_path: list of module names (from parent to submodule)
            name: name of parameter
            args: values

        :param name: name of parameter
        """
        if name in self.parameters_callbacks:
            for callback in self.parameters_callbacks[name]:
                callback(self.module_path, name, self.get(name))
