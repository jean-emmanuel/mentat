## Mentat

<div class="version">
Version: 1.0.0-alpha (WORK IN PROGRESS)
</div>

### Overview

Mentat is a HUB / Conductor for OSC / MIDI capable softwares. It aims to centralize all controls in one place, manage their state and create routings.

Mentat is a module for [python 3](https://www.python.org/) and requires writing code to work. If you're looking for a fully-featured software with a user interface, try [Chateigne](https://benjamin.kuperberg.fr/chataigne/en) instead.

### Install

```
git clone https://github.com/jean-emmanuel/mentat/
cd mentat
python3 setup.py install
```

### Usage

The typical use case for Mentat is a conductor for controlling a set of softwares during a live performance.

The [`Engine`](#engine) object is the main object, it manages the OSC / MIDI backends, the modules and the routes. It also holds a tempo, a cycle length (measure) and a time reference that's used to create timed scenes and sequences in a musical way (using beats instead of seconds).

[`Module`](#module) objects are interfaces between the controlled softwares and the engine. The `Module` class should be subclassed to
create dedicated module classes for different softwares.

A set of controllable parameters can be defined for each module, each parameter being an alias for an OSC / MIDI value in the controlled software.

Controlled parameters should only modified using the module's [`set()`](#module.set) and [`animate()`](#module.animate) methods in order to guarantee that the state of the modules reflects the actual state of the softwares. This removes the need for feedback from said softwares and allows us to trust Mentat as the source of truth during the performance.

All messages received by the engine that are coming from a software associated with a module are first passed to that module's  [`route()`](#module.route) method.

[`Route`](#route) objects represent the different parts of the performance (eg tracks / songs in a musical show). The `Engine` has one active route at a time and will pass all incoming messages to its [`route()`](#route.route) method.

Each track should be a dedicated class derived from the `Route` class. The [`route()`](#route.route) method definition will allow writing
the actual routing that should occur during that track.

----
