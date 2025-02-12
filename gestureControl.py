#!/usr/bin/env python
from pykeyboard import PyKeyboard
from pymouse import PyMouse
from time import sleep
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import butter, lfilter, lfilter_zi
from time import sleep
from pylsl import StreamInlet, resolve_byprop
from optparse import OptionParser
import seaborn as sns
from threading import Thread

sns.set(style="whitegrid")

parser = OptionParser()

parser.add_option("-w", "--window",
                  dest="window", type='float', default=5.,
                  help="window lenght to display in seconds.")
parser.add_option("-s", "--scale",
                  dest="scale", type='float', default=100,
                  help="scale in uV")
parser.add_option("-r", "--refresh",
                  dest="refresh", type='float', default=0.2,
                  help="refresh rate in seconds.")
parser.add_option("-f", "--figure",
                  dest="figure", type='string', default="15x6",
                  help="window size.")

filt = True
subsample = 2
buf = 12

(options, args) = parser.parse_args()

window = options.window
scale = options.scale
figsize = np.int16(options.figure.split('x'))

print("looking for an EEG stream...")
streams = resolve_byprop('type', 'EEG', timeout=2)

if len(streams) == 0:
    raise(RuntimeError("Cant find EEG stream"))
print("Start aquiring data")



class LSLViewer():

    def __init__(self, stream, fig, axes,  window, scale, dejitter=True):
        """Init"""
        self.stream = stream
        self.window = window
        self.scale = scale
        self.dejitter = dejitter
        self.inlet = StreamInlet(stream, max_chunklen=buf)
        self.filt = True
        self.k = PyKeyboard()
        self.m = PyMouse()
        self.xdim, self.ydim = self.m.screen_size()

        info = self.inlet.info()
        description = info.desc()

        self.sfreq = info.nominal_srate()
        self.n_samples = int(self.sfreq * self.window)
        self.n_chan = info.channel_count()

        ch = description.child('channels').first_child()
        ch_names = [ch.child_value('label')]

        for i in range(self.n_chan):
            ch = ch.next_sibling()
            ch_names.append(ch.child_value('label'))

        self.ch_names = ch_names

        fig.canvas.mpl_connect('key_press_event', self.OnKeypress)
        fig.canvas.mpl_connect('button_press_event', self.onclick)

        self.fig = fig
        self.axes = axes

        sns.despine(left=True)

        self.data = np.zeros((self.n_samples, self.n_chan))
        self.times = np.arange(-self.window, 0, 1./self.sfreq)
        impedances = np.std(self.data, axis=0)
        lines = []

        for ii in range(self.n_chan):
            line, = axes.plot(self.times[::subsample],
                              self.data[::subsample, ii] - ii, lw=1)
            lines.append(line)
        self.lines = lines

        axes.set_ylim(-self.n_chan + 0.5, 0.5)
        ticks = np.arange(0, -self.n_chan, -1)

        axes.set_xlabel('Time (s)')
        axes.set_ylabel('Average Voltage (uV)')
        axes.xaxis.grid(False)
        axes.set_yticks(ticks)

        ticks_labels = ['%s - %.1f' % (ch_names[ii], impedances[ii])
                        for ii in range(self.n_chan)]
        axes.set_yticklabels(ticks_labels)

        self.display_every = int(0.2 / (12/self.sfreq))

        self.bf, self.af = butter(4, np.array([1, 40])/(self.sfreq/2.),'bandpass')
        zi = lfilter_zi(self.bf, self.af)
        self.filt_state = np.tile(zi, (self.n_chan, 1)).transpose()
        self.data_f = np.zeros((self.n_samples, self.n_chan))

    def update_plot(self):
        k = 0
        while self.started:
            samples, timestamps = self.inlet.pull_chunk(timeout=1.0,
                                                        max_samples=12)
            if timestamps:
                if self.dejitter:
                    timestamps = np.float64(np.arange(len(timestamps)))
                    timestamps /= self.sfreq
                    timestamps += self.times[-1] + 1./self.sfreq
                self.times = np.concatenate([self.times, timestamps])
                self.n_samples = int(self.sfreq * self.window)
                self.times = self.times[-self.n_samples:]
                self.data = np.vstack([self.data, samples])
                self.data = self.data[-self.n_samples:]
                filt_samples, self.filt_state = lfilter(
                    self.bf, self.af,
                    samples,
                    axis=0, zi=self.filt_state)
                self.data_f = np.vstack([self.data_f, filt_samples])
                self.data_f = self.data_f[-self.n_samples:]
                k += 1

                if k == self.display_every:

                    if self.filt:
                        plot_data = self.data_f
                    elif not self.filt:
                        plot_data = self.data - self.data.mean(axis=0)
                    #                    LC,RC,EY,WR
                    t_values = np.array([75,75,75,1000])

                    print("Data\n")
                    last_100ms = np.absolute(plot_data[980:,:])
                    # print(last_100ms)
                    # print("Average\n")
                    # print(np.mean(last_100ms, axis = 0))
                    # print("Max\n")
                    # print(np.max(last_100ms, axis = 0))
                    # print("Count\n")
                    print("L, R, E, W")
                    # print(np.sum(last_100ms > t_values, axis = 0))
                    print("\n")
                    cmdArr = np.sum(last_100ms > t_values, axis = 0) > [10,7,10,10]
                    print(cmdArr)
                    print("\n")

                    self.k.release_key('c')
                    self.k.release_key('v')
                    self.k.release_key('z')
                    self.k.release_key('x')
                    ##Keyboard Input
                    if cmdArr[0]: ##Mario Left
                        self.k.press_key('c')
                    if cmdArr[1]: ##Mario Right
                        self.k.press_key('v')
                    if cmdArr[2]: ## Mario Jump
                        self.k.press_key('z')
                    if cmdArr[3]: ## Mario Special
                        self.k.press_key('x')


                    ####



                    for ii in range(self.n_chan):
                        self.lines[ii].set_xdata(self.times[::subsample] -
                                                 self.times[-1])
                        self.lines[ii].set_ydata(plot_data[::subsample, ii] /
                                                 self.scale - ii)
                        impedances = np.std(plot_data, axis=0)

                    ticks_labels = ['%s - %.2f' % (self.ch_names[ii],
                                                   impedances[ii])
                                    for ii in range(self.n_chan)]
                    self.axes.set_yticklabels(ticks_labels)
                    self.axes.set_xlim(-self.window, 0)
                    self.fig.canvas.draw()
                    k = 0
            else:
                sleep(0.2)

    def onclick(self, event):
        print((event.button, event.x, event.y, event.xdata, event.ydata))

    def OnKeypress(self, event):
        if event.key == '/':
            self.scale *= 1.2
        elif event.key == '*':
            self.scale /= 1.2
        elif event.key == '+':
            self.window += 1
        elif event.key == '-':
            if self.window > 1:
                self.window -= 1
        elif event.key == 'd':
            self.filt = not(self.filt)

    def start(self):
        self.started = True
        self.thread = Thread(target=self.update_plot)
        self.thread.daemon = True
        self.thread.start()

    def stop(self):
        self.started = False


##print(streams[0])
fig, axes = plt.subplots(1, 1, figsize=figsize, sharex=True)
lslv = LSLViewer(streams[0], fig, axes, window, scale)


help_str = """
            toggle filter : d
            toogle full screen : f
            zoom out : /
            zoom in : *
            increase time scale : -
            decrease time scale : +
           """

print(help_str)
lslv.start()

plt.show()
lslv.stop()
