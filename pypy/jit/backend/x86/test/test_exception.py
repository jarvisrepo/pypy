
import py
from pypy.jit.backend.x86.test.test_basic import Jit386Mixin
from pypy.jit.metainterp.test.test_exception import ExceptionTests

class TestExceptions(Jit386Mixin, ExceptionTests):
    # for the individual tests see
    # ====> ../../../metainterp/test/test_exception.py
    pass

