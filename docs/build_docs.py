from sys import path
path.insert(0, '../')

from mentat import Engine, Module, Parameter, Route

from inspect import getmembers, getdoc, signature, getsourcelines
import re

docs = """

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

"""

for mod in [Engine, Module, Parameter, Route]:

    # docs += "## Engine\n\n"
    docs += "## %s\n\n" % mod.__name__

    methods = []
    for name, obj in getmembers(mod):
        if hasattr(obj, '_public_method'):
            source, start_line = getsourcelines(obj)
            methods.append([name, obj, start_line])
    methods.sort(key = lambda v: v[2])

    for name, method, _ in methods:
        # sig = "%s`" % signature(method)
        if name == '__init__':
            name = mod.__name__
            docs += "### %s()\n\n" % (mod.__name__)
        else:
            docs += "### %s.%s()\n\n" % (mod.__name__, name)

        docs += "<div class='content'>\n\n"
        mdoc = getdoc(method)

        mdoc = re.sub("(%s\\(.*\\))" % name, r'<i>\1</i>', mdoc)

        # docs += "<i>zdzef</i>"
        docs += mdoc
        docs += "\n\n"
        docs += "</div>\n\n"


    docs += "----\n\n"

print(docs)
