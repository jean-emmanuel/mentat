class Message():

    def __init__(self, protocol, port, address, *args):
        """
        Message(protocol, module, address, *args)
        Message(protocol, port, address, *args)

        OSC / MIDI Message constructor

        :param protocol: 'osc' or 'midi'
        :param module: module name
        :param port: udp port number or osc.unix:// socket path if protocol is 'osc'
        :param address: osc address
        :param *args: values
        """
        self.protocol = protocol
        self.port = port
        self.address = address
        self.args = args
