# (C) Datadog, Inc. 2010-2016
# All rights reserved
# Licensed under Simplified BSD License (see LICENSE)

from requests.packages.urllib3.exceptions import TimeoutError
import logging

from etcd import EtcdKeyNotFound, EtcdConnectionFailed
from etcd import Client as etcd_client
from utils.service_discovery.abstract_config_store import AbstractConfigStore, KeyNotFound

DEFAULT_ETCD_HOST = '127.0.0.1'
DEFAULT_ETCD_PORTS = [4001, 2379]
DEFAULT_ETCD_PROTOCOL = 'http'
DEFAULT_RECO = True
DEFAULT_TIMEOUT = 5

log = logging.getLogger(__name__)


class EtcdStore(AbstractConfigStore):
    """Implementation of a config store client for etcd"""
    def _extract_settings(self, config):
        """Extract settings from a config object"""
        settings = {
            'host': config.get('sd_backend_host', DEFAULT_ETCD_HOST),
            'port': int(config.get('sd_backend_port', -1)),
            # these two are always set to their default value for now
            'allow_reconnect': config.get('etcd_allow_reconnect', DEFAULT_RECO),
            'protocol': config.get('etcd_protocol', DEFAULT_ETCD_PROTOCOL),
        }
        return settings

    def get_client(self, reset=False):
        if self.client and reset is False:
            return self.client  # Use cached client

        if self.settings.get('port') is not -1:
            try_ports = [self.settings.get('port')]
        else:
            try_ports = DEFAULT_ETCD_PORTS

        for port in try_ports:
            try:
                self.client = etcd_client(
                    host=self.settings.get('host'),
                    port=port,
                    allow_reconnect=self.settings.get('allow_reconnect'),
                    protocol=self.settings.get('protocol'),
                )
                return self.client
            except EtcdConnectionFailed as e:
                log.debug("Can't connect to etcd on %s://%s:%d: %s" %
                          (self.settings.get('protocol'), self.settings.get('host'), port, str(e)))

        # No port succeeded, raise an exception
        if self.settings.get('port') is not -1:
            raise ValueError("Can't connect to etcd on %s://%s:%d" %
                             (self.settings.get('protocol'),
                              self.settings.get('host'),
                              self.settings.get('port')))
        else:
            raise ValueError("Can't connect to etcd host on %s://%s on default ports 4001 and 2379" %
                             (self.settings.get('protocol'),
                              self.settings.get('host')))

    def client_read(self, path, **kwargs):
        """Retrieve a value from a etcd key."""
        try:
            res = self.client.read(
                path,
                timeout=kwargs.get('timeout', DEFAULT_TIMEOUT),
                recursive=kwargs.get('recursive') or kwargs.get('all', False))
            if kwargs.get('watch', False):
                modified_indices = (res.modifiedIndex, ) + tuple(leaf.modifiedIndex for leaf in res.leaves)
                return max(modified_indices)
            else:
                return res.value
        except EtcdKeyNotFound:
            raise KeyNotFound("The key %s was not found in etcd" % path)
        except TimeoutError as e:
            raise e

    def dump_directory(self, path, **kwargs):
        """Return a dict made of all image names and their corresponding check info"""
        templates = {}
        try:
            directory = self.client.read(
                path,
                recursive=True,
                timeout=kwargs.get('timeout', DEFAULT_TIMEOUT),
            )
        except EtcdKeyNotFound:
            raise KeyNotFound("The key %s was not found in etcd" % path)
        except TimeoutError as e:
            raise e
        for leaf in directory.leaves:
            image = leaf.key.split('/')[-2]
            param = leaf.key.split('/')[-1]
            value = leaf.value
            if image not in templates:
                templates[image] = {}
            templates[image][param] = value

        return templates
