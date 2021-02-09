import os

import numpy as np

data = np.loadtxt(os.path.join(os.path.dirname(__file__), "data.txt"))


def plot_data(ax):
    ax.scatter(*data.T)


def plot_data_samples(ax, samples, title):
    def line(a, b, x): return a * x + b
    plot_data(ax)
    x_min = -5
    x_max = 5
    xspace = np.linspace(x_min, x_max, 100)
    for s in samples:
        s = s.reshape(-1, 2)
        for (a, b) in s:
            ax.plot(xspace, line(a, b, xspace), alpha=0.1)
    ax.set_title(title)
