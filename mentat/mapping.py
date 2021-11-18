from .parameter import Parameter

class Mapping(Parameter):

    def __init__(self, name, parameters, types, getter, setter, module):

        super().__init__(name, address='', types=types)

        self.module = module
        self.parameters = [[x] if type(x) is not list else x for x in parameters]
        self.getter = getter
        self.setter = setter
        self.value = None

    def set(self, *args):
        value = self.get()
        self.setter(*args)
        if value != self.get():
            return True

    def update(self):
        values = [self.module.get(*x) for x in self.parameters]
        value = self.getter(*values)
        if type(value) is list:
            return Parameter.set(self, *value)
        else:
            return Parameter.set(self, value)
