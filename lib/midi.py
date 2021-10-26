import rtmidi
from rtmidi.midiconstants import *

MIDI_TO_OSC = {
    NOTE_ON: '/note_on',
    NOTE_OFF: '/note_off',
    CONTROL_CHANGE: '/control_change',
    PROGRAM_CHANGE: '/program_change',
    PITCH_BEND: '/pitch_bend',
    SYSTEM_EXCLUSIVE: '/sysex',
    CHANNEL_PRESSURE: '/channel_pressure',
    POLY_PRESSURE: '/key_pressure'
}

OSC_TO_MIDI = {
    '/note_on': NOTE_ON,
    '/note_off': NOTE_OFF,
    '/control_change': CONTROL_CHANGE,
    '/program_change': PROGRAM_CHANGE,
    '/pitch_bend': PITCH_BEND,
    '/sysex': SYSTEM_EXCLUSIVE,
    '/channel_pressure': CHANNEL_PRESSURE,
    '/key_pressure': POLY_PRESSURE
}

def midi_to_osc(message):
    mtype = message[0] & 0xF0

    if mtype not in MIDI_TO_OSC:
        return None

    osc = {}
    osc['address'] = MIDI_TO_OSC[mtype]

    if mtype == PROGRAM_CHANGE:
         # convert  0-127 pair -> 0-16384
        message = message[:1] + [message[1] + message[2] * 128]

    osc['args'] = message[1:]

    return osc

def osc_to_midi(address, args):

    if address not in OSC_TO_MIDI:
        return None

    message = []
    mtype = OSC_TO_MIDI[address]

    if mtype == SYSTEM_EXCLUSIVE:
        message = [int(arg) & 0x7F for arg in args]
    else:
        if mtype == PITCH_BEND:
            # convert 0-16384 -> 0-127 pair
            args = args[:1] + [args[1] & 0x7F, (args[1] >> 7) & 0x7F]

        channel = args[0]

        # status
        message.append((mtype & 0xF0) | (channel - 1 & 0x0F))

        # data 1
        if len(args) > 1:
            message.append(args[1] & 0x7F)

            # data 2
            if len(args) > 2:
                message.append(args[2] & 0x7F)

    return message
