

## Mentat

### Overview

`Mentat` is a HUB / Conductor for OSC / MIDI capable softwares. It aims to centralize all controls in one place, manage their state and create routings.

### Usage

The typical use case for `Mentat` a conductor for controlling a set of softwares during a live performance.

The [`Engine`](#engine) object is the main object, it manages the OSC / MIDI backends, the modules and the routes.

[`Module`](#module) objects are interfaces between the controlled softwares and the engine.
A set of controllable parameters may be defined for each module.
The `Module` class may be subclassed to create advanced modules.

[`Route`](#route) objects represent the different parts of the performance (eg tracks for a musical show).
The `Route` class should be subclassed for each track.

When the engine receives a message from a module, it does the following

- call the module's [`route()`](#module.route) method
- call the active route's [`route()`](#route.route) method.

Overriding these methods in the correponding class definitions will allow defining what should happend and when.

----

## Engine

### Engine()

<div class='content'>

<i>Engine(name, port, folder)</i><br/>

Engine constructor.

**Parameters**

- name: client name
- port: osc input port, can be an udp port number or a unix socket path
- folder: path to config folder where state files will be saved to and loaded from

</div>

### Engine.start()

<div class='content'>

<i>start()</i><br/>

Start engine.

</div>

### Engine.stop()

<div class='content'>

<i>stop()</i><br/>

Stop engine.

</div>

### Engine.restart()

<div class='content'>

<i>restart()</i><br/>

Stop the engine and restart once the process is terminated.

</div>

### Engine.autorestart()

<div class='content'>

<i>autorestart()</i><br/>

Watch main script and imported modules and call restart when they change.

</div>

### Engine.add_module()

<div class='content'>

<i>add_module(module)</i><br/>

Add a module.

**Parameters**

- module: Module object

</div>

### Engine.send()

<div class='content'>

<i>send(protocol, port, address, *args)</i><br/>

Send OSC / MIDI message.

**Parameters**

- protocol: 'osc' or 'midi'
- port:
    module name or udp port number or unix socket path if protocol is 'osc'
- address: osc address
- args: values

</div>

### Engine.add_route()

<div class='content'>

<i>add_route(route)</i><br/>

Add a route.

**Parameters**

- route: Route object

</div>

### Engine.set_route()

<div class='content'>

<i>set_route(name)</i><br/>

Set active route.

**Parameters**

- name: route name

</div>

### Engine.set_tempo()

<div class='content'>

<i>set_tempo(bpm)</i><br/>

Set engine tempo.

**Parameters**

- bpm: beats per minute

</div>

### Engine.set_cycle_length()

<div class='content'>

<i>set_cycle_length(eighth_notes)</i><br/>

Set engine cycle (measure) length.

**Parameters**

- eighth_notes: eighth notes per cycle

</div>

### Engine.start_cycle()

<div class='content'>

<i>start_cycle()</i><br/>

Set current time as cycle start.
Affects Route.wait_next_cycle() method.

</div>

----

## Module

### Module()

<div class='content'>

<i>Module(engine, name, protocol, port)</i><br/>
<i>Module(engine, name, protocol)</i><br/>
<i>Module(engine, name)</i><br/>

Base Module constructor.
Arguments protocol and port should be omitted only when the module is a submodule.

**Parameters**

- name: module name
- protocol: 'osc' or 'midi'
- port:
    udp port number or unix socket path if protocol is 'osc'
    can be None if the module has no fixed input port

</div>

### Module.initialize()

<div class='content'>

<i>initialize(engine, submodule=False)</i><br/>

Called by the engine when started.

</div>

### Module.add_submodule()

<div class='content'>

<i>add_submodule(module)</i><br/>

Add a submodule.
Submodule's protocol and port can be omitted,
they will be inherited from their parent.

**Parameters**

- module: Module object

</div>

### Module.set_aliases()

<div class='content'>

<i>set_aliases(aliases)</i><br/>

Set aliases for submodules.
Aliases can be used in place of the submodule_name argument in some methods.

**Parameters**

- aliases: {alias: name} dictionary

</div>

### Module.add_parameter()

<div class='content'>

<i>add_parameter(parameter)</i><br/>
<i>add_parameter(name, address, types, static_args=[], default=None)</i><br/>

Add parameter to module.

**Parameters**

- parameter: parameter object
- name: name of parameter
- address: osc address of parameter
- types: osc typetags string, one letter per value, including static values
- static_args: list of static values before the ones that can be modified
- default: list of values

</div>

### Module.get()

<div class='content'>

<i>get(parameter_name)</i><br/>
<i>get(submodule_name, param_name)</i><br/>

Get value of parameter

**Parameters**

- parameter_name: name of parameter
- submodule_name: name of submodule

**Return**

List of values

</div>

### Module.set()

<div class='content'>

<i>set(parameter_name, *args)</i><br/>
<i>set(submodule_name, param_nam, *args)</i><br/>

Set value of parameter.
Schedule a message if the new value differs from the one in memory.

**Parameters**

- parameter_name: name of parameter
- submodule_name: name of submodule, name of parameter
- *args: value(s)

</div>

### Module.animate()

<div class='content'>

<i>animate(parameter_name, start, end, duration, mode='seconds', easing='linear')</i><br/>
<i>animate(submodule_name, parameter_name, start, end, duration, mode='beats', easing='linear')</i><br/>

Animate parameter.

**Parameters**

- parameter_name: name of parameter
- submodule_name: name of submodule
- start: starting value(s), can be None to use currnet value
- end: ending value(s)
- duration: animation duration
- mode: 'seconds' or 'beats'
- easing: easing function name

</div>

### Module.stop_animate()

<div class='content'>

<i>stop_animate(parameter_name)</i><br/>
<i>stop_animate(submodule_name, param_name)</i><br/>

Stop parameter animation.

**Parameters**

- parameter_name: name of parameter, can be '*' to stop all animations.
- submodule_name: name of submodule, name of parameter

</div>

### Module.save()

<div class='content'>

<i>save(name)</i><br/>

Save current state (including submodules) to file.

**Parameters**

- name: name of state save (without file extension)

</div>

### Module.load()

<div class='content'>

<i>load(name)</i><br/>

Load state from memory or from file if not preloaded already

**Parameters**

- name: name of state save (without file extension)

</div>

### Module.route()

<div class='content'>

<i>route(address, args)</i><br/>

Route messages received by the engine on the module's port.
Does nothing by default, method should be overriden in subclasses.
Not called on submodules.

**Parameters**

- address: osc address
- args: list of values

</div>

### Module.send()

<div class='content'>

<i>send(address, *args)</i><br/>

Send message to the module's port.

**Parameters**

- address: osc address
- *args: values

</div>

### Module.watch_module()

<div class='content'>

<i>watch_module(module_name, param_name, callback)</i><br/>

Watch changes of a module's parameter.
Used by controller modules to collect feedback.

**Parameters**

- module_name:
    name of module This argument can be suplied multiple time if
    targetted module is a submodule
- parameter_name:
    name of parameter, can be '*' to subscribe to all parameters
    including submodules'

</div>

### Module.watched_module_changed()

<div class='content'>

<i>watched_module_changed(module_path, name, args)</i><br/>

Called when the value of a watched module's parameter updates.
To be overridden in subclasses.

**Parameters**

- module_path: list of module names (from parent to submodule)
- name: name of parameter
- args: values

</div>

----

## Parameter

### Parameter()

<div class='content'>

<i>Parameter(name, address, types, static_args=[], default=None)</i><br/>

Parameter constructor.

**Parameters**

- name: name of parameter
- address: osc address of parameter
- types: osc typetags string, one letter per value, including static values
- static_args: list of static values before the ones that can be modified
- default: list of values

</div>

### Parameter.get()

<div class='content'>

<i>get()</i><br/>

Get parameter value.

**Return**

List of n values, where n is the number of
values specified in constructor's types option

</div>

### Parameter.set()

<div class='content'>

<i>set(*args)</i><br/>

Set parameter value.

**Parameters**

- *args:
    n values, where n is the number of
    values specified in constructor's types option

**Return**

`True` is the new value differs from the old one, `False` otherwise

</div>

----

## Route

### Route()

<div class='content'>

<i>Route()</i><br/>

Route object constructor.

**Parameters**

- name: route name

</div>

### Route.initialize()

<div class='content'>

<i>initialize(engine)</i><br/>

Called by the engine when started.

**Parameters**

- engine: engine instance

</div>

### Route.activate()

<div class='content'>

<i>activate()</i><br/>

Called when the engine switches to this route.

</div>

### Route.deactivate()

<div class='content'>

<i>deactivate()</i><br/>

Called when the engine switches to another route.

</div>

### Route.route()

<div class='content'>

<i>route(protocol, port, address, args)</i><br/>

Process messages received by the engine.

**Parameters**

- protocol: 'osc' or 'midi'
- port: name of module or port number if unknown
- address: osc address
- args: list of values

</div>

### Route.start_scene()

<div class='content'>

<i>start_scene(name, scene, *args, **kwargs)</i><br/>

Start scene in a thread.
If a scene with the same name is already running, it will be stopped.
Scenes should be implemented as methods of the Route object and
can call self.wait() to create timed sequences or loops.

**Parameters**

- name: scene name
- scene: function or method
- *args: arguments for the scene function
- *kwargs: keyword arguments for the scene function

</div>

### Route.stop_scene()

<div class='content'>

<i>stop_scene(name, scene, *args, **kwargs)</i><br/>

Stop scene thread.

**Parameters**

- name: scene name, with wildcard support
- scene: function or method

</div>

### Route.wait()

<div class='content'>

<i>wait(duration, mode='beats')</i><br/>

Wait for given amount of time. Can only called in scenes.
Subsequent calls to wait() in a scene do not drift with time
and can be safely used to create beat sequences.
The engine's `tempo` must be set for the `beats` mode to work.

```
# Example
beat_1()
self.wait(1, 'b') # will wait 1 beat minus beat_1's exec time
beat_2()
self.wait(1, 'b') # will wait 1 beat minus beat_1 and beat_2's exec time
```

**Parameters**

- duration: amount of time to wait
- mode: 'beats' or 'seconds' (only the first letter matters)

</div>

### Route.wait_next_cycle()

<div class='content'>

<i>wait_next_cycle()</i><br/>

Wait until next cycle begins. The engine's `tempo` and `cycle_length`
must be set and the engine's `start_cycle()` method
must be called at the beginning of a cycle for this to work.

</div>

----


