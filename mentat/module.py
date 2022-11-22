import glob
import json
import pathlib
import re
import logging
from queue import Queue

from .utils import *
from .parameter import Parameter, MetaParameter
from .sequencer import Sequencer

class Module(Sequencer):
    """
    Interface between a software / hardware and the engine.

    **Instance properties**

    - `engine`: Engine instance
    - `logger`: python logger
    - `name`: module name
    - `parent_module`: parent module instance, `None` if the module is not a submodule
    - `module_path`: list of module names, from topmost parent (engine) to submodule
    - `submodules`: `dict` containing submodules added to the module with names as keys
    - `parameters`: `dict` containing parameters (including meta parameters) added to the module with names as keys
    - `meta_parameters`: `dict` containing meta parameters added to the module with names as keys
    """

    @public_method
    def __init__(self, name, protocol=None, port=None, parent=None):
        """
        Module(name, protocol=None, port=None, parent=None)

        Base Module constructor.

        **Parameters**

        - `name`: module name
        - `protocol`: 'osc', 'osc.tcp', 'osc.unix' or 'midi'
        - `port`: port used by the software / hardware to send and receive messages
            - port number if protocol is 'osc' or 'osc.tcp'
            - unix socket path if protocol is 'osc.unix'
            - `None` if protocol is 'midi' or if no port is needed
        - `parent`:
            if the module is a submodule, this must be set
            to the parent module's instance
        """
        logger_name = name
        if parent is not None:
            logger_name = parent.name + '.' + name
        self.logger = logging.getLogger(__name__).getChild(logger_name)

        self.name = name

        if '*' in name or '[' in name:
            self.logger.critical('characters "*" and "[" are forbidden in module name')

        from .engine import Engine
        if Engine.INSTANCE is None:
            self.logger.critical('the engine must created before any module')
        else:
            self.engine = Engine.INSTANCE
        if self != Engine.INSTANCE and parent is None:
            parent = Engine.INSTANCE

        self.parent_module = parent

        self.protocol = protocol
        if self != Engine.INSTANCE:
            if protocol == 'midi':
                self.port = name
            else:
                self.port = port

        self.parameters = {}
        self.animations = []
        self.meta_parameters = {}

        self.dirty_parameters = Queue()
        self.dirty = False

        self.submodules = {}
        self.aliases = {}

        self.module_path = [name]
        parent = self.parent_module

        while parent is not None:#   and parent is not self.engine.root_module:
            self.module_path.insert(0, parent.name)
            parent = parent.parent_module

        self.states = {}
        self.states_folder = ''
        self.states_folder = '%s/states/%s' % (self.engine.folder, '/'.join(self.module_path[1:]) if self != Engine.INSTANCE else '')
        for file in glob.glob('%s/*.json' % self.states_folder):
            state_name = file.split('/')[-1].rpartition('.')[0]
            self.load(state_name, preload=True)

        Sequencer.__init__(self, 'module/' + '/'.join(self.module_path))

    @public_method
    def add_submodule(self, *modules):
        """
        add_submodule(*modules)

        Add a submodule.

        Submodule's protocol and port can be omitted, in which case
        they will be inherited from their parent.

        A submodule can send messages but it will not receive messages through
        its route method.

        The submodule's parent instance must be provided in its constructor
        function (`parent` argument).

        **Parameters**

        - `modules`: Module objects (one module per argument)
        """
        for module in modules:
            if module.parent_module != self:
                self.logger.critical('incorrect value for argument "parent" of submodule "%s".' % module.name)
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
        - `address`: osc address of parameter. Can be `None` if the parameter should not send any message.
        - `types`: osc typetags string, one letter per value, including static values
        (character '*' can be used for arguments that should not be explicitely typed)
        - `static_args`: list of static values before the ones that can be modified
        - `default`: value or list of values if the parameter has multiple dynamic values
        """
        if name not in self.parameters:
            self.parameters[name] = Parameter(name, address, types, static_args, default)
            self.reset(name)
        else:
            self.logger.error('could not add parameter "%s" (parameter already exists)' % name)

    @public_method
    def remove_parameter(self, name):
        """
        remove_parameter(name)

        Remove parameter from module.

        **Parameters**

        - `name`: name of parameter, '*' to delete all parameters
        """
        if name == '*':
            for name in list(self.parameters.keys()):
                self.remove_parameter(name)
            return
        if name in self.parameters:
            del self.parameters[name]
        if name in self.meta_parameters:
            del self.meta_parameters[name]
        if name in self.animations:
            self.animations.remove(name)

    @public_method
    @force_mainthread
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
            self.logger.error('get: parameter or submodule "%s" not found' % name)

    @submodule_method(pattern_matching=False)
    def has(self, *args):
        """
        has(parameter_name)
        has(submodule_name, param_name)

        Check if module has parameter

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule

        **Return**

        `True` if module
        """
        name = args[0]
        return name in self.parameters

    @public_method
    @force_mainthread
    @submodule_method(pattern_matching=True)
    def set(self, *args, force_send=False, preserve_animation=False):
        """
        set(parameter_name, *args, force_send=False, preserve_animation=False)
        set(submodule_name, param_nam, *args, force_send=False, preserve_animation=False)

        Set value of parameter.

        The engine will apply the new value only at the end of current processing cycle
        and send a message if the new value differs from the one that was previously sent.

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule, with wildcard ('*') and range ('[]') support
        - `*args`: value(s)
        - `force_send`: send a message regardless of the last sent value
        - `preserve_animation`: by default, animations are automatically stopped when `set()` is called, set
        to `True` to prevent that
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            if parameter.animate_running and not preserve_animation:
                parameter.stop_animation()

            if force_send and parameter.address:
                parameter.set(*args[1:])
                self.send(parameter.address, *parameter.get_message_args())
                parameter.set_last_sent()

            else:

                if parameter.set(*args[1:]) and not parameter.dirty:
                    parameter.dirty = True
                    self.dirty_parameters.put(parameter)
                    self.set_dirty()

        else:
            self.logger.error('set: parameter or submodule "%s" not found' % name)

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
    @force_mainthread
    @submodule_method(pattern_matching=True)
    def animate(self, *args, **kwargs):
        """
        animate(parameter_name, start, end, duration, mode='beats', easing='linear', loop=False)
        animate(submodule_name, parameter_name, start, end, duration, mode='beats', easing='linear', loop=False)

        Animate parameter.

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule, with wildcard ('*') and range ('[]') support
        - `start`: starting value(s), can be None to use current value (only for single value parameters)
        - `end`: ending value(s), can be None to use current value (only for single value parameters)
        - `duration`: animation duration
        - `mode`: 'seconds' or 'beats'
        - `easing`: easing function name.
            - available easings: linear, sine, quadratic, cubic, quartic, quintic, exponential, random, elastic (sinc)
            - easing name can be suffixed with `-mirror` (back and forth animation)
            - easing name can be suffixed with `-out` (inverted and flipped easing) or `-inout` (linear interpolation between default and `-out`). Example: `exponential-mirror-inout`.
        - `loop`: if set to `True`, the animation will start over when `duration` is reached (use mirror easing for back-and-forth loop)
        """
        name = args[0]

        if name in self.parameters:

            parameter = self.parameters[name]
            parameter.start_animation(self.engine, *args[1:], **kwargs)
            if parameter.animate_running:
                if name not in self.animations:
                    self.animations.append(name)
                self.set_animating()
        else:
            self.logger.error('animate: parameter or submodule "%s" not found' % name)

    @public_method
    @force_mainthread
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
                if parameter.update_animation(self.engine.current_time) and not parameter.dirty:
                    parameter.dirty = True
                    self.dirty_parameters.put(parameter)
                    self.set_dirty()
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
            list of parameters involved in the meta parameter's definition. Each item in the list can be either:
            - `string`: a parameter name
            - `list`: one or multiple submodule names and one parameter name (`['submodule_name', 'parameter_name']`) if the parameter is owned by a submodule
        - `getter`:
            callback function that will be called with the values of each
            `parameters` as arguments whenever one these parameters changes.
            Its return value will define the meta parameter's value.
        - `setter`:
            callback function used to set the value of each `parameters`when when `set()` is called to change the meta parameter's value.
            The function's signature must not use *args or **kwargs arguments.
        """
        if name not in self.parameters:
            meta_parameter = MetaParameter(name, parameters, getter, setter, module=self)
            self.meta_parameters[name] = meta_parameter
            self.parameters[name] = meta_parameter
            for p in meta_parameter.parameters:
                # avoid updating meta parameter the first time if
                # dependencies don't exist they may be not ready yet
                if not self.has(*p):
                    return
            self.update_meta_parameter(name)
        else:
            self.logger.error('could not add meta parameter "%s" (parameter already exists)' % name)

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
        if self.parent_module is not None:
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

    @public_method
    def add_alias_parameter(self, name, parameter):
        """
        add_alias_parameter(name, parameter)

        Add a special parameter that just mirrors another parameter owned by the module or its submodules.
        Under the hood, this creates a meta parameter with the simplest getter and setters possible.

        **Parameters**

        - `name`: name of alias parameter
        - `parameter`:
            name of parameter to mirror, may a be list if the parameter are owned by a submodule (`['submodule_name', 'parameter_name']`)
        """
        getter = lambda val: val
        if type(parameter) is list:
            setter = lambda val: self.set(*parameter, val)
        else:
            setter = lambda val: self.set(parameter, val)

        self.add_meta_parameter(name, parameter, getter, setter)

    @public_method
    def get_state(self, omit_defaults=False):
        """
        get_state()

        Get state of all parameters and submodules' parameters.

        **Parameters**

        - `omit_defaults`: set to `True` to only retreive parameters that differ from their default values.

        **Return**

        List of lists that can be fed to set()
        """
        state = []

        for name in self.parameters:

            val = self.parameters[name].get()

            if omit_defaults and val == self.parameters[name].default:
                continue

            if type(val) is list:
                state.append([name, *val])
            else:
                state.append([name, val])

        for name in self.submodules:

            sstate = self.submodules[name].get_state(omit_defaults)
            state = state + [[name] + x for x in sstate]

        return state

    @public_method
    def set_state(self, state, force_send=False):
        """
        set_state(state)

        Set state of any number of parameters and submodules' parameters.

        **Parameters**

        - `state`: state object as returned by `get_state()`
        - `force_send`: see `set()`
        """
        for data in state:
            if type(data) == list:
                self.set(*data, force_send=force_send)

    @public_method
    def send_state(self):
        """
        send_state()

        Send current state of all parameters and submodules' parameters.
        """
        self.set_state(self.get_state(), force_send=True)

    @public_method
    def save(self, name, omit_defaults=False):
        """
        save(name, omit_defaults=False)

        Save current state (including submodules) to a JSON file.

        **Parameters**

        - `name`: name of state save (without file extension)
        - `omit_defaults`: set to `True` to only save parameters that differ from their default values.
        """
        file = '%s/%s.json' % (self.states_folder, name)
        self.states[name] = self.get_state(omit_defaults)
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
    def load(self, name, force_send=False, preload=False):
        """
        load(name, force_send=False)

        Load state from memory or from file if not preloaded already.
        The file must be valid a JSON file containing one list of lists as returned by `get_state()`.
        Comments may be added manually by inserting string items in the main list:
        ```
        [
            "This is a comment",
            ["parameter_a", 1.0],
            ["parameter_b", 2.0],
            "etc"
        ]
        ```

        **Parameters**

        - `name`: name of state save (without file extension)
        - `force_send`: see `set()`
        """
        if name not in self.states and preload:

            file = '%s/%s.json' % (self.states_folder, name)

            try:
                f = open(file)

                try:
                    self.states[name] = json.loads(f.read())
                except Exception as e:
                    self.logger.info('failed to parse state file "%s"\n%s' % (file, e))
                finally:
                    f.close()

            except Exception as e:
                self.logger.info('failed to open state file "%s"\n%s' % (file, e))

            self.logger.info('state "%s" preloaded from %s' % (name, file))

        if not preload:

            if name in self.states:
                try:
                    self.set_state(self.states[name], force_send=force_send)
                    self.logger.info('state "%s" loaded' % name)
                except Exception as e:
                    self.logger.info('failed to load state "%s"\n%s' % (name, e))
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


    def set_animating(self):
        """
        Tell parent module we have animating parameters
        """
        if self not in self.engine.animating_modules:
            self.engine.animating_modules.append(self)


    def set_dirty(self):
        """
        Tell parent module we have dirty parameters
        """
        if not self.dirty:
            self.dirty = True
            self.engine.dirty_modules.put(self)

    def update_dirty_parameters(self):
        """
        update_dirty_parameters()

        Apply parameters' pending values and send messages if they changed.
        """
        while not self.dirty_parameters.empty():
            parameter = self.dirty_parameters.get()
            if parameter.should_send():
                if parameter.address:
                    self.send(parameter.address, *parameter.get_message_args())
                parameter.set_last_sent()
                self.engine.dispatch_event('parameter_changed', self, parameter.name, parameter.get())
                self.check_meta_parameters(parameter.name)
            parameter.dirty = False

        self.dirty = False

    @public_method
    def send(self, address, *args):
        """
        send(address, *args)

        Send message to the module's port.

        **Parameters**

        - `address`: osc address
        - `*args`: values, or (typetag, value) tuples
        """
        proto = self.protocol
        port = self.port

        if not port and self.parent_module:
            proto = self.parent_module.protocol
            port = self.parent_module.port

        if port:
            message = [proto, port, address, *args]
            self.engine.message_queue.put(message)

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
        - `engine_route_changed`: emitted when the engine's active route changes
            - `name`: name of active route
        - `parameter_changed`: emitted when a module's parameter changes. Arguments:
            - `module`: instance of module that emitted the event
            - `name`: name of parameter
            - `value`: value of parameter or list of values

        """

        self.engine.register_event_callback(event, callback)
