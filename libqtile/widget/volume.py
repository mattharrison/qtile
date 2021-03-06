import re
import time
from subprocess import call

import cairo

import base
from .. import manager, bar, hook

__all__ = [
    'Volume',
]

re_vol = re.compile('\[(\d?\d?\d?)%\]')

class Volume(base._TextBox):
    ''' Widget that display and change volume 
        if theme_path is set it draw widget as
        icons '''
    defaults = manager.Defaults(
        ("cardid", 0, "Card Id"),
        ("channel", "Master", "Channel"),
        ("font", "Arial", "Text font"),
        ("fontsize", None, "Font pixel size. Calculated if None."),
        ("padding", None, "Padding left and right. Calculated if None."),
        ("background", None, "Background colour."),
        ("foreground", "#ffffff", "Foreground colour."),
        ("theme_path", None, "Path of the icons"),
    )
    def __init__(self, **config):
        base._TextBox.__init__(self, '0', width=bar.CALCULATED, **config)
        self.surfaces = {}
        self.lasttick = 0

    def _configure(self, qtile, bar):
        base._TextBox._configure(self, qtile, bar)
        if self.theme_path:
            self.setup_images()
        hook.subscribe.tick(self.update)

    def click(self, x, y, button):
        if button == 5:
            call(['amixer', '-q', '-c', str(self.cardid),
                              'sset', self.channel, '5%-'])
        elif button == 4:
            call(['amixer', '-q', '-c', str(self.cardid),
                              'sset', self.channel, '5%+'])
        elif button == 1:
            call(['amixer', '-q', '-c', str(self.cardid),
                           'sset', self.channel, 'toggle'])
        self.draw()

    def update(self):
        t = time.time()
        if self.lasttick + 0.2 < t:
            self.lasttick = t
            #self.draw()
            self.bar.draw()

    def setup_images(self):
        for img_name in ('audio-volume-high', 'audio-volume-low',
                      'audio-volume-medium', 'audio-volume-muted'):

            try:
                img = cairo.ImageSurface.create_from_png(
                        '%s/%s.png' % (self.theme_path, img_name))
            except cairo.Error, error:
                self.theme_path = None
                self.qtile.log.add(error)
                self.qtile.log.add('Volume switching to text mode')
                return
            input_width = img.get_width()
            input_height = img.get_height()

            sp = input_height/float(self.bar.height-1)

            width = input_width / sp
            if width > self.width:
                self.width = int(width)

            imgpat = cairo.SurfacePattern(img)

            scaler = cairo.Matrix()

            scaler.scale(sp, sp)
            imgpat.set_matrix(scaler)

            imgpat.set_filter(cairo.FILTER_BEST)
            self.surfaces[img_name] = imgpat

    def get_volume(self):
        from subprocess import check_output
        mixer_out = check_output(['amixer', '-c', str(self.cardid),
                                         'sget', self.channel])
        if '[off]' in mixer_out:
            return -1

        volgroups = re_vol.search(mixer_out)
        if volgroups:
            return int(volgroups.groups()[0])
        else:
            # this shouldn't happend
            return -1

    def draw(self):
        vol = self.get_volume()
        if self.theme_path:
            self.drawer.clear(self.bar.background)
            if vol <= 0:
                img_name = 'audio-volume-muted'
            elif vol <= 30:
                img_name = 'audio-volume-low'
            elif vol < 80:
                img_name = 'audio-volume-medium'
            elif vol >= 80:
                img_name = 'audio-volume-high'

            self.drawer.ctx.set_source(self.surfaces[img_name])
            self.drawer.ctx.paint()
            self.drawer.draw(self.offset, self.width)
        else:
            if vol == -1:
                self.text = 'M'
            else:
                self.text = '%s%%' % vol
            base._TextBox.draw(self)
