"""
Scheduler app configuration file parsing
"""
from typing import Callable, Dict, Tuple

from libcloud.compute.drivers.gce import GCENodeDriver
from marshmallow import Schema, fields
from marshmallow.decorators import post_load
from marshmallow.exceptions import ValidationError
from marshmallow_enum import EnumField

from resaas.scheduler.nodes.base import NodeType
from resaas.scheduler.nodes.mock import DeployableDummyNodeDriver


class GCEDriverConfigSchema(Schema):
    user_id = fields.String(required=True)
    key = fields.String(required=True)
    project = fields.String(required=True)
    datacenter = fields.String(required=True)


class DummyDriverConfigSchema(Schema):
    creds = fields.String(required=True)


DRIVER_SCHEMAS: Dict[NodeType, Dict[str, Tuple[Callable, Schema]]] = {
    NodeType.LIBCLOUD_VM: {
        "gce": (GCENodeDriver, GCEDriverConfigSchema),
        "dummy": (DeployableDummyNodeDriver, DummyDriverConfigSchema),
    }
}


class SchedulerConfig:
    def __init__(
        self,
        ssh_public_key: str,
        node_entrypoint: str,
        node_image: str,
        node_size: str,
        node_type: NodeType,
        driver: Callable,
        driver_args=Tuple,
        driver_kwargs=Dict,
    ):
        self.ssh_public_key = ssh_public_key
        self.node_entrypoint = node_entrypoint
        self.image = node_image
        self.size = node_size
        self.node_type = node_type
        self.driver = driver
        self.driver_args = driver_args
        self.driver_kwargs = driver_kwargs

    def create_node_driver(self):
        """Create a new node driver instance using the scheduler config"""
        return self.driver(*self.driver_args, **self.driver_kwargs)


class SchedulerConfigSchema(Schema):
    """Schema for parsing scheduler configuration files.

    To aid in prototyping, this schema works by allowing users to specify a
    driver id which must exist in the 'DRIVER_SCHEMAS' global registry. Required
    arguments for instantiating the various drivers are declared in this registry
    using a separate schema for each driver type. See GCEDriverConfigSchema
    for an example.
    """

    ssh_public_key = fields.String(required=True)
    node_entrypoint = fields.String(required=True)
    node_image = fields.String(required=True)
    node_size = fields.String(required=True)
    # The type of nodes to instantiate
    node_type = EnumField(NodeType, by_value=True, required=True)
    node_driver = fields.String(required=True)
    # Initial parsing converts driver info into a dict. We will
    # then verify that all of the expected fields exist in that dict.
    driver_specs = fields.Dict(fields.String, fields.Dict)

    @post_load
    def make_scheduler_config(self, data, **kwargs):
        # Lookup the expected schema for the driver config
        node_type = data["node_type"]
        if node_type not in DRIVER_SCHEMAS:
            raise ValidationError(f"Scheduler config specified an unknown node_type: {node_type}")
        requested_driver = data["node_driver"]
        if requested_driver not in DRIVER_SCHEMAS[node_type]:
            raise ValidationError(
                f"Scheduler config specified an unknown driver type: {requested_driver}"
            )
        driver, driver_config_schema = DRIVER_SCHEMAS[node_type][requested_driver]
        if requested_driver not in data["driver_specs"]:
            raise ValidationError(
                f"Scheduler config specified node_driver '{requested_driver}' but did not "
                "specify corresponding specs for it in driver_specs."
            )
        # Validate that the required config fields exist
        driver_config = driver_config_schema().load(data["driver_specs"][requested_driver])
        return SchedulerConfig(
            ssh_public_key=data["ssh_public_key"],
            node_entrypoint=data["node_entrypoint"],
            node_image=data["node_image"],
            node_size=data["node_size"],
            node_type=data["node_type"],
            driver=driver,
            driver_args=(),
            driver_kwargs=driver_config,
        )