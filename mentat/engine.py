import time
import liblo
import queue
import fnmatch
import atexit
import sys
import os
import pyinotify
import logging
import threading
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
    Main object. Singleton that must be instanciated before any `Module` or `Route` object.
    The global engine instance is always accessible via `Engine.INSTANCE`.

    **Instance properties**

    - `modules`: `dict` containing modules added to the engine with names as keys
    - `routes`: `dict` containing routes added to the engine with names as keys
    - `active_route`: active route object (`None` by default)
    - `restarted`: `True` if the engine was restarted using `autorestart()`
    - `logger`: python logger
    - `root_module`:
            module instance that exposes all modules added to the engine.
            Allows reaching toplevel module's parameters by name with `set()`, `animate()`,
            and creating meta parameters with multiple modules.
    - `tempo`: beats per minute
    - `cycle_length`: quarter notes per cycle
    """

    INSTANCE = None

    @public_method
    def __init__(self, name, port, folder, debug=False, tcp_port=None, unix_port=None):
        """
        Engine(name, port, folder, debug=False, tcp_port=None, unix_port=None)

        Engine constructor.

        **Parameters**

        - `name`: client name
        - `port`: osc (udp) input port number
        - `folder`: path to config folder where state files will be saved to and loaded from
        - `debug`: set to True to enable debug messages and i/o statistics
        - `tcp_port`: osc (tcp) input port number
        - `unix_port`: osc (unix) input socket path
        """
        self.logger = logging.getLogger(__name__).getChild(name)
        self.name = name

        self.port = port
        self.tcp_port = tcp_port
        self.unix_port = unix_port

        if Engine.INSTANCE is not None:
            self.logger.error('only one instance Engine can be created')
            raise Exception
        else:
            Engine.INSTANCE = self
            from .module import Module

        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

        self.osc_server = None
        self.osc_tcp_server = None
        self.osc_unix_server = None

        self.osc_inputs = {'osc':{}, 'osc.tcp': {}, 'osc.unix': {}}
        self.osc_outputs = {'osc': {}, 'osc.tcp': {}, 'osc.unix': {}}

        self.midi_server = None
        self.midi_ports = {}

        self.routes = {}
        self.active_route = None

        self.scenes = {}
        self.scenes_timers = {}

        self.is_running = False
        self.is_restarting = False

        self.current_time = time.monotonic_ns()
        self.cycle_start_time = self.current_time
        self.cycle_length = 4
        self.tempo = 120

        self.folder = folder

        self.root_module = Module(self.name)
        self.modules = {}
        self.event_callbacks = {}
        self.queue = Queue()

        self.dirty_modules = Queue()
        self.animating_modules = []

        self.lock = threading.Lock()

        self.notifier = None
        self.restarted = os.getenv('MENTAT_RESTART') is not None

        self.log_statistics = debug
        self.statistics_time = 0
        self.statistics = {
            'midi_in': 0,
            'midi_out': 0,
            'osc_in': 0,
            'osc_out': 0,
            'exec_time': [0, 0, 0] # max, total, iterations
        }

    def start_servers(self):
        """
        start_servers()

        Starts osc servers and open midi ports
        """

        self.osc_server = liblo.Server(self.port, proto=liblo.UDP)
        self.osc_server.add_method(None, None, self.route_osc)

        if self.tcp_port:
            self.osc_tcp_server = liblo.Server(self.tcp_port, proto=liblo.TCP)
            self.osc_tcp_server.add_method(None, None, self.route_osc)

        if self.unix_port:
            self.osc_unix_server = liblo.Server(self.unix_port, proto=liblo.UNIX)
            self.osc_unix_server.add_method(None, None, self.route_osc)

        self.midi_server = alsaseq.Sequencer(clientname=self.name)
        for module_name in self.midi_ports:
            self.midi_ports[module_name] = self.midi_server.create_simple_port(module_name, alsaseq.SEQ_PORT_TYPE_MIDI_GENERIC | alsaseq.SEQ_PORT_TYPE_APPLICATION, alsaseq.SEQ_PORT_CAP_WRITE | alsaseq.SEQ_PORT_CAP_SUBS_WRITE | alsaseq.SEQ_PORT_CAP_READ | alsaseq.SEQ_PORT_CAP_SUBS_READ)

    def stop_servers(self):
        """
        stop_servers()

        Stop osc servers and close midi ports
        """

        if self.osc_server:
            self.osc_server.free()
            self.osc_server = None

        if self.osc_tcp_server:
            self.osc_tcp_server.free()
            self.osc_tcp_server = None

        if self.osc_unix_server:
            self.osc_unix_server.free()
            self.osc_unix_server = None

        self.midi_server = None

    def poll_servers(self):
        """
        poll_servers()

        Process incoming osc and midi messages
        """
        # process osc messages
        while self.osc_server and self.osc_server.recv(0):
            pass
        while self.osc_tcp_server and self.osc_tcp_server.recv(0):
            pass
        while self.osc_unix_server and self.osc_unix_server.recv(0):
            pass

        # process midi messages
        midi_events = self.midi_server.receive_events()
        for e in midi_events:
            self.route_midi(e)

    @public_method
    def start(self):
        """
        start()

        Start engine. This is usually the last statement in the script as
        it starts the processing loop that keeps the engine running.
        """

        signal(SIGINT, lambda a,b: self.stop())
        signal(SIGTERM, lambda a,b: self.stop())

        self.start_servers()

        if self.active_route:
            self.active_route.activate()

        self.is_running = True

        last_animation = 0
        animation_period = ANIMATION_PERIOD * 1000000

        self.logger.info('started')
        self.dispatch_event('engine_started')

        while self.is_running:

            self.current_time = time.monotonic_ns()

            self.poll_servers()

            # update animations
            if self.current_time - last_animation >= ANIMATION_PERIOD:
                last_animation = self.current_time
                with self.lock:
                    for mod in self.animating_modules:
                        mod.update_animations()

            # update parameters and queue messages
            while not self.dirty_modules.empty():
                mod = self.dirty_modules.get()
                mod.update_dirty_parameters()

            # send pending messages
            self.flush()

            # statistics
            if self.log_statistics:
                self.statistics['exec_time'][0] = max(time.monotonic_ns() - self.current_time, self.statistics['exec_time'][0])
                self.statistics['exec_time'][1] += time.monotonic_ns() - self.current_time
                self.statistics['exec_time'][2] += 1
                if self.statistics_time == 0:
                    self.statistics_time = self.current_time
                if self.current_time - self.statistics_time >= 1000000000:
                    for stat in self.statistics:
                        if stat == 'exec_time':
                            peak_time = self.statistics['exec_time'][0] / 1000000
                            average_time = self.statistics['exec_time'][1] / self.statistics['exec_time'][2] / 1000000
                            self.logger.info('statistic: main loop exec time: peak %.3fms, average %.3fms' % (peak_time, average_time))
                            self.statistics['exec_time'] = [0, 0, 0]
                        elif self.statistics[stat] != 0:
                            self.logger.info('statistic: %s: %i in 1s' % (stat, self.statistics[stat]))
                            self.statistics[stat] = 0
                    self.statistics_time = self.current_time

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

        Stop engine. This is called automatically when the process
        is terminated or when the engine restarts.
        """

        self.logger.info('stopping...')
        self.dispatch_event('engine_stopping')
        self.is_running = False
        self.stop_scene('*')
        self.stop_servers()
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

        Enable engine autorestart. This watches the main python script
        and all imported modules that are located in the same directoty.
        Whenever a file is modified, the engine is restarted.
        """
        wm = pyinotify.WatchManager()
        self.notifier = pyinotify.ThreadedNotifier(wm)
        base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
        # add watches for imported modules
        for m in sys.modules.values():
            # builtin modules don't have a __file__ attribute
            if hasattr(m, '__file__') and m.__file__ is not None:
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
            if module.protocol in ['osc', 'osc.tcp', 'osc.unix']:
                self.osc_inputs[module.protocol][module.port] = module.name
                self.osc_outputs[module.protocol][module.name] = module.port
            elif module.protocol == 'midi':
                self.midi_ports[module.name] = None

    def flush(self):
        """
        flush()

        Send messages in queue.
        """
        if self.is_running:

            while not self.queue.empty():
                message = self.queue.get()
                self.send(*message)

            self.midi_server.sync_output_queue()

    @public_method
    def send(self, protocol, port, address, *args):
        """
        send(protocol, port, address, *args)

        Send OSC / MIDI message.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp', 'osc.unix' or 'midi'
        - `port`:
            module name, port number ('osc' protocol only) or unix socket path ('osc.unix' protocol only)
        - `address`: osc address
        - `args`: values
        """
        if not self.is_running:
            # in case a module calls this method directly
            # before the server is started
            message = [proto, port, address, *args]
            self.queue.put(message)
            return

        if protocol in ['osc', 'osc.tcp', 'osc.unix']:

            if port in self.osc_outputs[protocol]:
                port = self.osc_outputs[protocol][port]
            if protocol == 'osc':
                self.osc_server.send(port, address, *args)
            elif protocol == 'osc.tcp':
                self.osc_tcp_server.send(port, address, *args)
            elif protocol == 'osc.unix':
                self.osc_unix_server.send(port, address, *args)
            else:
                return

            if self.log_statistics:
                self.statistics['osc_out'] += 1

        elif protocol == 'midi':

            if port in self.midi_ports:

                midi_event = osc_to_midi(address, args)
                if midi_event:
                    midi_event.source = (self.midi_server.client_id, self.midi_ports[port])
                    self.midi_server.output_event(midi_event)
                    self.midi_server.drain_output()
                    if self.log_statistics:
                        self.statistics['midi_out'] += 1

        else:

            self.logger.error('unknown protocol %s' % protocol)

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

    @public_method
    def route(self, protocol, port, address, args):
        """
        route(protocol, port, address, args)

        Unified route for osc and midi messages, called when the engine
        receives a midi or osc message.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp' or 'midi'
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
        proto = 'osc'
        port = src.port
        if src.protocol == liblo.TCP:
            proto = 'osc.tcp'
        elif src.protocol == liblo.UNIX:
            proto = 'osc.unix'
        if src.port in self.osc_inputs[proto]:
            port = self.osc_inputs[proto][src.port]
        self.route(proto, port, address, args)
        if self.log_statistics:
            self.statistics['osc_in'] += 1

    def route_midi(self, event):
        """
        Route incoming raw midi events.
        """
        port = self.midi_server.get_port_info(event.dest[1],event.dest[0])['name']
        osc_message = midi_to_osc(event)
        if osc_message:
            osc_message['port'] = port
            self.route('midi', port, osc_message['address'], osc_message['args'])
            if self.log_statistics:
                self.statistics['midi_in'] += 1

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
        self.logger.debug('starting scene %s' % name)

    def restart_scene(self, name):
        """
        restart_scene(name)

        Restart a scene that's already running.
        Does nothing if the scene is not running.

        **Parameters**

        - `name`: scene name, with wildcard support
        """
        if '*' in name or '[' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.restart_scene(n)
        elif name in self.scenes and self.scenes[name].is_alive():
            self.scenes[name].kill()
            self.scenes_timers[name].reset()
            self.scenes[name].start()
            self.logger.debug('restarting scene %s' % name)

    def stop_scene(self, name):
        """
        scene(scene)

        Stop scene thread.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        """
        if '*' in name or '[' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.stop_scene(n)
        elif name in self.scenes:
            if self.scenes[name].is_alive():
                self.logger.debug('stopping scene %s' % name)
                self.scenes[name].kill()
            else:
                self.logger.debug('cleaning scene %s' % name)
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
    def set_cycle_length(self, quarter_notes):
        """
        set_cycle_length(quarter_notes)

        Set engine cycle (measure) length in quarter notes.

        **Parameters**

        - `quarter_notes`: quarter notes per cycle (decimals allowed)
        """
        self.cycle_length = float(quarter_notes)

    def time_signature_to_quarter_notes(self, signature):
        """
        Convert time signature string to quarter notes.
        """
        beats, unit = signature.split('/')
        mutliplier = 4 / float(unit)
        return float(beats) * mutliplier

    @public_method
    def set_time_signature(self, signature):
        """
        set_time_signature(signature)

        Set engine cycle (measure) length from a musical time signature.

        **Parameters**

        - `signature`: `string` like '4/4', '5/4', '7/8'...
        """
        self.set_cycle_length(self.time_signature_to_quarter_notes(signature))

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
