class Light():

    def part(self, *args, **kwargs):

        super().part(*args, **kwargs)

        print('trackA light route:', args)


    def route(self, protocol, port, address, args):
        """
        Need additional message routing ?
        Don't forget to call super().route()
        when overriding the method
        """
        super().route(protocol, port, address, args)

        print('trackA light direct routing')
