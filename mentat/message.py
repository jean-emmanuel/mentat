class Message():

    def __init__(self, protocol, port, address, *args):
        """
        Message(protocol, module, address, *args)
        Message(protocol, port, address, *args)

        OSC / MIDI Message constructor

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp' or 'midi'
        - `module`: module name
        - `port`: port number if protocol is 'osc' or 'osc.tcp'
        - `address`: osc address
        - `*args`: values
        """
        self.protocol = protocol
        self.port = port
        self.address = address
        self.args = args
