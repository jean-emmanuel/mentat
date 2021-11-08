from mentat.module import Module

class Pedalboard(Module):

    def __init__(self, *args, **kwargs):

        Module.__init__(self, *args, **kwargs)

        self.watch_module('klick-1', '*')

    def watched_module_changed(self, module_path, name, args):
        print(self.name, module_path, name, args)

    def route(self, address, args):
        pass
