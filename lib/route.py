class Route():

    def __init__(self, name):
        """
        Route()

        Route object constructor.
        """
        self.engine = None
        self.name = name

    def initialize(self, engine):
        """
        initialize()

        Called by the engine when started.
        """
        self.engine = engine

    def activate(self):
        """
        activate()

        Called when the engine switches to this route.
        """
        pass

    def deactivate(self):
        """
        deactivate()

        Called when the engine switches to another route.
        """
        self.stop_scene('*')

    def route(self, protocol, port, address, args):
        """
        route(protocol, port, address, args)

        Process messages received by the engine.

        :param protocol: 'osc' or 'midi'
        :param port: name of module or port number if unknown
        :param address: osc address
        :param args: list of values
        """
        pass

    def start_scene(self, name, scene, *args, **kwargs):
        """
        scene(scene)

        Start scene in a thread.
        If a scene with the same name is already running, it will be stopped.
        Scenes should be implemented as methods of the Route object and
        can call self.wait() to create timed sequences or loops.

        :param name: scene name
        :param scene: function or method
        :param *args: arguments for the scene function
        :param *kwargs: keyword arguments for the scene function
        """
        self.stop_scene('/route/%s/%s' % (self.name, name))
        self.engine.start_scene('/route/%s/%s' % (self.name, name), scene, *args, **kwargs)

    def stop_scene(self, name):
        """
        scene(scene)

        Stop scene thread.

        :param name: scene name, with wildcard support
        :param scene: function or method
        """
        self.engine.stop_scene('/route/%s/%s' % (self.name, name))

    def wait(self, duration, mode='beat'):
        """
        wait(duration, mode)

        Wait for given amount of time. Can only called in scenes.
        Subsequent calls to wait() in a scene do not drift with time
        and can be safely used to create beat sequences. Example:
        beat_1()
        self.wait(1, 'b') # will wait 1 beat minus beat_1's exec time
        beat_2()
        self.wait(1, 'b') # will wait 1 beat minus beat_1 and beat_2's exec time


        :param duration: amount of time to wait
        :param mode: 'beats' or 'seconds' (only the first letter matters)
        """
        timer = self.engine.get_scene_timer()
        if timer:
            timer.wait(duration, mode)
