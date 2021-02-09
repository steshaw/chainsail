import sys

import matplotlib.pyplot as plt

import numpy as np

from plots import plot_data

a1 = 1
b1 = 0
xs_line1 = np.linspace(-5, 5, 30)
ys_line1 = np.random.normal(a1 * xs_line1 + b1)

a2 = -1
b2 = 0
xs_line2 = np.linspace(-5, 5, 30)
ys_line2 = np.random.normal(a2 * xs_line2 + b2)


a3 = -4
b3 = 0
xs_line3 = np.linspace(-5, 5, 30)
ys_line3 = np.random.normal(a3 * xs_line3 + b3)

all_xs = np.concatenate((xs_line1,
                         xs_line2,
                         xs_line3
                         ))
all_ys = np.concatenate((ys_line1,
                         ys_line2,
                         ys_line3
                         ))

np.savetxt(sys.argv[1], np.vstack((all_xs, all_ys)).T)

fig, ax = plt.subplots()
plot_data(ax)
plt.show()
