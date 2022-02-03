import glob
import json
import pathlib
import re
import logging

from .utils import *
from .parameter import Parameter, MetaParameter
from .sequencer import Sequencer
from .engine import Engine

class Module(Sequencer):
    """
    Interface between a software / hardware and the engine.

    **Instance properties**

    - `engine`: Engine instance
    - `logger`: python logger
    - `name`: module name
    - `parent_module`: parent module instance, `None` if the module is not a submodule
    - `module_path`: list of module names, from topmost parent (excluding the engine's `root_module`) to submodule
    - `submodules`: `dict` containing submodules added to the module with names as keys
    """

    @public_method
    def __init__(self, name, protocol=None, port=None, parent=None):
        """
        Module(name, protocol=None, port=None, parent=None)

        Base Module constructor.

        **Parameters**

        - `name`: module name
        - `protocol`: 'osc', 'osc.tcp', 'osc.unix' or 'midi'
        - `port`:
            port number if protocol is 'osc' or 'osc.tcp'
            unix socket path if protocol is 'osc.unix'
            None if protocol is 'midi' or if no osc input port is needed
        - `parent`:
            if the module is a submodule, this must be set
            to the parent module's instance
        """
        self.logger = logging.getLogger(__name__).getChild(name)
        self.name = name

        if '*' in name or '[' in name:
            self.logger.error('characters "*" and "[" are forbidden in module name')
            raise Exception

        if Engine.INSTANCE is None:
            self.logger.error('the engine must created before any module')
            raise Exception
        else:
            self.engine = Engine.INSTANCE

        self.parent_module = parent

        self.protocol = protocol
        if protocol == 'midi':
            self.port = name
        else:
            self.port = port

        self.parameters = {}
        self.animations = []
        self.meta_parameters = {}

        self.submodules = {}
        self.aliases = {}

        self.module_path = [name]
        parent = self.parent_module
        while parent is not None and parent is not self.engine.root_module:
            self.module_path.insert(0, parent.name)
            parent = parent.parent_module

        self.states = {}
        self.states_folder = ''
        self.states_folder = '%s/states/%s' % (self.engine.folder, '/'.join(self.module_path))
        for file in glob.glob('%s/*.json' % self.states_folder):
            name = file.split('/')[-1].split('.')[0]
            self.load(name, preload=True)

        Sequencer.__init__(self, 'module/' + '/'.join(self.module_path))

    @public_method
    def add_submodule(self, *modules):
        """
        add_submodule(*modules)

        Add a submodule.
        Submodule's protocol and port can be omitted, in which case
        they will be inherited from their parent. The submodule's parent
        instance must be provided in its constructor function (`parent` argument).

        **Parameters**

        - `modules`: Module objects (one module per argument)
        """
        for module in modules:
            if module.parent_module != self:
                self.logger.error('incorrect value for argument "parent" of submodule "%s".' % module.name)
                raise Exception
            self.submodules[module.name] = module
            if module.protocol is None:
                module.protocol = self.protocol
            if module.port is None:
                module.port = self.port
            module.parent_module = self

    @public_method
    def set_aliases(self, aliases):
        """
        set_aliases(aliases)

        Set aliases for submodules.
        Aliases can be used in place of the submodule_name argument in some methods.

        **Parameters**

        - `aliases`: {alias: name} dictionary
        """
        self.aliases = aliases

    @public_method
    def add_parameter(self, name, address, types, static_args=[], default=None):
        """
        add_parameter(name, address, types, static_args=[], default=None)

        Add parameter to module.

        **Parameters**

        - `name`: name of parameter
        - `address`: osc address of parameter
        - `types`: osc typetags string, one letter per value, including static values
        - `static_args`: list of static values before the ones that can be modified
        - `default`: value or list of values if the parameter has multiple dynamic values
        """
        self.parameters[name] = Parameter(name, address, types, static_args, default)
        self.reset(name)

    @public_method
    @submodule_method(pattern_matching=False)
    def get(self, *args):
        """
        get(parameter_name)
        get(submodule_name, param_name)

        Get value of parameter

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule

        **Return**

        List of values
        """
        name = args[0]

        if name in self.parameters:

            return self.parameters[name].get()

        else:
            self.logger.error('get: parameter "%s" not found' % name)

    @public_method
    @submodule_method(pattern_matching=True)
    def set(self, *args, force_send=False):
        """
        set(parameter_name, *args)
        set(submodule_name, param_nam, *args)

        Set value of parameter.
        Schedule a message if the new value differs from the one in memory.

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule, with wildcard ('*') and range ('[]') support
        - `*args`: value(s)
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            if parameter.animate_running:
                parameter.stop_animation()
            if parameter.set(*args[1:]) or force_send:
                if parameter.address:
                    self.send(parameter.address, *parameter.args)
                self.engine.dispatch_event('parameter_changed', self, name, parameter.get())
                self.check_meta_parameters(name)

        else:
            self.logger.error('set: parameter "%s" not found' % name)

    @public_method
    def reset(self, name=None):
        """
        reset(name=None)

        Reset parameter to its default values.

        **Parameters**

        - `name`: name of parameter. If omitted, affects all parameters including submodules'
        """
        if name is None:
            for sname in self.submodules:
                self.submodules[sname].reset()
            for name in self.parameters:
                self.reset(name)

        elif name in self.parameters:
            if (default := self.parameters[name].default) is not None:
                if type(default) == list:
                    self.set(name, *default)
                else:
                    self.set(name, default)


    @public_method
    @submodule_method(pattern_matching=True)
    def animate(self, *args, **kwargs):
        """
        animate(parameter_name, start, end, duration, mode='seconds', easing='linear')
        animate(submodule_name, parameter_name, start, end, duration, mode='beats', easing='linear')

        Animate parameter.

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule, with wildcard ('*') and range ('[]') support
        - `start`: starting value(s), can be None to use currnet value
        - `end`: ending value(s)
        - `duration`: animation duration
        - `mode`: 'seconds' or 'beats'
        - `easing`: easing function name
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            parameter.start_animation(self.engine, *args[1:], **kwargs)
            if name not in self.animations and parameter.animate_running:
                self.animations.append(name)
        else:
            self.logger.error('animate: parameter "%s" not found' % name)

    @public_method
    @submodule_method(pattern_matching=False)
    def stop_animate(self, *args):
        """
        stop_animate(parameter_name)
        stop_animate(submodule_name, param_name)

        Stop parameter animation.

        **Parameters**

        - `parameter_name`: name of parameter, can be '*' to stop all animations including submodules'.
        - `submodule_name`: name of submodule
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
                if parameter.update_animation(self.engine.current_time):
                    if parameter.address:
                        self.send(parameter.address, *parameter.args)
                    self.engine.dispatch_event('parameter_changed', self, name, parameter.get())
                    self.check_meta_parameters(name)
            else:
                self.animations.remove(name)

    @public_method
    def add_meta_parameter(self, name, parameters, getter, setter):
        """
        add_meta_parameter(name, parameters, getter, setter)

        Add a special parameter whose value depends on the state of one
        or several parameters owned by the module or its submodules.

        **Parameters**

        - `name`: name of meta parameter
        - `parameters`:
            list of parameter names involved in the meta parameter.
            Items may be lists if the parameters are owned by a submodule (`['submodule_name', 'parameter_name']`)
        - `getter`:
            callback function that will be called with the values of involved
            parameters as arguments whenever one these parameters changes.
            Its return value will define the meta parameter's value.
        - `setter`:
            callback function used to set the value of the parameters involved in the meta parameter when `set()` is called.
            The function's signature must not use *args or **kwargs arguments.
        """
        meta_parameter = MetaParameter(name, parameters, getter, setter, module=self)
        self.meta_parameters[name] = meta_parameter
        self.parameters[name] = meta_parameter
        self.update_meta_parameter(name)

    def check_meta_parameters(self, updated_parameter):
        """
        check_meta_parameters(updated_parameter)

        Update meta parameters in which updated parameter is involved.

        **Parameters**

        - `updated_parameter`: parameter name, may be a list if owned by a submodule.
        """
        if self.meta_parameters:
            if type(updated_parameter) is not list:
                updated_parameter = [updated_parameter]
            for name in self.meta_parameters:
                if updated_parameter in self.meta_parameters[name].parameters:
                    self.update_meta_parameter(name)

        # pass meta_parameter update to parent module
        if self.parent_module is not None and self.parent_module.meta_parameters:
            if type(updated_parameter) is not list:
                updated_parameter = [updated_parameter]
            updated_parameter.insert(0, self.name)
            self.parent_module.check_meta_parameters(updated_parameter)

    def update_meta_parameter(self, name):
        """
        update_meta_parameter(name)

        Update meta parameter state and emit appropriate event if it changed.

        **Parameters**

        - `name`: name of meta parameter
        """
        if self.meta_parameters[name].update():
            self.engine.dispatch_event('parameter_changed', self, name, self.meta_parameters[name].get())


    def get_state(self):
        """
        get_state()

        Get state of all parameters and submodules' parameters.

        **Return**

        List of lists that can be fed to set()
        """
        state = []

        for name in self.parameters:

            val = self.parameters[name].get()
            if type(val) is list:
                state.append([name, *val])
            else:
                state.append([name, val])

        for name in self.submodules:

            sstate = self.submodules[name].get_state()
            state = state + [[name] + x for x in sstate]

        return state

    def set_state(self, state, force_send=False):
        """
        set_state(state)

        Set state of any number of parameters and submodules' parameters.
        """
        for data in state:
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

        - `name`: name of state save (without file extension)
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
        self.logger.info('state "%s" saved to %s' % (name, file))

    @public_method
    def load(self, name, preload=False):
        """
        load(name)

        Load state from memory or from file if not preloaded already

        **Parameters**

        - `name`: name of state save (without file extension)
        """
        if name not in self.states and preload:

            file = '%s/%s.json' % (self.states_folder, name)
            f = open(file)
            self.states[name] = json.loads(f.read())
            f.close()
            self.logger.info('state "%s" preloaded from %s' % (name, file))

        if not preload:

            if name in self.states:
                self.set_state(self.states[name])
                self.logger.info('state "%s" loaded' % name)
            else:
                self.logger.error('state "%s" not found' % name)

    @public_method
    def route(self, address, args):
        """
        route(address, args)

        Route messages received by the engine on the module's port.
        Does nothing by default, method should be overriden in subclasses.
        Not called on submodules.

        **Parameters**

        - `address`: osc address
        - `args`: list of values

        **Return**

        `False` if the message should not be passed to the engine's
        active route after being processed by the module.
        """
        pass

    @public_method
    def send(self, address, *args):
        """
        send(address, *args)

        Send message to the module's port.

        **Parameters**

        - `address`: osc address
        - `*args`: values
        """
        proto = self.protocol
        port = self.port

        if not port and self.parent_module:
            proto = self.parent_module.protocol
            port = self.parent_module.port

        if port:
            message = [proto, port, address, *args]
            self.engine.queue.put(message)

    @public_method
    def add_event_callback(self, event, callback):
        """
        add_event_callback(event, callback)

        Bind a callback function to an event.

        **Parameters**

        - `event`: name of event
        - `callback`: function or method.
        The callback's signature must match the event's arguments.

        **Events**

        - `engine_started`: emitted when the engine starts.
        - `engine_stopping`: emitted before the engine stops
        - `engine_stopped`: emitted when the engine is stopped
        - `parameter_changed`: emitted when a module's parameter changes. Arguments:
            - `module`: instance of module that emitted the event
            - `name`: name of parameter
            - `value`: value of parameter or list of values

        """

        self.engine.add_event_callback(event, callback)
