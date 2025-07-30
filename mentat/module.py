"""
Module class
"""

import inspect
import time
import glob
import json
import pathlib
import re
import logging
from queue import Queue

from typing import TYPE_CHECKING

from .utils import public_method, force_mainthread, submodule_method, type_callback
from .parameter import Parameter, MetaParameter, Mapping
from .sequencer import Sequencer
from .eventemitter import EventEmitter

class Module(Sequencer, EventEmitter):
    """
    Interface between a software / hardware and the engine.

    **Instance properties**

    - `engine`: Engine instance
    - `logger`: python logger
    - `name`: module name
    - `parent_module`: parent module instance, `None` if the module is not a submodule
    - `module_path`: list of module names, from topmost parent (engine) to submodule
    - `submodules`: `dict` containing submodules added to the module with names as keys
    - `parameters`: `dict` containing parameters added to the module with names as keys
    - `meta_parameters`: `dict` containing meta parameters added to the module with names as keys

    **Events**

    - `module_added`: emitted when a submodule is added to a module. Arguments:
        - `module`: instance of parent module
        - `submodule`: instace of child module
    - `parameter_added`: emitted when a parameter is added to a module. Arguments:
        - `module`: instance of module that emitted the event
        - `name`: name of parameter
    - `parameter_changed`: emitted when a module's parameter changes. Arguments:
        - `module`: instance of module that emitted the event
        - `name`: name of parameter
        - `value`: value of parameter or list of values
    """
    if TYPE_CHECKING:
        from .engine import Engine
        engine: Engine

    @public_method
    def __init__(self,
                 name: str,
                 protocol: str|None = None,
                 port: int|str|None = None,
                 parent: 'Module|None' = None):
        """
        Module(name, protocol=None, port=None, parent=None)

        Base Module constructor.

        **Parameters**

        - `name`: module name
        - `protocol`: 'osc', 'osc.tcp', 'osc.unix' or 'midi'
        - `port`: port used by the software / hardware to send and receive messages
            - port number if protocol is 'osc' or 'osc.tcp', or liblo url for non-local host
              (e.g. 'osc.udp://192.168.1.2:6666')
            - unix socket path if protocol is 'osc.unix' (e.g. '/tmp/mysocket')
            - `None` if protocol is 'midi' or if no port is needed
        - `parent`:
            when a module is instanciated it needs to know of its parent module right away
            in order to be initialized correctly. If omitted it will default to the calling
            module (ie when the module is instanciated from another module's method or directly in a call to `add_submodule()`) or to
            the engine instance.

        **Notes**

        - 'osc.tcp' protocol should be avoided (as of now the sender's port can't be
        determined when using tcp, thus breaking Mentat's Module<->Software relationship
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
            self.logger.critical('the engine must be created before any module')
        else:
            self.engine = Engine.INSTANCE
        if self != Engine.INSTANCE and parent is None:
            parent = Engine.INSTANCE
            # attempt to retreive parent module automatically
            # for submodules instanciated in their parent's methods
            frames = inspect.getouterframes(inspect.currentframe())[1:]
            for i,f in enumerate(frames):
                f_locals = f[0].f_locals
                if i == 0:
                    # one liner mod.add_submodule(Module())
                    # -> retreive "mod" value in context
                    oneliner_found = False
                    for line in f.code_context:
                        if '.add_submodule' in line:
                            modvar = line.split('.add_submodule')[0].strip()
                            if modvar in f[0].f_locals:
                                parent = f_locals[modvar]
                                oneliner_found = True
                                break
                # otherwise, retreive first "self" found in the stack
                if not oneliner_found and 'self' in f_locals and isinstance(f_locals['self'], Module) and f_locals['self'] != self:
                    parent = f_locals['self']
                    break


        self.parent_module = parent

        self.protocol = protocol
        if self != Engine.INSTANCE:
            if protocol == 'midi':
                self.port = name
            else:
                if type(port) is str and '://' in port and port[-1] != '/':
                    # append slash to port-as-url to match liblo's url scheme
                    port = port + '/'
                self.port = port

        self.parameters = {}
        self.animations = []
        self.meta_parameters = {}
        self.mappings = []
        self.mappings_srcs_map = []
        self.mappings_need_sorting = False

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

        if self != Engine.INSTANCE:
            state_path = '/'.join(self.module_path[1:])
            self.states_folder = f'{self.engine.folder}/states/{state_path}'

        for file in glob.glob(f'{self.states_folder}/*.json'):
            state_name = file.split('/')[-1].rpartition('.')[0]
            self.load(state_name, preload=True)

        Sequencer.__init__(self, 'module/' + '/'.join(self.module_path))
        EventEmitter.__init__(self)


    def __repr__(self):
        return f'{self.__class__.__name__}("{self.name}")'


    @public_method
    def add_submodule(self, *modules: 'Module'):
        """
        add_submodule(*modules)

        Add a submodule.

        Submodule's protocol and port can be omitted, in which case
        they will be inherited from their parent.

        A submodule can send messages but it will not receive messages through
        its route method.

        Will throw a critical error if the submodule's parent (see constructor) does
        not match the module calling this method.

        **Parameters**

        - `modules`: Module objects (one module per argument)
        """
        for module in modules:
            if module.parent_module != self:
                self.logger.critical(f'parent module mismatch for submodule {module} (added to {self}, initialized with parent={module.parent_module})')
            self.submodules[module.name] = module
            if module.protocol is None:
                module.protocol = self.protocol
            if module.port is None:
                module.port = self.port
            module.parent_module = self
            self.dispatch_event('module_added', self, module)

    @public_method
    def set_aliases(self, aliases: dict[str, str]):
        """
        set_aliases(aliases)

        Set aliases for submodules.
        Aliases can be used in place of the submodule_name argument in some methods.

        **Parameters**

        - `aliases`: {alias: name} dictionary
        """
        self.aliases = aliases

    @public_method
    def add_parameter(self,
                      name: str,
                      address: str|None,
                      types: str,
                      static_args: list|None = None,
                      default = None,
                      transform: type_callback = None,
                      **metadata):
        """
        add_parameter(name, address, types, static_args=[], default=None, transform=None)

        Add parameter to module.

        **Parameters**

        - `name`: name of parameter
        - `address`: osc address of parameter (`None` if the parameter should not send any message)
        - `types`: osc typetags string, one letter per value, including static values
        (character '*' can be used for arguments that should not be explicitely typed)
        - `static_args`: list of static values before the ones that can be modified
        - `default`: value or list of values if the parameter has multiple dynamic values
        - `transform`:
            function that takes one argument per parameter value (excluding static args)
            and returns a list or tuple of values, it is called whenever the parameter's value
            is set (right before type casting) and its result will be used as the new value.
            This may be used to apply custom roundings or boundaries.
        - `metadata`:
            extra keyword arguments will are stored in parameter.metadata (dict), this can
            be used to store custom informations (range, min, max) for unspecified usages

        **Return**

        Parameter object or None if parameter already exists
        """
        if name not in self.parameters:
            self.parameters[name] = Parameter(name, address, types, static_args, default, transform, **metadata)
            self.reset(name)
            self.dispatch_event('parameter_added', self, name)
            return self.parameters[name]
        else:
            self.logger.error(f'could not add parameter "{name}" (parameter already exists)')
            return None

    @public_method
    def remove_parameter(self, name: str):
        """
        remove_parameter(name)

        Remove parameter from module.

        **Parameters**

        - `name`: name of parameter, '*' to delete all parameters
        """
        if name == '*':
            for param in list(self.parameters.keys()):
                self.remove_parameter(param)
            return
        if name in self.parameters:
            del self.parameters[name]
        if name in self.meta_parameters:
            del self.meta_parameters[name]
        if name in self.animations:
            self.animations.remove(name)

    @public_method
    @submodule_method(pattern_matching=False)
    def get(self, parameter_name: str, *args):
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
        if parameter_name in self.parameters:
            return self.parameters[parameter_name].get()

        else:
            self.logger.error(f'get: parameter or submodule "{parameter_name}" not found')
            return None

    @public_method
    @submodule_method(pattern_matching=False)
    def get_parameter(self, *args):
        """
        get_parameter(parameter_name)
        get_parameter(submodule_name, param_name)

        Check if module has parameter and return it.

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule

        **Return**

        Parameter object or None
        """
        name = args[0]
        return self.parameters[name] if name in self.parameters else None

    @public_method
    @force_mainthread
    @submodule_method(pattern_matching=True)
    def set(self,
            parameter_name: str,
            *args,
            force_send: bool = False,
            preserve_animation: bool = False) -> None:
        """
        set(parameter_name, *args, force_send=False, preserve_animation=False)
        set(submodule_name, parameter_name, *args, force_send=False, preserve_animation=False)

        Set value of parameter.

        The engine will trigger events related to the value change only at the end of current
        processing cycle and send a message if the new value differs from the one that was
        previously sent.

        When in a scene, subsequent calls to `set()` are not guaranteed to be executed
        within the same processing cycle. (see `lock()`)

        **Parameters**

        - `parameter_name`: name of parameter
        - `submodule_name`: name of submodule, with wildcard ('*') and range ('[]') support
        - `*args`: value(s)
        - `force_send`: send a message even if the parameter's value has not changed
        - `preserve_animation`: by default, animations are automatically stopped when `set()` is called, set
        to `True` to prevent that
        """

        if parameter_name in self.parameters:

            parameter = self.parameters[parameter_name]
            if parameter.animate_running and not preserve_animation:
                parameter.stop_animation()

            parameter_changed = parameter.set(*args)

            if parameter_changed and not parameter.dirty:
                parameter.dirty = True
                parameter.dirty_timestamp = time.time()
                self.dirty_parameters.put(parameter)
                self.set_dirty()

            elif force_send and parameter.address:
                self.send(parameter.address, *parameter.get_message_args(), timestamp=time.time())
                parameter.set_last_sent()



        else:
            self.logger.error(f'set: parameter or submodule "{parameter_name}" not found')

    @public_method
    @force_mainthread
    @submodule_method(pattern_matching=True)
    def reset(self, parameter_name: str|None = None, *args):
        """
        reset(parameter_name=None)
        reset(submodule_name, parameter_name=None)

        Reset parameter to its default values.

        **Parameters**

        - `submodule_name`: name of submodule, with wildcard ('*') and range ('[]') support
        - `parameter_name`: name of parameter. If omitted, affects all parameters including submodules'
        """
        if parameter_name is None:
            for sname in self.submodules:
                self.submodules[sname].reset()
            for param in self.parameters:
                self.reset(param)

        elif parameter_name in self.parameters:
            if (default := self.parameters[parameter_name].default) is not None:
                if isinstance(default, list):
                    self.set(parameter_name, *default)
                else:
                    self.set(parameter_name, default)


    @public_method
    @force_mainthread
    @submodule_method(pattern_matching=True)
    def animate(self, parameter_name: str, *args, **kwargs):
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
        if parameter_name in self.parameters:

            parameter = self.parameters[parameter_name]
            parameter.start_animation(self.engine, *args, **kwargs)
            if parameter.animate_running:
                if parameter_name not in self.animations:
                    self.animations.append(parameter_name)
                self.set_animating()
        else:
            self.logger.error(f'animate: parameter or submodule "{parameter_name}" not found')

    @public_method
    @force_mainthread
    @submodule_method(pattern_matching=False)
    def stop_animate(self, parameter_name: str, *args):
        """
        stop_animate(parameter_name)
        stop_animate(submodule_name, param_name)

        Stop parameter animation.

        **Parameters**

        - `parameter_name`: name of parameter, can be '*' to stop all animations including submodules'.
        - `submodule_name`: name of submodule
        """

        if parameter_name == '*':

            for sname in self.submodules:
                self.submodules[sname].stop_animation('*')
            for name in self.animations:
                self.parameters[name].stop_animation()

        elif parameter_name in self.animations:

            self.parameters[parameter_name].stop_animation()


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
                    parameter.dirty_timestamp = time.time()
                    self.dirty_parameters.put(parameter)
                    self.set_dirty()
            else:
                self.animations.remove(name)


    @public_method
    def add_mapping(self,
                    src: str|tuple[str, ...]|list[str|tuple[str, ...], ...],
                    dest: str|tuple[str, ...]|list[str|tuple[str, ...], ...],
                    transform: type_callback,
                    inverse: type_callback|None = None,
                    condition: type_callback|None = None):
        """
        add_mapping(src, dest, transform, inverse=None)

        Add a value mapping between two or more parameters owned by
        the module or one of its submodules. Whenever a value change
        occurs in one of the source parameters, `transform` will be
        called and its result will be dispatched to the destination parameters.

        **Parameters**

        - `src`:
            source parameter(s), can be
            - `string` if there's only one source parameter owned
            by the module itself
            - `tuple` of `string` if the source parameter is owned
            by a submodule  (e.g. `('submodule_name', 'parameter_name')`)
            - `list` containing either of the above if there are multiple
            source parameters.
        - `dest`:
            destination parameter(s), see `src`
        - `transform`:
            function that takes one argument per source parameter and
            returns a value for the destination parameters or a list if
            there are multiple destination parameters.
        - `inverse`:
            same as `transform` but for updating source parameters when
            destination parameters update. If `transform` and `inverse`
            are inconsistent (e.g. `transform(inverse(x)) != x`), mappings
            will not trigger each others indefinetely (a mapping cannot
            run twice during a cycle).
        - `condition`:
            condition parameter, disables the mapping if False / falsy, can be
            - `string` if there's only one source parameter owned
            by the module itself
            - `tuple` of `string` if the source parameter is owned
            by a submodule  (e.g. `('submodule_name', 'parameter_name')`)

        """
        mapping = Mapping(src, dest, transform, condition)
        self.mappings.append(mapping)
        if inverse is not None:
            self.add_mapping(dest, src, inverse, None, condition)
        else:
            self.mappings_need_sorting = True
        for p in mapping.src + mapping.dest:
            # avoid updating mapping the first time if
            # dependencies don't exist they may be not ready yet
            if self.get_parameter(*p) is None:
                return

        self.update_mapping(mapping)

    def check_mappings(self, updated_parameter):
        """
        check_mappings(updated_parameter)

        Update mappings in which updated parameter is involved.

        **Parameters**

        - `updated_parameter`: parameter name, may be a list if owned by a submodule.
        """
        if self.mappings:
            if self.mappings_need_sorting:
                self.mappings_need_sorting = False
                # create a dict of (param_path,) vs list of mappings that depend on them
                # to later avoid looping over all mappings when a parameter updates
                self.mappings_srcs_map = {}
                for m in self.mappings:
                    for s in m.src:
                        if s not in self.mappings_srcs_map:
                            self.mappings_srcs_map[s] = []
                        self.mappings_srcs_map[s].append(m)
                # sort mappings (see Mapping.__lt__)
                for s in self.mappings_srcs_map:
                    self.mappings_srcs_map[s].sort()

            tuple_param = tuple(updated_parameter) if type(updated_parameter) is list else (updated_parameter,)
            if tuple_param in self.mappings_srcs_map:
                for mapping in self.mappings_srcs_map[tuple_param]:
                    # if mapping.match(updated_parameter):
                    self.update_mapping(mapping)

        if self.meta_parameters:
            for name in self.meta_parameters:
                if self.meta_parameters[name].match(updated_parameter):
                    self.update_meta_parameter(name)

        # pass mapping update to parent module
        if self.parent_module is not None:
            if not isinstance(updated_parameter, list):
                updated_parameter = [updated_parameter]
            updated_parameter.insert(0, self.name)
            self.parent_module.check_mappings(updated_parameter)

    def update_mapping(self, mapping):
        """
        update_mapping(mapping)

        Update parameter mapping. Execute transform function with
        source parameters' values as arguments and set destination
        parameters to returned values.

        """
        if mapping.lock():

            src_params = mapping.src
            condition = True
            if mapping.has_condition:
                condition = bool(self.get(*src_params[-1]))
                src_params= src_params[0:-1]

            if condition is True:

                src_values = [self.get(*param) for param in src_params]
                dest_values = mapping.transform(*src_values)

                animating = False
                for param in src_params:
                    # preserve animation if src parameter is animating
                    if self.get_parameter(*param).animate_running is not None:
                        animating = True
                        break

                if mapping.n_args == 1:
                    dest_values = [dest_values]
                for i in range(mapping.n_args):
                    val = dest_values[i]
                    param = mapping.dest[i]
                    if isinstance(val, list):
                        self.set(*param, *val, preserve_animation=animating)
                    else:
                        self.set(*param, val, preserve_animation=animating)

            if not self.dirty:
                mapping.unlock()

    @public_method
    def add_meta_parameter(self,
                           name: str,
                           parameters: str|tuple[str, ...]|list[str|tuple[str, ...], ...],
                           getter: type_callback,
                           setter: type_callback):
        """
        add_meta_parameter(name, parameters, getter, setter)

        Add a special parameter whose value depends on the state of one
        or several parameters owned by the module or its submodules.

        **Parameters**

        - `name`: name of meta parameter
        - `parameters`:
            parameters involved in the meta parameter's definition, can be
            - `string` if there's only one source parameter owned
            by the module itself
            - `tuple` of `string` if the source parameter is owned
            by a submodule  (e.g. `('submodule_name', 'parameter_name')`)
            - `list` containing either of the above if there are multiple
            source parameters.
        - `getter`:
            callback function that will be called with the values of each
            `parameters` as arguments whenever one these parameters changes.
            Its return value will define the meta parameter's value.
        - `setter`:
            callback function used to set the value of each `parameters` when `set()` is called to change the meta parameter's value.
            The function's signature must not use *args or **kwargs arguments.
        """
        if name not in self.parameters:
            meta_parameter = MetaParameter(name, parameters, getter, setter, module=self)
            self.meta_parameters[name] = meta_parameter
            self.parameters[name] = meta_parameter
            for p in meta_parameter.parameters:
                # avoid updating meta parameter the first time if
                # dependencies don't exist they may be not ready yet
                if self.get_parameter(*p) is None:
                    return
            self.update_meta_parameter(name)
            self.dispatch_event('parameter_added', self, name)
        else:
            self.logger.error(f'could not add meta parameter "{name}" (parameter already exists)')

    def update_meta_parameter(self, name):
        """
        update_meta_parameter(name)

        Update meta parameter state and emit appropriate event if it changed.

        **Parameters**

        - `name`: name of meta parameter
        """
        if self.meta_parameters[name].update():
            self.dispatch_event('parameter_changed', self, name, self.meta_parameters[name].get())


    @public_method
    def add_alias_parameter(self, name: str, parameter: str):
        """
        add_alias_parameter(name, parameter)

        Add a special parameter that just mirrors another parameter owned by the module or its submodules.
        Under the hood, this creates a parameter and a 1:1 mapping between them.

        **Parameters**

        - `name`: name of alias parameter
        - `parameter`:
            name of parameter to mirror, may a be tuple if the parameter are owned by a submodule (`('submodule_name', 'parameter_name')`)
        """
        if not isinstance(parameter, tuple):
            parameter = (parameter,)
        if (p := self.get_parameter(*parameter)) is None:
            self.logger.error(f'could not create alias parameter {name} for {parameter} (parameter doesn\'t exist)')
            return
        elif self.get_parameter(name) is not None:
            self.logger.error(f'could not create alias parameter {name} for {parameter} (parameter {name} already exists)')
            return
        else:
            self.parameters[name] = Parameter(name, address=None, types=p.types[-p.n_args-1:], static_args=[], default=None)
            if p.n_args == 1:
                self.parameters[name].set(p.get())
            else:
                self.parameters[name].set(*p.get())
            self.add_mapping(parameter, name, lambda x: x, lambda y: y)
            self.dispatch_event('parameter_added', self, name)

    @public_method
    def get_state(self, omit_defaults: bool = False) -> list[list, ...]:
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

            if isinstance(val, list):
                state.append([name, *val])
            else:
                state.append([name, val])

        for name in self.submodules:

            sstate = self.submodules[name].get_state(omit_defaults)
            state = state + [[name] + x for x in sstate]

        return state

    @public_method
    @force_mainthread
    def set_state(self, state: list[list, ...], force_send: bool = False):
        """
        set_state(state)

        Set state of any number of parameters and submodules' parameters.

        **Parameters**

        - `state`: state object as returned by `get_state()`
        - `force_send`: see `set()`
        """
        for data in state:
            if isinstance(data, list):
                self.set(*data, force_send=force_send)

    @public_method
    def send_state(self):
        """
        send_state()

        Send current state of all parameters and submodules' parameters.
        """
        self.set_state(self.get_state(), force_send=True)

    @public_method
    def save(self, name: str, omit_defaults: bool = False):
        """
        save(name, omit_defaults=False)

        Save current state (including submodules) to a JSON file.

        **Parameters**

        - `name`: name of state save (without file extension)
        - `omit_defaults`: set to `True` to only save parameters that differ from their default values.
        """
        file = f'{self.states_folder}/{name}.json'
        self.states[name] = self.get_state(omit_defaults)
        pathlib.Path(self.states_folder).mkdir(parents=True, exist_ok=True)
        with open(file, 'w') as f:
            s = json.dumps(self.states[name], indent=2)
            s = re.sub(r'\n\s\s\s\s', ' ', s)
            s = re.sub(r'\n\s\s(\],?)', r'\1', s)
            s = re.sub(r'\s\s\[\s', '  [', s)
            f.write(s)

        self.logger.info(f'state "{name}" saved to {file}')

    @public_method
    def load(self, name: str, force_send: bool = False, preload: bool = False):
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

            file = f'{self.states_folder}/{name}.json'

            try:
                f = open(file)

                try:
                    self.states[name] = json.loads(f.read())
                except Exception as e:
                    self.logger.info(f'failed to parse state file "{file}"\n{e}')
                finally:
                    f.close()

            except Exception as e:
                self.logger.erro(f'failed to open state file "{file}"\n{e}')

            self.logger.info(f'state "{name}" preloaded from {file}')

        if not preload:

            if name in self.states:
                try:
                    self.set_state(self.states[name], force_send=force_send)
                    self.logger.info(f'state "{name}" loaded')
                except Exception as e:
                    self.logger.error(f'failed to load state "{name}"\n{e}')
            else:
                self.logger.error(f'state "{name}" not found')

    @public_method
    def delete(self, name: str):
        """
        delete(name)

        Delete state and associated JSON file.

        **Parameters**

        - `name`: name of state save (without file extension)
        """
        if name in self.states:
            del self.states[name]
            try:
                pathlib.Path.unlink(f'{self.states_folder}/{name}.json')
            except Exception as e:
                self.logger.error(f'failed to delete state file "{self.states_folder}/{name}.json"\n{e}')
        else:
            self.logger.error(f'state "{name}" not found')

    @public_method
    def route(self, address: str, args: list):
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
                    self.send(parameter.address, *parameter.get_message_args(), timestamp=parameter.dirty_timestamp)
                parameter.set_last_sent()
                self.dispatch_event('parameter_changed', self, parameter.name, parameter.get())
                self.check_mappings(parameter.name)
            parameter.dirty = False
        for mapping in self.mappings:
            mapping.unlock()

        self.dirty = False

    @public_method
    def send(self, address: str, *args, timestamp=0):
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
            # timestamp is used to preserve the sending order between
            # parameter changes and direct calls to send()
            message = [time.time() if timestamp == 0 else timestamp, proto, port, address, *args]
            self.engine.message_queue.put(message)
