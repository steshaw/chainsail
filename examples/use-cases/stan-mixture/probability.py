import numpy as np
import requests


class PDF:
    STAN_SERVER_ADDRESS = "http://localhost"

    def __init__(self, model_code, data=None, port=8082):
        self._port = port
        try:
            r = requests.post(
                f"{self.STAN_SERVER_ADDRESS}:{self._port}/v1/models",
                json={"program_code": model_code},
            )
            r.raise_for_status()
            self._model_id = r.json()["name"]
        except Exception as e:
            raise Exception(f"Model compilation failed. Error: {e}")
        self._data = data or {}

    def log_prob(self, x):
        try:
            r = requests.post(
                f"{self.STAN_SERVER_ADDRESS}:{self._port}/v1/{self._model_id}/log_prob",
                json={
                    "unconstrained_parameters": x.tolist(),
                    "data": self._data,
                    "adjust_transform": False,
                },
            )
            r.raise_for_status()
            return r.json()["log_prob"]
        except Exception as e:
            raise Exception(f"Querying log-prob failed: Error: {e}")

    def log_prob_gradient(self, x):
        try:
            r = requests.post(
                f"{self.STAN_SERVER_ADDRESS}:{self._port}/v1/{self._model_id}/log_prob_grad",
                json={
                    "unconstrained_parameters": x.tolist(),
                    "data": self._data,
                    "adjust_transform": False,
                },
            )
            r.raise_for_status()
            return np.array(r.json()["log_prob_grad"])
        except Exception as e:
            raise Exception(f"Querying log-prob gradient failed: Error: {e}")


model_code = """
parameters {
  real y;
}
model {
  target += log_sum_exp(log(0.3) + normal_lpdf(y | -1.5, 0.5),
                        log(0.7) + normal_lpdf(y | 2.0, 0.2));
}
"""

pdf = PDF(model_code)
initial_states = np.array([np.random.uniform(-2, 3)])