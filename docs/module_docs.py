from sys import path
path.insert(0, '../')

from mentat import Engine, Module, Route
from mentat.logger import Logger

from inspect import getmembers, getdoc, signature, getsourcelines
import re

docs = ""

for mod in [Engine, Module, Route]:

    # docs += "## Engine\n\n"
    docs += "## %s\n\n" % mod.__name__

    methods = []
    for name, obj in getmembers(mod):
        if hasattr(obj, '_public_method'):
            source, start_line = getsourcelines(obj)
            if obj.__qualname__.split('.')[0] == 'Sequencer':
                start_line += 10000
            elif obj.__qualname__.split('.')[0] == 'Logger':
                start_line += 20000
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

        mdoc = re.sub("^(%s\\(.*\\))" % name, r'<i>\1</i><br/>', mdoc, flags=re.MULTILINE)

        # docs += "<i>zdzef</i>"
        docs += mdoc
        docs += "\n\n"
        docs += "</div>\n\n"


    docs += "----\n\n"

print(docs)
