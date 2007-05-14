"""
A simple standalone target for the prolog interpreter.
"""

import sys
from pypy.lang.prolog.interpreter.translatedmain import repl, execute

# __________  Entry point  __________

from pypy.lang.prolog.interpreter.engine import Engine
from pypy.lang.prolog.interpreter import engine, term
e = Engine()
engine.DEBUG = False
term.DEBUG = False

def entry_point(argv):
    if len(argv) == 2:
        execute(e, argv[1])
    try:
        repl(e)
    except SystemExit:
        return 1
    return 0

# _____ Define and setup target ___

def handle_config(config):
    return
    config.translation.stackless = True

def target(driver, args):
    driver.exe_name = 'pyrolog-%(backend)s'
    return entry_point, None

def portal(driver):
    from pypy.lang.prolog.interpreter.portal import get_portal
    return get_portal(driver)

if __name__ == '__main__':
    entry_point(sys.argv)
