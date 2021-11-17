class Message():

    def __init__(self, protocol, port, address, *args):
        """
        Message(protocol, module, address, *args)
        Message(protocol, port, address, *args)

        OSC / MIDI Message constructor

        **Parameters**

        - `protocol`: 'osc' or 'midi'
        - `module`: module name
        - `port`: udp port number or osc.unix:// socket path if protocol is 'osc'
        - `address`: osc address
        - `*args`: values
        """
        self.protocol = protocol
        self.port = port
        self.address = address
        self.args = args
