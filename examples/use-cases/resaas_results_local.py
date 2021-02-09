import os
import sys

import numpy as np
from resaas.common.storage import SimulationStorage, LocalStorageBackend

basename = sys.argv[1]
sim_path = sys.argv[2]
outfolder = sys.argv[3]
storage = SimulationStorage(basename, sim_path, LocalStorageBackend())

samples = storage.load_all_samples()
print(samples.shape)

np.save(os.path.join(outfolder, 're_all_samples.npy'), samples)