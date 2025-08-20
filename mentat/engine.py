"""
Engine class
"""

import time
import fnmatch
import atexit
import sys
import os
import logging
import threading

from queue import Queue
from pathlib import Path
from signal import signal, SIGINT, SIGTERM
from typing import TYPE_CHECKING

import pyinotify

try:
    import pyliblo3 as liblo
except:
    import liblo

from pyalsa import alsaseq

from .config import MAINLOOP_PERIOD, MAINLOOP_PERIOD_NS, ANIMATION_PERIOD_NS
from .utils import public_method, force_mainthread
from .midi import osc_to_midi, midi_to_osc
from .thread import KillableThread as Thread
from .timer import Timer
from .module import Module

if TYPE_CHECKING:
    from .route import Route

class Engine(Module):
    """
    Main object. Singleton that must be instanciated before any `Module` or `Route` object.
    The global engine instance is always accessible via `Engine.INSTANCE`.

    The engine is also a `Module` instance and can use the methods of this class.

    **Instance properties**

    - `modules`: `dict` containing modules added to the engine with names as keys
    - `routes`: `dict` containing routes added to the engine with names as keys
    - `active_route`: active route object (`None` by default)
    - `restarted`: `True` if the engine was restarted using `autorestart()`
    - `logger`: python logger
    - `tempo`: beats per minute
    - `cycle_length`: quarter notes per cycle
    - `port`: osc (udp) input port number
    - `tcp_port`: osc (tcp) input port number
    - `unix_port`: osc (unix) input socket path

    **Events**

    - `started`: emitted when the engine starts.
    - `stopping`: emitted before the engine stops
    - `stopped`: emitted when the engine is stopped
    - `route_added`: emitted when a route is added to the engine. Arguments:
        - `route`: route instance
    - `route_changed`: emitted when the engine's active route changes. Arguments:
        - `name`: active route instance
    """

    INSTANCE = None

    @public_method
    def __init__(self,
                 name: str,
                 port: int,
                 folder: str,
                 debug: bool = False,
                 tcp_port: int|None = None,
                 unix_port: int|None = None):
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
            self.logger.critical('only one instance Engine can be created')
        else:
            Engine.INSTANCE = self

        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

        self.osc_server = None
        self.osc_tcp_server = None
        self.osc_unix_server = None

        self.osc_inputs = {'osc':{}, 'osc.tcp': {}, 'osc.unix': {}}
        self.osc_outputs = {'osc': {}, 'osc.tcp': {}, 'osc.unix': {}}

        self.midi_server = None
        self.midi_ports = {}
        self.midi_drain_pending = False
        self.midi_sync_pending = False


        self.osc_input_queue = Queue()
        self.midi_input_queue = Queue()

        self.routes = {}
        self.active_route = None

        self.scenes = {}
        self.scenes_timers = {}

        self.is_running = False
        self.is_stopping = False
        self.is_restarting = False

        self.current_time = time.monotonic_ns()
        self.cycle_start_time = self.current_time
        self.cycle_length = 4.0
        self.tempo = 120.0
        self.tempo_map = []

        self.fastforwarding = False
        self.fastforward_frametime = False
        self.fastforward_frames = 0
        self.time_offset = 0

        self.folder = Path(folder).expanduser().resolve()

        self.modules = {}

        self.dirty_modules = Queue()
        self.animating_modules = []

        self.message_queue = Queue()
        self.action_queue = Queue()

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

        self.main_loop_lock = threading.RLock()

        Module.__init__(self, name)

    def start_servers(self):
        """
        start_servers()

        Starts osc servers and open midi ports
        """

        def queue_osc(address, args, types, src):
            self.osc_input_queue.put([address, args, types, src])

        def receive_osc(server):
            while True:
                server.recv(100)

        self.osc_server = liblo.Server(self.port, proto=liblo.UDP)
        self.osc_server.add_method(None, None, queue_osc)
        self.start_scene_thread('osc_server', receive_osc, self.osc_server)

        if self.tcp_port:
            self.osc_tcp_server = liblo.Server(self.tcp_port, proto=liblo.TCP)
            self.osc_tcp_server.add_method(None, None, queue_osc)
            self.start_scene_thread('osc_tcp_server', receive_osc, self.osc_tcp_server)

        if self.unix_port:
            self.osc_unix_server = liblo.Server(self.unix_port, proto=liblo.UNIX)
            self.osc_unix_server.add_method(None, None, queue_osc)
            self.start_scene_thread('osc_unix_server', receive_osc, self.osc_unix_server)

        if self.midi_ports:
            def queue_midi():
                while self.midi_server:
                    for event in self.midi_server.receive_events():
                        self.midi_input_queue.put(event)
                    time.sleep(MAINLOOP_PERIOD)

            self.midi_server = alsaseq.Sequencer(clientname=self.name, maxreceiveevents=1024)
            for module_name in self.midi_ports:
                port_type = alsaseq.SEQ_PORT_TYPE_MIDI_GENERIC | alsaseq.SEQ_PORT_TYPE_APPLICATION
                port_caps = (alsaseq.SEQ_PORT_CAP_WRITE | alsaseq.SEQ_PORT_CAP_SUBS_WRITE |
                             alsaseq.SEQ_PORT_CAP_READ | alsaseq.SEQ_PORT_CAP_SUBS_READ)
                port_id = self.midi_server.create_simple_port(module_name, port_type, port_caps)
                self.midi_ports[module_name] = port_id
            self.midi_thread = Thread(target=queue_midi)
            self.midi_thread.start()

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

        if self.midi_server:
            self.midi_thread.kill()
            self.midi_server = None

    @public_method
    def start(self):
        """
        start()

        Start engine. This is usually the last statement in the script as
        it starts the processing loop that keeps the engine running.
        """
        if self.is_running:
            self.logger.error('already started')
            return

        if threading.main_thread() == threading.current_thread():
            signal(SIGINT, lambda a,b: self.stop())
            signal(SIGTERM, lambda a,b: self.stop())
        else:
            self.logger.warning('started in a thread')

        self.start_servers()

        self.current_time = time.monotonic_ns()
        self.cycle_start_time = self.current_time
        self.update_tempo_map()

        self.is_running = True

        if self.active_route:
            self.active_route.activate()

        last_animation = self.current_time

        self.logger.info('started')
        self.dispatch_event('started')

        while self.is_running:

            with self.main_loop_lock:

                self.current_time = time.monotonic_ns() + self.time_offset

                if self.fastforwarding:
                    self.time_offset += self.fastforward_frametime
                    self.fastforward_frames -= 1
                    if self.fastforward_frames == 0:
                        self.fastforwarding = False

                # process incoming osc messages
                while not self.osc_input_queue.empty():
                    message = self.osc_input_queue.get()
                    try:
                        self.route_osc(*message)
                    except Exception as error:
                        self.logger.error(f'an error occured while routing osc message {message}', exception=True)

                # process incoming midi messages
                while not self.midi_input_queue.empty():
                    event = self.midi_input_queue.get()
                    try:
                        self.route_midi(event)
                    except Exception as error:
                        self.logger.error(f'an error occured while routing midi event {event} {args}', exception=True)

                # update animations
                if self.current_time > last_animation + ANIMATION_PERIOD_NS - MAINLOOP_PERIOD_NS / 2:
                    last_animation += ANIMATION_PERIOD_NS
                    for mod in self.animating_modules:
                        mod.update_animations()
                        if not mod.animations:
                            self.animating_modules.remove(mod)

                # update parameters and queue messages
                while not self.dirty_modules.empty():
                    mod = self.dirty_modules.get()
                    mod.update_dirty_parameters()

                # resolve pending actions
                while not self.action_queue.empty():
                    method, _self, args, kwargs = self.action_queue.get()
                    method(_self, *args, **kwargs)

                # send pending messages
                self.flush()

                # statistics
                if self.log_statistics:
                    current_time = self.current_time - self.time_offset
                    self.statistics['exec_time'][0] = max(time.monotonic_ns() - current_time, self.statistics['exec_time'][0])
                    self.statistics['exec_time'][1] += time.monotonic_ns() - current_time
                    self.statistics['exec_time'][2] += 1
                    if self.statistics_time == 0:
                        self.statistics_time = current_time
                    if current_time - self.statistics_time >= 1000000000:
                        for stat in self.statistics:
                            if stat == 'exec_time':
                                peak_time = self.statistics['exec_time'][0] / 1000000
                                average_time = self.statistics['exec_time'][1] / self.statistics['exec_time'][2] / 1000000
                                self.logger.info(f'statistic: main loop exec time: peak {peak_time:.3f}ms, average {average_time:.3f}ms')
                                self.statistics['exec_time'] = [0, 0, 0]
                            elif self.statistics[stat] != 0:
                                self.logger.info(f'statistic: {stat}: {self.statistics[stat]} in 1s')
                                self.statistics[stat] = 0
                        self.statistics_time = current_time

                # restart ?
                if self.is_restarting:
                    self._restart()

                # take some rest
                time.sleep(MAINLOOP_PERIOD)

        self.logger.info('stopped')
        self.dispatch_event('stopped')


    @public_method
    def stop(self):
        """
        stop()

        Stop engine. This is called automatically when the process
        is terminated or when the engine restarts.
        """
        if self.is_stopping:
            self.logger.info('force quitting')
            os._exit(1)
            return
        self.is_stopping = True
        self.logger.info('stopping...')
        self.dispatch_event('stopping')
        self.is_running = False
        self.stop_scene_thread('*')
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
        self.dispatch_event('restarting')

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
        watcher = pyinotify.WatchManager()
        self.notifier = pyinotify.ThreadedNotifier(watcher)
        base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__)) # pylint: disable=no-member
        # add watches for imported modules
        for module in sys.modules.values():
            # builtin modules don't have a __file__ attribute
            if hasattr(module, '__file__') and module.__file__ is not None:
                filename = os.path.abspath(module.__file__)
                # only watch file if it's in the same directory as the main script
                # + module src files
                if filename.startswith(base_dir)  or 'mentat' in module.__name__:
                    watcher.add_watch(filename, pyinotify.IN_MODIFY, lambda event: self.restart())
        self.notifier.start()

    @public_method
    def add_module(self, module: Module):
        """
        add_module(module)

        Add a module. This method will create midi ports if the module's protocol is 'midi'.

        **Parameters**

        - `module`: Module object
        """
        if module == self:
            self.logger.critical('cannot add self as module')

        if module.name in self.modules:
            self.logger.critical(f'could not add module {module.name} (a module with this name has already been added)')

        self.modules[module.name] = module
        self.submodules[module.name] = module
        module.parent_module = self

        if module.port is not None:
            if module.protocol in ['osc', 'osc.tcp', 'osc.unix']:
                if module.port in self.osc_inputs[module.protocol]:
                    self.logger.critical(f'could not add module {module.name} (port {module.port} already used by module {self.osc_inputs[module.protocol][module.port]})')
                self.osc_inputs[module.protocol][module.port] = module.name
                self.osc_outputs[module.protocol][module.name] = module.port
            elif module.protocol == 'midi':
                self.midi_ports[module.name] = None


        self.dispatch_event('module_added', self, module)

    def add_submodule(self, *args, **kwargs):
        """
        Bypass Module.add_submodule()
        """
        self.add_module(*args, **kwargs)

    def flush(self):
        """
        flush()

        Send messages in queue.
        """
        messages = []
        while not self.message_queue.empty():
            messages.append(self.message_queue.get())
        if messages:
            # sort by timestamp
            for message in sorted(messages, key=lambda message: message[0]):
                self.send(*message[1:])

        if self.midi_drain_pending:
            try:
                self.midi_server.drain_output()
                self.midi_drain_pending = False
                self.midi_sync_pending = True
            except:
                self.logger.warning('midi pool unnavailable, trying again')
                pass

        if self.midi_sync_pending :
            self.midi_server.sync_output_queue()
            self.midi_sync_pending = False


    @public_method
    def send(self,
             protocol: str,
             port: str|int,
             address: str,
             *args,
             timestamp=0):
        """
        send(protocol, port, address, *args)

        Send OSC / MIDI message.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp', 'osc.unix' or 'midi'
        - `port`:
            module name, port number ('osc' protocol only) or
            unix socket path ('osc.unix' protocol only)
        - `address`: osc address
        - `args`: values or (typetag, value) tuples
        """
        if not self.is_running:
            # in case a module calls this method directly
            # before the server is started
            message = [time.time() if timestamp == 0 else timestamp, protocol, port, address, *args]
            self.message_queue.put(message)
            return

        if protocol in ['osc', 'osc.tcp', 'osc.unix']:

            if port in self.osc_outputs[protocol]:
                port = self.osc_outputs[protocol][port]
            if protocol == 'osc':
                self.osc_server.send(port, address, *args)
            elif protocol == 'osc.tcp':
                # liblo doesn't actually send from the tcp server and opens a random port
                if type(port) is str and '://' in port:
                    self.osc_tcp_server.send(port, address, *args)
                else:
                    self.osc_tcp_server.send('osc.tcp://127.0.0.1:%s' % port, address, *args)
            elif protocol == 'osc.unix':
                self.osc_unix_server.send('osc.unix://%s' % port, address, *args)
            else:
                return

            if self.log_statistics:
                self.statistics['osc_out'] += 1

        elif protocol == 'midi':

            if port in self.midi_ports:

                try:
                    midi_event = osc_to_midi(address, args)
                except Exception as error:
                    self.logger.error(f'failed to generate midi event {address} {args}', exception=True)
                    midi_event = None

                if midi_event:
                    midi_event.source = (self.midi_server.client_id, self.midi_ports[port])
                    self.midi_server.output_event(midi_event)
                    try:
                        self.midi_server.drain_output()
                        self.midi_drain_pending = False
                        self.midi_sync_pending = True
                    except:
                        self.midi_drain_pending = True
                        self.logger.warning('midi pool unnavailable, trying again')
                    if self.log_statistics:
                        self.statistics['midi_out'] += 1

        else:

            self.logger.error(f'unknown protocol {protocol}')

    @public_method
    def add_route(self, route: 'Route'):
        """
        add_route(route)

        Add a route.

        **Parameters**

        - `route`: Route object
        """
        self.routes[route.name] = route
        self.dispatch_event('route_added', route)

    @public_method
    @force_mainthread
    def set_route(self, name: str):
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
            self.logger.info(f'active route set to "{name}"')
            self.dispatch_event('route_changed', self.active_route)
        else:
            self.logger.error('route "{name}" not found')

    @public_method
    def route(self,
              protocol: str,
              port: str|int,
              address: str,
              args: list|tuple):
        """
        route(protocol, port, address, args)

        Unified route for osc and midi messages, called when the engine
        receives a midi or osc message. Messages are processed this way :

        1. If the message is sent from a port that matches a module's,
        the message is passed to that module's route method. If it
        returns `False`, further processing is prevented.

        2. If the address matches a command as per the generic control API,
        further processing is prevented.

        3. If a route is active, the message is passed to that route's
        route method.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp' or 'midi'
        - `port`: name of module, port number if unknown and local,
                  url if unknown and non-local
        - `address`: osc address
        - `args`: list of values
        """
        if port in self.modules:
            if self.modules[port].route(address, args) is False:
                return

        if protocol != 'midi':
            if self.route_generic_osc_api(address, args) is False:
                return

        if self.active_route:
            self.active_route.route(protocol, port, address, args)

    def route_osc(self, address, args, types, src): # pylint: disable=unused-argument
        """
        Route incoming raw osc events.
        """

        if src.protocol == liblo.TCP:
            proto = 'osc.tcp'
        elif src.protocol == liblo.UNIX:
            proto = 'osc.unix'
        else:
            proto = 'osc'

        if src.url in self.osc_inputs[proto]:
            # non-local port (by url)
            port = self.osc_inputs[proto][src.url]
        elif src.port in self.osc_inputs[proto]:
            # local port (by number or socket path)
            port = self.osc_inputs[proto][src.port]
        elif src.hostname not in ['localhost', '127.0.0.1']:
            # non-local & unknown -> url
            port = src.url
        else:
            # local & unknown -> port number
            port = src.port

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

    def route_generic_osc_api(self, address, args):
        """
        Generic OSC API: control any parameter or call any module method

        **Parameters**

        - `address`: osc address
        - `args`: list of values

        **Returns*
        `False` if a module parameter or method was reached, `True` otherwise.
        """
        module_path = address.split('/')[1:]
        module_name = module_path[0]

        if len(module_path) < 2 or module_path[0] != self.name:
            return True

        method_name = module_path[-1]
        module_path = module_path[:-1]
        module = self

        if len(module_path) > 1:
            module_name = module_path[1]
            if module_name in self.modules:
                module = self.modules[module_name]
                for name in module_path[2:]:
                    if name in module.submodules:
                        module = module.submodules[name]
                    else:
                        module = None
                        break
            else:
                module = None

        if module is not None:

            if hasattr(module, method_name):
                method = getattr(module, method_name)
                # only allow public methods and user-defined methods
                if callable(method) and (
                        hasattr(method, '_public_method') or
                        method.__qualname__.split('.')[0] not in ('Engine',
                                                                  'Module',
                                                                  'Route',
                                                                  'Sequencer')
                    ):
                    method(*args)


            return False

        else:

            return True

    def start_scene_thread(self, name, scene, *args, **kwargs):
        """
        start_scene_thread(scene)

        Start function in a thread.
        If a scene with the same name is already running, it will be stopped.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        - `*args`: arguments for the scene function
        - `*kwargs`: keyword arguments for the scene function
        """
        if self.is_stopping:
            return
        self.stop_scene_thread(name)
        self.scenes_timers[name] = Timer(self)
        self.scenes[name] = Thread(target=scene, name=name, args=args, kwargs=kwargs)
        self.scenes[name].start()
        self.logger.debug(f'starting scene {name}')

    def restart_scene_thread(self, name):
        """
        restart_scene_thread(name)

        Restart a scene that's already running.
        Does nothing if the scene is not running.

        **Parameters**

        - `name`: scene name, with wildcard support
        """
        if self.is_stopping:
            return
        if '*' in name or '[' in name:
            for match in fnmatch.filter(self.scenes.keys(), name):
                self.restart_scene_thread(match)
        elif name in self.scenes and self.scenes[name].is_alive():
            self.scenes[name].kill()
            self.scenes_timers[name].reset()
            self.scenes[name].start()
            self.logger.debug(f'restarting scene {name}')

    def stop_scene_thread(self, name):
        """
        stop_scene_thread(scene)

        Stop scene thread.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        """
        if '*' in name or '[' in name:
            for match in fnmatch.filter(self.scenes.keys(), name):
                self.stop_scene_thread(match)
        elif name in self.scenes:
            if self.scenes[name].is_alive():
                self.logger.debug(f'stopping scene {name}')
                self.scenes[name].kill()
            else:
                self.logger.debug(f'cleaning scene {name}')
            del self.scenes[name]
            del self.scenes_timers[name]

    def is_scene_thread(self):
        """
        is_scene_threa()

        Return True if we are in a scene
        """
        return Thread.get_current().name in self.scenes_timers

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

    def get_main_loop_lock(self):
        """
        get_main_loop_lock()

        Return main loop lock

        **Return**

        threading.RLock instance
        """
        name = Thread.get_current().name
        if name in self.scenes_timers:
            return self.main_loop_lock
        else:
            self.logger.error('cannot call lock() from main thread')
            # return cheap no-op context
            return memoryview(b'')

    @public_method
    def set_tempo(self, bpm: int|float):
        """
        set_tempo(bpm)

        Set engine tempo.

        **Parameters**

        - `bpm`: beats per minute
        """
        if bpm != self.tempo:
            self.tempo = max(float(bpm), 0.001)
            self.update_tempo_map()
            for name in self.scenes_timers:
                self.scenes_timers[name].update_tempo()

    def update_tempo_map(self):
        """
        update_tempo_map(self)

        Update inner tempo map to keep track of tempo/cycle_length changes over time
        """
        self.tempo_map.append([self.current_time, self.tempo, self.cycle_length])


    @public_method
    def set_cycle_length(self, quarter_notes: int|float):
        """
        set_cycle_length(quarter_notes)

        Set engine cycle (measure) length in quarter notes.

        **Parameters**

        - `quarter_notes`: quarter notes per cycle (decimals allowed)
        """
        if quarter_notes != self.cycle_length:
            self.cycle_length = float(quarter_notes)
            self.update_tempo_map()

    def time_signature_to_quarter_notes(self, signature):
        """
        Convert time signature string to quarter notes.
        """
        beats, unit = signature.split('/')
        mutliplier = 4 / float(unit)
        return float(beats) * mutliplier

    @public_method
    def set_time_signature(self, signature: str):
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
        self.tempo_map = []
        self.update_tempo_map()

    @public_method
    def fastforward(self, duration: int|float, mode: str = 'beats'):
        """
        fastforward(amount, mode='beats')

        `/!\\ Experimental /!\\`

        Increment current time by a number of beats or seconds.
        All parameter animations and wait() calls will be affected.

        **Parameters**

        - `duration`: number of beats or seconds
        - `mode`: 'beats' or 'seconds' (only the first letter matters)
        """
        if type(duration) not in (int, float) or duration <= 0:
            self.logger.error('fastforward: duration must be a positive number')
            return
        if self.fastforwarding:
            self.logger.error('fastforward: already busy')
            return


        if mode[0] == 'b':
            duration = duration * 60. / self.tempo
            duration *= 1000000000 # s to ns
        elif mode[0] == 's':
            duration *= 1000000000 # s to ns

        self.fastforward_frames = 100
        self.fastforward_frametime = duration / self.fastforward_frames
        self.fastforwarding = True
