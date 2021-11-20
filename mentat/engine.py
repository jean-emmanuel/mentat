import time
import liblo
import queue
import fnmatch
import atexit
import sys
import os
import pyinotify
import logging
from pyalsa import alsaseq
from signal import signal, SIGINT, SIGTERM
from queue import Queue

from .config import *
from .utils import *
from .midi import osc_to_midi, midi_to_osc
from .thread import KillableThread as Thread
from .timer import Timer

class Engine():
    """
    Main object. Singleton that must be instanciated before any Module or Route object.
    The global engine instance is always accessigne via `Engine.INSTANCE`.

    **Instance properties**

    - `modules`: `dict` containing modules added to the engine with names as keys
    - `restarted`: `True` if the engine was restarted using `autorestart()`
    - `logger`: python logger
    - `root_module`:
            module instance that exposes all modules added to the engine
            Allows reaching toplevel module's parameters by name with `set()`, `animate()`,
            and creating meta parameters that with multiple modules.

    """

    INSTANCE = None

    @public_method
    def __init__(self, name, port, folder, debug=False):
        """
        Engine(name, port, folder)

        Engine constructor.

        **Parameters**

        - `name`: client name
        - `port`: osc input port, can be an udp port number or a unix socket path
        - `folder`: path to config folder where state files will be saved to and loaded from
        - `debug`: set to True to enable debug messages
        """
        self.logger = logging.getLogger(__name__).getChild(name)
        self.name = name

        if Engine.INSTANCE is not None:
            self.logger.error('only one instance Engine can be created')
            raise Exception
        else:
            Engine.INSTANCE = self
            from .module import Module

        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

        self.osc_server = liblo.Server(port)
        self.osc_server.add_method(None, None, self.route_osc)
        self.osc_inputs = {}
        self.osc_outputs = {}

        self.midi_server = alsaseq.Sequencer(clientname=self.name)
        self.midi_ports = {}

        self.routes = {}
        self.active_route = None

        self.scenes = {}
        self.scenes_timers = {}

        self.is_running = False
        self.is_restarting = False

        self.current_time = time.monotonic_ns()
        self.cycle_start_time = self.current_time
        self.cycle_length = 8
        self.tempo = 120

        self.folder = folder

        self.root_module = Module(self.name)
        self.modules = {}
        self.event_callbacks = {}
        self.queue = Queue()

        self.notifier = None
        self.restarted = os.getenv('MENTAT_RESTART') is not None

    @public_method
    def start(self):
        """
        start()

        Start engine.
        """

        signal(SIGINT, lambda a,b: self.stop())
        signal(SIGTERM, lambda a,b: self.stop())

        if self.active_route:
            self.active_route.activate()

        self.is_running = True

        last_animation = 0
        animation_period = ANIMATION_PERIOD * 1000000

        self.logger.info('started')
        self.dispatch_event('engine_started')

        while self.is_running:

            self.current_time = time.monotonic_ns()

            # process osc messages
            while self.osc_server and self.osc_server.recv(0):
                pass

            # process midi messages
            midi_events = self.midi_server.receive_events()
            for e in midi_events:
                self.route_midi(e)

            # update animations
            if self.current_time - last_animation >= ANIMATION_PERIOD:
                last_animation = self.current_time
                for name in self.modules:
                    self.modules[name].update_animations()

            # send pending messages
            self.flush()

            # restart ?
            if self.is_restarting:
                self._restart()

            # take some rest
            time.sleep(MAINLOOP_PERIOD)

        self.logger.info('stopped')
        self.dispatch_event('engine_stopped')


    @public_method
    def stop(self):
        """
        stop()

        Stop engine.
        """

        self.logger.info('stopping...')
        self.dispatch_event('engine_stopping')
        self.is_running = False
        self.stop_scene('*')
        if self.osc_server:
            self.osc_server.free()
            self.osc_server = None
        if self.notifier:
            try:
                self.notifier.stop()
                self.notifier = None
            except:
                pass

    @public_method
    def restart(self):
        """
        restart()

        Stop the engine and restart once the process is terminated.
        """
        self.is_restarting = True
        self.logger.info('restarting...')

    def _restart(self):
        def restart_python():
            os.environ['MENTAT_RESTART'] = '1'
            os.execl(sys.executable, sys.executable, *sys.argv)
        atexit.register(restart_python)
        self.stop()

    @public_method
    def autorestart(self):
        """
        autorestart()

        Watch main script and imported modules and call restart when they change.
        """
        wm = pyinotify.WatchManager()
        self.notifier = pyinotify.ThreadedNotifier(wm)
        base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
        # add watches for imported modules
        for m in sys.modules.values():
            # builtin modules don't have a __file__ attribute
            if hasattr(m, '__file__'):
                f = os.path.abspath(m.__file__)
                # only watch file if it's in the same directory as the main script
                # + module src files
                if f.startswith(base_dir)  or 'mentat' in m.__name__:
                    wm.add_watch(f, pyinotify.IN_MODIFY, lambda e: self.restart())
        self.notifier.start()

    @public_method
    def add_module(self, module):
        """
        add_module(module)

        Add a module. This method will create midi ports if the module's protocol is 'midi'.
        Modules added with this method will be children of the engine's root module instance.

        **Parameters**

        - `module`: Module object
        """
        self.modules[module.name] = module
        module.parent_module = self.root_module
        self.root_module.add_submodule(module)

        if module.port is not None:
            if module.protocol == 'osc':
                self.osc_inputs[module.port] = module.name
                self.osc_outputs[module.name] = module.port
            elif module.protocol == 'midi':
                self.midi_ports[module.name] = self.midi_server.create_simple_port(module.name, alsaseq.SEQ_PORT_TYPE_MIDI_GENERIC | alsaseq.SEQ_PORT_TYPE_APPLICATION, alsaseq.SEQ_PORT_CAP_WRITE | alsaseq.SEQ_PORT_CAP_SUBS_WRITE | alsaseq.SEQ_PORT_CAP_READ | alsaseq.SEQ_PORT_CAP_SUBS_READ)

    def flush(self):
        """
        flush()

        Send messages in queue.
        """
        while not self.queue.empty():
            message = self.queue.get()
            self.send(message.protocol, message.port, message.address, *message.args)

        self.midi_server.sync_output_queue()

    @public_method
    def send(self, protocol, port, address, *args):
        """
        send(protocol, port, address, *args)

        Send OSC / MIDI message.

        **Parameters**

        - `protocol`: 'osc' or 'midi'
        - `port`:
            module name or udp port number or unix socket path if protocol is 'osc'
        - `address`: osc address
        - `args`: values
        """
        if protocol == 'osc':

            if port in self.osc_outputs:
                port = self.osc_outputs[port]

            self.osc_server.send(port, address, *args)

        elif protocol == 'midi':

            if port in self.midi_ports:

                midi_event = osc_to_midi(address, args)
                if midi_event:
                    midi_event.source = (self.midi_server.client_id, self.midi_ports[port])
                    self.midi_server.output_event(midi_event)
                    self.midi_server.drain_output()

    @public_method
    def add_route(self, route):
        """
        add_route(route)

        Add a route.

        **Parameters**

        - `route`: Route object
        """
        self.routes[route.name] = route

    @public_method
    def set_route(self, name):
        """
        set_route(name)

        Set active route.

        **Parameters**

        - `name`: route name
        """
        if name in self.routes:
            if self.active_route and self.is_running:
                self.active_route.deactivate()
            self.active_route = self.routes[name]
            if self.is_running:
                self.active_route.activate()
            self.logger.info('active route set to "%s"' % name)
        else:
            self.logger.error('route "%s" not found' % name)

    def route(self, protocol, port, address, args):
        """
        route(protocol, port, address, args)

        Unified route for osc and midi messages.

        **Parameters**

        - `protocol`: 'osc' or 'midi'
        - `port`: name of module or port number if unknown
        - `address`: osc address
        - `args`: list of values
        """
        if port in self.modules:
            if self.modules[port].route(address, args) == False:
                return

        if self.active_route:
            self.active_route.route(protocol, port, address, args)

    def route_osc(self, address, args, types, src):
        """
        Route incoming raw osc events.
        """
        port = src.port
        if src.port in self.osc_inputs:
            port = self.osc_inputs[src.port]
        self.route('osc', port, address, args)

    def route_midi(self, event):
        """
        Route incoming raw midi events.
        """
        port = self.midi_server.get_port_info(event.dest[1],event.dest[0])['name']
        osc_message = midi_to_osc(event)
        if osc_message:
            osc_message['port'] = port
            self.route('midi', port, osc_message['address'], osc_message['args'])

    def start_scene(self, name, scene, *args, **kwargs):
        """
        scene(scene)

        Start function in a thread.
        If a scene with the same name is already running, it will be stopped.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        - `*args`: arguments for the scene function
        - `*kwargs`: keyword arguments for the scene function
        """
        self.stop_scene(name)
        self.scenes_timers[name] = Timer(self)
        self.scenes[name] = Thread(target=scene, name=name, args=args, kwargs=kwargs)
        self.scenes[name].start()
        self.logger.info('starting scene %s' % name)

    def restart_scene(self, name):
        """
        restart_scene(name)

        Restart a scene that's already running.
        Does nothing if the scene is not running.

        **Parameters**

        - `name`: scene name, with wildcard support
        """
        if '*' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.restart_scene(n)
        elif name in self.scenes and self.scenes[name].is_alive():
            self.scenes[name].kill()
            self.scenes_timers[name].reset()
            self.scenes[name].start()
            self.logger.info('restarting scene %s' % name)

    def stop_scene(self, name):
        """
        scene(scene)

        Stop scene thread.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        """
        if '*' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.stop_scene(n)
        elif name in self.scenes:
            if self.scenes[name].is_alive():
                self.logger.info('stopping scene %s' % name)
                self.scenes[name].kill()
            else:
                self.logger.info('cleaning scene %s' % name)
            id = self.scenes[name].ident
            del self.scenes[name]
            del self.scenes_timers[name]

    def get_scene_timer(self):
        """
        get_scene_timer()

        Threaded scenes each have a Timer object they can use to wait().
        Route objects can call self.wait(), but it is forbidden in the main thread.
        """
        name = Thread.get_current().name
        if name in self.scenes_timers:
            return self.scenes_timers[name]
        else:
            self.logger.error('cannot call wait() from main thread')
            return None

    @public_method
    def set_tempo(self, bpm):
        """
        set_tempo(bpm)

        Set engine tempo.

        **Parameters**

        - `bpm`: beats per minute
        """
        self.tempo = max(float(bpm), 0.001)

    @public_method
    def set_cycle_length(self, eighth_notes):
        """
        set_cycle_length(eighth_notes)

        Set engine cycle (measure) length.

        **Parameters**

        - `eighth_notes`: eighth notes per cycle
        """
        self.cycle_length = float(eighth_notes)

    @public_method
    def start_cycle(self):
        """
        start_cycle()

        Set current time as cycle start.
        Affects Route.wait_next_cycle() method.
        """
        self.cycle_start_time = self.current_time


    def add_event_callback(self, event, callback):
        """
        add_event_callback(event, callback)

        See module.add_event_callback()
        """
        if event not in self.event_callbacks:
            self.event_callbacks[event] = []
        if callback not in self.event_callbacks[event]:
            self.event_callbacks[event].append(callback)

    @public_method
    def dispatch_event(self, event, *args):
        """
        dispatch_event(event, *args)

        Dispatch event to bound callback functions.

        **Parameters**

        - `event`: name of event
        - `*args`: arguments for the callback function
        """
        if event in self.event_callbacks:
            for callback in self.event_callbacks[event]:
                callback(*args)
