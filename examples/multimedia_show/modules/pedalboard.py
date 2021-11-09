from mentat.module import Module

class Pedalboard(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.watch_module('klick-1', '*')

    def watched_module_changed(self, module_path, name, args):

        self.send("/" + "/".join(module_path), *args)

        print(self.name, module_path, name, args)

    def route(self, address, args):

        module_path = address.split('/')[1:]
        
        self.engine.modules[module_path[0]].set(*module_path[:1], *args)
