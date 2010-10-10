import inspect
import os.path
import sys
import pdb
import re
from cStringIO import StringIO
import py

class FakeStdin:
    def __init__(self, lines):
        self.lines = iter(lines)

    def readline(self):
        try:
            line = self.lines.next() + '\n'
            sys.stdout.write(line)
            return line
        except StopIteration:
            return ''

class ConfigTest(pdb.DefaultConfig):
    highlight = False
    prompt = '# ' # because + has a special meaning in the regexp
    editor = 'emacs'
    stdin_paste = 'epaste'
    disable_pytest_capturing = False


class PdbTest(pdb.Pdb):
    use_rawinput = 1

    def __init__(self, **kwds):
        pdb.Pdb.__init__(self, Config=ConfigTest, **kwds)

    def _open_editor(self, editor, lineno, filename):
        print "RUN %s +%d '%s'" % (editor, lineno, filename)

    def _open_stdin_paste(self, cmd, lineno, filename, text):
        print "RUN %s +%d" % (cmd, lineno)
        print text


def set_trace():
    frame = sys._getframe().f_back
    pdb.set_trace(frame, PdbTest)

def xpm():
    pdb.xpm(PdbTest)

def runpdb(func, input):
    oldstdin = sys.stdin
    oldstdout = sys.stdout

    try:
        sys.stdin = FakeStdin(input)
        sys.stdout = stdout = StringIO()
        func()
    finally:
        sys.stdin = oldstdin
        sys.stdout = oldstdout

    return stdout.getvalue().splitlines()

def extract_commands(lines):
    return [line[2:] for line in lines if line.startswith('# ')]

shortcuts = {
    '(': '\\(',
    ')': '\\)',
    'NUM': ' *[0-9]*',
    'CLEAR': re.escape(pdb.CLEARSCREEN),
    }

def cook_regexp(s):
    for key, value in shortcuts.iteritems():
        s = s.replace(key, value)
    return s

def check(func, expected):
    expected = expected.strip().splitlines()
    commands = extract_commands(expected)
    expected = map(cook_regexp, expected)
    lines = runpdb(func, commands)
    assert len(expected) == len(lines)
    for pattern, string in zip(expected, lines):
        assert re.match(pattern, string)


def test_runpdb():
    def fn():
        set_trace()
        a = 1
        b = 2
        c = 3
        return a+b+c

    check(fn, """
> .*fn()
-> a = 1
# n
> .*fn()
-> b = 2
# n
> .*fn()
-> c = 3
# c
""")

def test_parseline():
    def fn():
        r = 42
        set_trace()
        return r

    check(fn, """
> .*fn()
-> return r
# r
42
# c
""")

def test_args_name():
    def fn():
        args = 42
        set_trace()
        return args

    check(fn, """
> .*fn()
-> return args
# args
42
# c
""")

def test_longlist():
    def fn():
        a = 1
        set_trace()
        return a

    check(fn, """
> .*fn()
-> return a
# ll
NUM         def fn():
NUM             a = 1
NUM             set_trace()
NUM  ->         return a
# c
""".replace('NUM', ' *[0-9]*'))

def test_watch():
    def fn():
        a = 1
        set_trace()
        b = 1
        a = 2
        a = 3
        return a

    check(fn, """
> .*fn()
-> b = 1
# watch a
# n
> .*fn()
-> a = 2
# n
> .*fn()
-> a = 3
a: 1 --> 2
# unwatch a
# n
> .*fn()
-> return a
# c
""")

def test_watch_undefined():
    def fn():
        set_trace()
        b = 42
        return b

    check(fn, """
> .*fn()
-> b = 42
# watch b
# n
> .*fn()
-> return b
b: <undefined> --> 42
# c
""")

def test_sticky():
    def fn():
        set_trace()
        a = 1
        b = 2
        c = 3
        return a

    check(fn, """
> .*fn()
-> a = 1
# sticky
CLEAR>.*

NUM         def fn():
NUM             set_trace()
NUM  ->         a = 1
NUM             b = 2
NUM             c = 3
NUM             return a
# n
> .*fn()
-> b = 2
CLEAR>.*

NUM         def fn():
NUM             set_trace()
NUM             a = 1
NUM  ->         b = 2
NUM             c = 3
NUM             return a
# sticky
# n
> .*fn()
-> c = 3
# c
""")

def test_sticky_range():
    import inspect
    def fn():
        set_trace()
        a = 1
        b = 2
        c = 3
        return a
    _, lineno = inspect.getsourcelines(fn)
    start = lineno + 1
    end = lineno + 3

    check(fn, """
> .*fn()
-> a = 1
# sticky %d %d
CLEAR>.*

 %d             set_trace()
NUM  ->         a = 1
NUM             b = 2
# c
""" % (start, end, start))


def test_exception_lineno():
    def bar():
        assert False
    def fn():
        try:
            a = 1
            bar()
            b = 2
        except AssertionError:
            xpm()

    check(fn, """
> .*bar()
-> assert False
# u
> .*fn()
-> bar()
# ll
NUM         def fn():
NUM             try:
NUM                 a = 1
NUM  >>             bar()
NUM                 b = 2
NUM             except AssertionError:
NUM  ->             xpm()
# c
""")

def test_exception_through_generator():
    def gen():
        yield 5
        assert False
    def fn():
        try:
            for i in gen():
                pass
        except AssertionError:
            xpm()

    check(fn, """
> .*gen()
-> assert False
# u
> .*fn()
-> for i in gen():
# c
""")

def test_py_code_source():
    src = py.code.Source("""
    def fn():
        x = 42
        set_trace()
        return x
    """)
    
    exec src.compile()
    check(fn, """
> .*fn()
-> return x
# ll
NUM     def fn():
NUM         x = 42
NUM         set_trace()
NUM  ->     return x
# c
""")

def test_source():
    def bar():
        return 42
    def fn():
        set_trace()
        return bar()

    check(fn, """
> .*fn()
-> return bar()
# source bar
NUM         def bar():
NUM             return 42
# c
""")

def test_bad_source():
    def fn():
        set_trace()
        return 42

    check(fn, r"""
> .*fn()
-> return 42
# source 42
\*\* Error: arg is not a module, class, method, function, traceback, frame, or code object \*\*
# c
""")

def test_edit():
    def fn():
        set_trace()
        return 42
    def bar():
        fn()
        return 100

    _, lineno = inspect.getsourcelines(fn)
    return42_lineno = lineno + 2
    call_fn_lineno = lineno + 4
    filename = os.path.abspath(__file__)
    if filename.endswith('.pyc'):
        filename = filename[:-1]
    
    check(fn, r"""
> .*fn()
-> return 42
# edit
RUN emacs \+%d '%s'
# c
""" % (return42_lineno, filename))

    check(bar, r"""
> .*fn()
-> return 42
# up
> .*bar()
-> fn()
# edit
RUN emacs \+%d '%s'
# c
""" % (call_fn_lineno, filename))


def test_edit_obj():
    def fn():
        bar()
        set_trace()
        return 42
    def bar():
        pass
    _, bar_lineno = inspect.getsourcelines(bar)
    filename = os.path.abspath(__file__)
    if filename.endswith('.pyc'):
        filename = filename[:-1]

    check(fn, r"""
> .*fn()
-> return 42
# edit bar
RUN emacs \+%d '%s'
# c
""" % (bar_lineno, filename))


def test_put():
    def fn():
        set_trace()
        return 42
    _, lineno = inspect.getsourcelines(fn)
    start_lineno = lineno + 1

    check(fn, r"""
> .*fn()
-> return 42
# x = 10
# y = 12
# put
RUN epaste \+%d
        x = 10
        y = 12

# c
""" % start_lineno)


def test_put_if():
    def fn():
        x = 0
        if x < 10:
            set_trace()
        return x
    _, lineno = inspect.getsourcelines(fn)
    start_lineno = lineno + 3

    check(fn, r"""
> .*fn()
-> return x
# x = 10
# y = 12
# put
RUN epaste \+%d
            x = 10
            y = 12

# c
""" % start_lineno)

def test_side_effects_free():
    r = pdb.side_effects_free
    assert r.match('  x')
    assert r.match('x.y[12]')
    assert not r.match('x(10)')
    assert not r.match('  x = 10')
    assert not r.match('x = 10')

def test_put_side_effects_free():
    def fn():
        x = 10
        set_trace()
        return 42
    _, lineno = inspect.getsourcelines(fn)
    start_lineno = lineno + 2

    check(fn, r"""
> .*fn()
-> return 42
# x
10
# x.__add__
.*
# y = 12
# put
RUN epaste \+%d
        y = 12

# c
""" % start_lineno)

def test_enable_disable():
    def fn():
        x = 1
        pdb.disable()
        set_trace()
        x = 2
        pdb.enable()
        set_trace()
        return x

    check(fn, """
> .*fn()
-> return x
# x
2
# c
""")
