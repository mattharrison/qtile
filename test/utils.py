import subprocess, os, time, sys, socket, traceback
import Xlib.display, Xlib.X
import libpry
import libqtile, libqtile.ipc, libqtile.hook

WIDTH = 800
HEIGHT = 600
SECOND_WIDTH = 640
SECOND_HEIGHT = 480

def _find_display():
    """
        Returns the next available display
    """
    display = 1
    while os.path.exists("/tmp/.X%s-lock" % display):
        display += 1
    return display

DISPLAY = ":%s" % _find_display()


def whereis(program):
    for path in os.environ.get('PATH', '').split(':'):
        if os.path.exists(os.path.join(path, program)) and \
           not os.path.isdir(os.path.join(path, program)):
            return os.path.join(path, program)
    return None


class Xephyr(libpry.TestContainer):
    def __init__(self, xinerama, randr=False, two_screens=True, width=WIDTH, height=HEIGHT):
        self.xinerama, self.randr = xinerama, randr
        self.name = "xephyr"
        if xinerama:
            self.name += "_xinerama"
        if randr:
            self.name += "_randr"
        self.two_screens = two_screens
        libpry.TestContainer.__init__(self)
        self["display"] = DISPLAY
        self["xinerama"] = xinerama
        self.width = width
        self.height = height

    def setUp(self):
        args = [
            "Xephyr", "-keybd", "evdev",
            self["display"], "-ac",
            "-screen", "%sx%s"%(self.width, self.height)]
        if self.two_screens:
            args.extend(["-screen", "%sx%s+800+0"%(SECOND_WIDTH, SECOND_HEIGHT)])

        if self.xinerama:
            args.extend(["+xinerama"])
        if self.randr:
            args.extend(["+extension", "RANDR"])
        self.sub = subprocess.Popen(
                        args,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.PIPE,
                    )
        time.sleep(0.05)

    def tearDown(self):
        os.kill(self.sub.pid, 9)
        os.waitpid(self.sub.pid, 0)


class _QtileTruss(libpry.AutoTree):
    qtilepid = None
    def setUp(self):
        self.testwindows = []

    def _waitForXephyr(self):
        # Try until Xephyr is up
        for i in range(50):
            try:
                d = Xlib.display.Display(self["display"])
                break
            except (Xlib.error.DisplayConnectionError, Xlib.error.ConnectionClosedError), v:
                time.sleep(0.1)
        else:
            raise AssertionError, "Could not connect to display."
        d.close()
        del d

    def _waitForQtile(self):
        for i in range(20):
            try:
                if self.c.status() == "OK":
                    break
            except libqtile.ipc.IPCError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError, "Timeout waiting for Qtile"

    def qtileRaises(self, exc, config):
        self._waitForXephyr()
        self["fname"] = os.path.join(self.tmpdir(), "qtilesocket")
        libpry.raises(exc, libqtile.manager.Qtile, config, self["display"], self["fname"])

    def startQtile(self, config):
        self._waitForXephyr()
        self["fname"] = os.path.join(self.tmpdir(), "qtilesocket")
        pid = os.fork()
        if pid == 0:
            try:
                q = libqtile.manager.Qtile(config, self["display"], self["fname"], testing=True)
                q.loop()
            except Exception, e:
                traceback.print_exc(file=sys.stderr)
            sys.exit(0)
        else:
            self.qtilepid = pid
            self.c = libqtile.command.Client(self["fname"], config)
            self._waitForQtile()

    def stopQtile(self):
        assert self.c.status()
        if self.qtilepid:
            try:
                self._kill(self.qtilepid)
            except OSError:
                # The process may have died due to some other error
                pass
        for pid in self.testwindows[:]:
            self._kill(pid)

    def _testProc(self, path, args):
        if path is None:
            raise AssertionError("Trying to run None! (missing executable)")
        start = len(self.c.windows())
        pid = os.fork()
        if pid == 0:
            os.putenv("DISPLAY", self["display"])
            os.execv(path, args)
        for i in range(20):
            if len(self.c.windows()) > start:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Window never appeared...")
        self.testwindows.append(pid)
        return pid

    def testWindow(self, name):
        return self._testProc(
                    "scripts/window",
                    ["scripts/window", self["display"], name]
                )

    def testXclock(self):
        path = whereis("xclock")
        return self._testProc(
                    path,
                    [path, "-display", self["display"]]
                )

    def testXeyes(self):
        path = whereis("xeyes")
        return self._testProc(
                    path,
                    [path, "-display", self["display"]]
                )

    def testGkrellm(self):
        path = whereis("gkrellm")
        return self._testProc(
                    path,
                    [path]
                )

    def testXterm(self):
        path = whereis("xterm")
        return self._testProc(
                    path,
                    [path, "-display", self["display"]]
                )

    def _kill(self, pid):
        os.kill(pid, 9)
        os.waitpid(pid, 0)
        if pid in self.testwindows:
            self.testwindows.remove(pid)

    def kill(self, pid):
        start = len(self.c.windows())
        self._kill(pid)
        for i in range(20):
            if len(self.c.windows()) < start:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Window could not be killed...")


class QtileTests(_QtileTruss):
    config = None
    def setUp(self):
        _QtileTruss.setUp(self)
        self.startQtile(self.config)

    def tearDown(self):
        _QtileTruss.tearDown(self)
        libqtile.hook.clear()
        self.stopQtile()

    def _groupconsistency(self):
        groups = self.c.groups()
        screens = self.c.screens()
        seen = set()
        for g in groups.values():
            scrn = g["screen"]
            if scrn is not None:
                if scrn in seen:
                    raise AssertionError, "Screen referenced from more than one group."
                seen.add(scrn)
                assert screens[scrn]["group"] == g["name"]
        assert len(seen) == len(screens), "Not all screens had an attached group."
