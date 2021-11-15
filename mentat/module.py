import glob
import json
import pathlib
import re

from .utils import *
from .message import Message
from .parameter import Parameter
from .logger import Logger
from .sequencer import Sequencer

from functools import wraps
def submodule_method(method):
    """
    Decorator for Module methods that can be passed to submodules
    by passing the submodule's name as first argument instead
    of the usual first argument (ie parameter_name)
    """
    @wraps(method)
    def decorated(self, *args, **kwargs):
        name = args[0]

        if name in self.submodules or name in self.aliases:

            if name in self.aliases:
                name = self.aliases[name]

            return getattr(self.submodules[name], method.__name__)(*args[1:], **kwargs)

        else:

            return method(self, *args, **kwargs)

    return decorated

class Module(Logger, Sequencer):
    """
    Interface between a software / hardware and the engine.

    **Instance properties**

    - `engine`: Engine instance, available once the engine is started
    """

    @public_method
    def __init__(self, name, protocol=None, port=None):
        """
        Module(engine, name, protocol, port)
        Module(engine, name, protocol)
        Module(engine, name)

        Base Module constructor.
        Arguments protocol and port should be omitted only when the module is a submodule.

        **Parameters**

        - name: module name
        - protocol: 'osc' or 'midi'
        - port:
            udp port number or unix socket path if protocol is 'osc'
            can be None if the module has no fixed input port
        """
        Logger.__init__(self, __name__)
        Sequencer.__init__(self, __name__)

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

    @public_method
    def initialize(self, engine, submodule=False):
        """
        initialize(engine, submodule=False)

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
            for file in glob.glob('%s/*.json' % self.states_folder):
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

        for name in self.parameters:
            self.reset_parameter(name)

    @public_method
    def add_submodule(self, module):
        """
        add_submodule(module)

        Add a submodule.
        Submodule's protocol and port can be omitted, in which case
        they will be inherited from their parent.

        **Parameters**

        - module: Module object
        """
        self.submodules[module.name] = module
        if module.protocol is None:
            module.protocol = self.protocol
        if module.port is None:
            module.port = self.port
        if self.engine is not None:
            # if module is already initialized, initialize submodule
            module.initialize(self.engine, True)

    @public_method
    def set_aliases(self, aliases):
        """
        set_aliases(aliases)

        Set aliases for submodules.
        Aliases can be used in place of the submodule_name argument in some methods.

        **Parameters**

        - aliases: {alias: name} dictionary
        """
        self.aliases = aliases

    @public_method
    def add_parameter(self, name, address, types, static_args=[], default=None):
        """
        add_parameter(name, address, types, static_args=[], default=None)

        Add parameter to module.

        **Parameters**

        - name: name of parameter
        - address: osc address of parameter
        - types: osc typetags string, one letter per value, including static values
        - static_args: list of static values before the ones that can be modified
        - default: value or list of values
        """
        self.parameters[name] = Parameter(name, address, types, static_args)
        if self.engine is not None:
            # if module is already initialized, initialize parameter
            self.reset_parameter(name)

    def reset_parameter(self, name):
        """
        reset_parameter(name)

        Apply parameter's default value and send it.

        **Parameters**

        - name: name of parameter
        """
        if default := self.parameters[name].default is not None:
            if type(default) == list:
                self.set(name, *default)
            else:
                self.set(name, default)

    @public_method
    @submodule_method
    def get(self, *args):
        """
        get(parameter_name)
        get(submodule_name, param_name)

        Get value of parameter

        **Parameters**

        - parameter_name: name of parameter
        - submodule_name: name of submodule

        **Return**

        List of values
        """
        name = args[0]

        if name in self.parameters:

            return self.parameters[name].get()

        else:
            self.error('get: parameter "%s" not found' % name)

    @public_method
    @submodule_method
    def set(self, *args, force_send=False):
        """
        set(parameter_name, *args)
        set(submodule_name, param_nam, *args)

        Set value of parameter.
        Schedule a message if the new value differs from the one in memory.

        **Parameters**

        - parameter_name: name of parameter
        - submodule_name: name of submodule
        - *args: value(s)
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            if parameter.animate_running:
                parameter.stop_animation()
            if self.port:
                if change := parameter.set(*args[1:]) or force_send:
                    self.send(parameter.address, *parameter.args)
                    self.engine.put.append(message)
                    if change:
                        self.notify_parameter_change(name)
        else:
            self.error('set: parameter "%s" not found' % name)

    @public_method
    def reset(self):
        """
        reset()

        Reset all parameters to their default values (including submodules')
        """
        for sname in self.submodules:
            self.submodules[sname].reset()
        for name in self.parameters:
            self.reset_parameter(name)

    @public_method
    @submodule_method
    def animate(self, *args, **kwargs):
        """
        animate(parameter_name, start, end, duration, mode='seconds', easing='linear')
        animate(submodule_name, parameter_name, start, end, duration, mode='beats', easing='linear')

        Animate parameter.

        **Parameters**

        - parameter_name: name of parameter
        - submodule_name: name of submodule
        - start: starting value(s), can be None to use currnet value
        - end: ending value(s)
        - duration: animation duration
        - mode: 'seconds' or 'beats'
        - easing: easing function name
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            parameter.start_animation(self.engine, *args[1:], **kwargs)
            if name not in self.animations and parameter.animate_running:
                self.animations.append(name)
        else:
            self.error('animate: parameter "%s" not found' % name)

    @public_method
    @submodule_method
    def stop_animate(self, *args):
        """
        stop_animate(parameter_name)
        stop_animate(submodule_name, param_name)

        Stop parameter animation.

        **Parameters**

        - parameter_name: name of parameter, can be '*' to stop all animations.
        - submodule_name: name of submodule, name of parameter
        """
        name = args[0]

        if name == '*':

            for sname in self.submodules:
                self.submodules[sname].stop_animation('*')
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
                    self.send(parameter.address, *parameter.args)
                    self.notify_parameter_change(name)
            else:
                self.animations.remove(name)

    def get_state(self):
        """
        get_state()

        Get state of all parameters and submodules' parameters.

        **Return**

        List of lists that can be fed to set()
        """
        state = []

        for name in self.parameters:

            state.append([name, *self.parameters[name].get()])

        for name in self.submodules:

            sstate = self.submodules[name].get_state()
            state = state + [[name] + x for x in sstate]

        return state

    def set_state(self, state, force_send=False):
        """
        set_state(state)

        Set state of any number of parameters and submodules' parameters.
        """
        for data in self.states[name]:
            self.set(*data, force_send=force_send)

    @public_method
    def send_state(self):
        """
        send_state()

        Send current state of all parameters and submodules' parameters.
        """
        self.set_state(self.get_state(), force_send=True)

    @public_method
    def save(self, name):
        """
        save(name)

        Save current state (including submodules) to file.

        **Parameters**

        - name: name of state save (without file extension)
        """
        file = '%s/%s.json' % (self.states_folder, name)
        self.states[name] = self.get_state()
        pathlib.Path(self.states_folder).mkdir(parents=True, exist_ok=True)
        f = open(file, 'w')
        s = json.dumps(self.states[name], indent=2)
        s = re.sub(r'\n\s\s\s\s', ' ', s)
        s = re.sub(r'\n\s\s(\],?)', r'\1', s)
        s = re.sub(r'\s\s\[\s', '  [', s)
        f.write(s)
        f.close()
        self.info('%s: state "%s" saved to %s' % (self.name, name, file))

    @public_method
    def load(self, name, preload=False):
        """
        load(name)

        Load state from memory or from file if not preloaded already

        **Parameters**

        - name: name of state save (without file extension)
        """
        if name not in self.states and preload:

            file = '%s/%s.json' % (self.states_folder, name)
            f = open(file)
            self.states[name] = json.loads(f.read())
            f.close()
            self.info('%s: state "%s" preloaded from %s' % (self.name, name, file))

        if not preload:

            if name in self.states:
                self.set_state(self.states[name])
                self.info('%s: state "%s" loaded' % (self.name, name))
            else:
                self.error('%s: state "%s" not found' % (self.name, name))

    @public_method
    def route(self, address, args):
        """
        route(address, args)

        Route messages received by the engine on the module's port.
        Does nothing by default, method should be overriden in subclasses.
        Not called on submodules.

        **Parameters**

        - address: osc address
        - args: list of values

        **Return**

        `False` the message should not be passed to the engine's
        active route after being processed by the module.
        """
        pass

    @public_method
    def send(self, address, *args):
        """
        send(address, *args)

        Send message to the module's port.

        **Parameters**

        - address: osc address
        - *args: values
        """
        if self.port:
            message = Message(self.protocol, self.port, address, *args)
            self.engine.queue.put(message)

    @public_method
    def watch_module(self, *args):
        """
        watch_module(module_name, param_name, callback)

        Watch changes of a module's parameter.
        Used by controller modules to collect feedback.

        **Parameters**

        - module_name:
            name of module This argument can be suplied multiple time if
            targetted module is a submodule
        - parameter_name:
            name of parameter, can be '*' to subscribe to all parameters
            including submodules'
        """
        module_path = '/'.join(args[:-1])
        parameter_name = args[-1]
        if module_path not in self.watched_modules:
            self.watched_modules[module_path] = []
        self.watched_modules[module_path].append(parameter_name)

    @public_method
    def watched_module_changed(self, module_path, name, args):
        """
        watched_module_changed(module_path, name, args)

        Called when the value of a watched module's parameter updates.
        To be overridden in subclasses.

        **Parameters**

        - module_path: list of module names (from parent to submodule)
        - name: name of parameter
        - args: values
        """
        pass

    @submodule_method
    def add_parameter_change_callback(self, *args):
        """
        add_parameter_change_callback(parameter_name, callback)
        add_parameter_change_callback(submodule_name, param_name, callback)

        Register a callback function to be called whenever the value
        of a parameter changes. Used by controller modules to collect feedback.

        **Parameters**

        - submodule_name:
            name of submodule
        - parameter_name:
            name of parameter, can be '*' to subscribe to all parameters
            including submodules'
        - callback:
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

        **Parameters**

        - name: name of parameter
        """
        if name in self.parameters_callbacks:
            for callback in self.parameters_callbacks[name]:
                callback(self.module_path, name, self.get(name))
