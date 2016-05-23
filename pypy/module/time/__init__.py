
from pypy.interpreter.mixedmodule import MixedModule
from .interp_time import CLOCK_CONSTANTS, HAS_CLOCK_GETTIME, cConfig
import os

_WIN = os.name == "nt"

class Module(MixedModule):
    applevel_name = 'time'

    interpleveldefs = {
        'time': 'interp_time.time',
        'clock': 'interp_time.clock',
        'ctime': 'interp_time.ctime',
        'asctime': 'interp_time.asctime',
        'gmtime': 'interp_time.gmtime',
        'localtime': 'interp_time.localtime',
        'mktime': 'interp_time.mktime',
        'strftime': 'interp_time.strftime',
        'sleep' : 'interp_time.sleep',
        '_STRUCT_TM_ITEMS': 'space.wrap(interp_time._STRUCT_TM_ITEMS)',
        'monotonic': 'interp_time.monotonic',
        'perf_counter': 'interp_time.perf_counter',
        'process_time': 'interp_time.process_time',
    }

    if HAS_CLOCK_GETTIME:
        interpleveldefs['clock_gettime'] = 'interp_time.clock_gettime'
        interpleveldefs['clock_settime'] = 'interp_time.clock_settime'
        interpleveldefs['clock_getres'] = 'interp_time.clock_getres'
    if os.name == "posix":
        interpleveldefs['tzset'] = 'interp_time.tzset'

    for constant in CLOCK_CONSTANTS:
        value = getattr(cConfig, constant)
        if value is not None:
            interpleveldefs[constant] = 'space.wrap(interp_time.cConfig.%s)' % constant

    appleveldefs = {
        'struct_time': 'app_time.struct_time',
        '__doc__': 'app_time.__doc__',
        'strptime': 'app_time.strptime',
        'get_clock_info': 'app_time.get_clock_info'
    }

    def startup(self, space):
        if _WIN:
            from pypy.module.time.interp_time import State
            space.fromcache(State).startup(space)

        # this machinery is needed to expose constants
        # that have to be initialized one time only
        from pypy.module.time import interp_time

        interp_time._init_timezone(space)

