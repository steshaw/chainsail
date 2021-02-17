"""
Main entrypoint to the resaas controller
"""
import json
import logging
from concurrent import futures
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from importlib import import_module
from logging.handlers import MemoryHandler
from math import floor
from multiprocessing import Process
from typing import Tuple

import click
import grpc
import requests
import yaml
from marshmallow import Schema, fields
from marshmallow.decorators import post_load
from resaas.common.runners import AbstractRERunner, runner_config
from resaas.common.spec import JobSpec, JobSpecSchema
from resaas.common.storage import load_storage_config
from resaas.controller import (
    CloudREJobController,
    optimization_objects_from_spec,
    update_nodes_mpi,
)
from resaas.grpc import Health, add_HealthServicer_to_server

ProcessStatus = Tuple[bool, str]


logger = logging.getLogger("resaas.controller")
##############################################################################
# CONFIG
##############################################################################


@dataclass
class ControllerConfig:
    """Resaas controller configurations"""

    scheduler_address: str
    scheduler_port: int
    metrics_address: str
    metrics_port: int
    runner: str
    storage_basename: str = ""
    port: int = 50051
    n_threads: int = 10
    log_level: str = "INFO"
    remote_logging: bool = True
    remote_logging_port: int = 80
    remote_logging_buffer_size: int = 5


class ControllerConfigSchema(Schema):
    scheduler_address = fields.String(required=True)
    scheduler_port = fields.Integer(required=True)
    metrics_address = fields.String(required=True)
    metrics_port = fields.Integer(required=True)
    runner = fields.String(required=True)
    storage_basename = fields.String()
    port = fields.Integer()
    n_threads = fields.Integer()
    log_level = fields.String()
    remote_logging = fields.Boolean()
    remote_logging_port = fields.Integer()
    remote_logging_buffer_size = fields.Integer()

    @post_load
    def make_controller_config(self, data, **kwargs) -> ControllerConfig:
        return ControllerConfig(**data)


class GraphiteHTTPHandler(logging.Handler):
    """A logging handler for writing Graphite events.

    Uses `requests` internally and writes the log record to the Graphite event's
    'data' field. Supports custom logging formaters.

    Args:
        url: The graphite events url
        what: The name of the event
        tags: An optional list of tags to give the event
        timeout: Request timeout in seconds

    """

    def __init__(self, url: str, what="log", tags=None, timeout=5):
        super().__init__()
        self.url = url
        self.timeout = timeout
        self.what = what
        if not tags:
            self.tags = ["log"]
        else:
            self.tags = tags

    def emit(self, record: logging.LogRecord):
        try:
            payload = {
                "what": self.what,
                "tags": self.tags + [record.levelname],
                "when": floor(datetime.utcnow().timestamp()),
                "data": self.format(record),
            }
            response = requests.post(
                url=self.url,
                data=json.dumps(payload),
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception:
            self.handleError(record)


##############################################################################
# ENTRYPOINT
##############################################################################


def load_runner(runner_path: str) -> AbstractRERunner:
    """Loads a runner class from its module path.

    Args:
        runner: The path to the runner with the module and class delimited
            by a colon. e.g. 'some.module:MyRunner'
    """
    module, runner_name = runner_path.split(":")
    logger.info(f"Attempting to load runner '{runner_name}' from {module}")
    module = import_module(module)
    return getattr(module, runner_name)


def check_status(proc: Process) -> ProcessStatus:
    if proc.exitcode is None:
        return (True, "SERVING")
    elif proc.exitcode != 0:
        return (False, "FAILED")
    else:
        return (True, "SUCCESS")


@click.command()
@click.option("--job", required=True, type=str, help="resaas job id")
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True),
    help="path to controller YAML config file",
)
@click.option(
    "--storage",
    required=True,
    type=click.Path(exists=True),
    help="path to storage backend YAML config file",
)
# Note: The controller is currently configured to only work with mpi, so this is not
#  abstracted away. At some point in the future the hostsfile logic could get moved
#  into its own area. The main thing is that with a master-worker achitecture, the
#  master process (running the controller in the current case) needs a way of identifying
#  the workers.
@click.option(
    "--hostsfile", required=True, type=click.Path(exists=True), help="path to job hostsfile"
)
@click.option(
    "--job-spec", required=True, type=click.Path(exists=True), help="path to job spec json file"
)
def run(job, config, storage, hostsfile, job_spec):
    """
    The resaas node controller.
    """
    # Load the controller configuration file
    with open(config) as f:
        config: ControllerConfig = ControllerConfigSchema().load(yaml.safe_load(f))
    # Configure logging
    log_level = logging.getLevelName(config.log_level)
    base_logger = logging.getLogger("resaas")
    base_logger.setLevel(log_level)
    basic_handler = logging.StreamHandler()
    basic_formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(name)s - %(message)s")
    basic_handler.setFormatter(basic_formatter)
    base_logger.addHandler(basic_handler)

    if config.remote_logging:
        logger.info("Configuring remote logging")

        # Add graphite remote logging
        graphite_handler = GraphiteHTTPHandler(
            url=f"http://{config.metrics_address}:{config.remote_logging_port}/events",
            what="log",
            tags=["log"],
        )
        graphite_handler.setFormatter(basic_formatter)
        # Use buffering to avoid having to making excessive calls
        buffered_graphite_handler = MemoryHandler(
            config.remote_logging_buffer_size, target=graphite_handler
        )
        base_logger.addHandler(buffered_graphite_handler)

    logger.info("Loading job spec from file")
    with open(job_spec) as f:
        job_spec: JobSpec = JobSpecSchema().loads(f.read())

    logger.info("Loading storage config file")
    backend_config = load_storage_config(storage)
    logger.info("Initializing storage backend using config")
    storage_backend = backend_config.get_storage_backend()

    # Load the controller
    runner = load_runner(config.runner)()
    # TODO: Hard-coding this for now until we have a need for multiple runners
    runner_config["hostsfile"] = hostsfile
    runner_config["run_id"] = job
    runner_config["storage_config"] = storage
    runner_config["metrics_host"] = config.metrics_address
    runner_config["metrics_port"] = config.metrics_port

    logger.debug(repr(runner_config))

    optimization_objects = optimization_objects_from_spec(job_spec)

    controller = CloudREJobController(
        job,
        config.scheduler_address,
        config.scheduler_port,
        job_spec.replica_exchange_parameters,
        job_spec.local_sampling_parameters,
        job_spec.optimization_parameters,
        runner,
        storage_backend,
        node_updater=partial(update_nodes_mpi, hostsfile),
        basename=f"{config.storage_basename}/{job}",
        **optimization_objects,
    )

    # Start controller in another process
    def wrapped_run_job():
        try:
            controller.run_job()
        except Exception as e:
            # Ensures that top-level errors in the controller get logged
            logger.exception(e)
            raise e

    controller_proc = Process(target=wrapped_run_job, daemon=True)
    controller_proc.start()

    # Gets the status of the controller process
    def controller_state():
        return check_status(controller_proc)[1]

    # Start gRPC server
    with futures.ThreadPoolExecutor(max_workers=config.n_threads) as ex:
        server = grpc.server(ex)
        add_HealthServicer_to_server(Health(callback=controller_state), server)
        server.add_insecure_port(f"[::]:{config.port}")
        server.start()
        server.wait_for_termination()


if __name__ == "__main__":
    run()
