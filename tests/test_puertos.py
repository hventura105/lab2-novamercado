"""Salvaguardas de la reparación de puertos; dobles locales, sin modificar Docker."""

from copy import deepcopy
import contextlib
import io
import json
import unittest
from unittest.mock import patch

from scripts import puertos


def configuration():
    return {"name": "lab2-novamercado", "networks": {
        "internal": {"name": "lab2-novamercado_internal", "internal": True},
        "publicacion": {"name": puertos.NETWORK_NAME, "driver": "bridge", "internal": False, "driver_opts": {puertos.NAT_OPTION: "nat"}}},
        "services": {**{name: {"ports": [{"target": port, "published": str(port), "host_ip": "127.0.0.1", "protocol": "tcp", "mode": "ingress"}],
                              "networks": {"internal": None, "publicacion": None}}
                        for name, port in puertos.TARGETS.items()},
                     "product-db": {"networks": {"internal": None}}, "airflow-db": {"networks": {"internal": None}}}}


def inventory(published=False):
    return [{"id": name + "-id", "name": "/lab2-" + name, "project": "lab2-novamercado", "service": name,
             "running": True, "networks": {"lab2-novamercado_internal": {}},
             "requested": {f"{port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]},
             "actual": {f"{port}/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}] if published else None}}
            for name, port in puertos.TARGETS.items()]


class PortRepairTests(unittest.TestCase):
    def test_null_empty_and_zero_bindings_are_not_publications(self):
        for value in (None, [], [{"HostIp": "", "HostPort": "0"}], [{"HostIp": "127.0.0.1", "HostPort": "0"}]):
            self.assertFalse(puertos.binding_matches(value, 8000))
        self.assertTrue(puertos.binding_matches([{"HostIp": "127.0.0.1", "HostPort": "8000"}], 8000))

    def test_random_port_config_is_rejected(self):
        config = configuration()
        config["services"]["api"]["ports"][0]["published"] = "0"
        with self.assertRaisesRegex(RuntimeError, "8000"):
            puertos.validate_config(config)

    def test_postgres_never_joins_publication_network(self):
        config = configuration()
        config["services"]["product-db"]["networks"]["publicacion"] = None
        with self.assertRaisesRegex(RuntimeError, "product-db"):
            puertos.validate_config(config)

    def test_foreign_publisher_blocks_before_any_mutation(self):
        items = inventory()
        items.append({"id": "foreign", "name": "/otro-proyecto", "project": "otro", "actual": {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8000"}]}})
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=items), patch.object(puertos, "network_state", return_value=None), patch.object(puertos, "docker") as docker:
            with self.assertRaisesRegex(RuntimeError, "otro-proyecto"):
                puertos.apply()
        docker.assert_not_called()

    def test_forbidden_socket_blocks_before_any_mutation(self):
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=inventory()), patch.object(puertos, "network_state", return_value=None), patch.object(puertos.socket, "socket", side_effect=PermissionError()), patch.object(puertos, "docker") as docker:
            with self.assertRaisesRegex(RuntimeError, "sockets denegados"):
                puertos.apply()
        docker.assert_not_called()

    def test_missing_requested_binding_requires_review_not_recreation(self):
        items = inventory()
        items[0]["requested"] = {}
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=items), patch.object(puertos, "docker") as docker:
            with self.assertRaisesRegex(RuntimeError, "autorizar"):
                puertos.apply()
        docker.assert_not_called()

    def test_foreign_network_is_never_reused(self):
        network = {"Name": puertos.NETWORK_NAME, "Driver": "bridge", "Internal": False, "Labels": {"com.docker.compose.project": "otro"}}
        with self.assertRaisesRegex(RuntimeError, "no pertenece"):
            puertos.validate_network(network)

    def test_apply_only_creates_network_and_connects_existing_ids(self):
        before = inventory()
        after = deepcopy(before)
        for item in after:
            item["networks"][puertos.NETWORK_NAME] = {}
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", side_effect=[before, after]), patch.object(puertos, "network_state", return_value=None), patch.object(puertos.socket, "socket"), patch.object(puertos, "docker") as docker, contextlib.redirect_stdout(io.StringIO()):
            puertos.apply()
        operations = [call.args[:2] for call in docker.call_args_list]
        self.assertEqual(operations, [("network", "create"), ("network", "connect"), ("network", "connect"), ("network", "connect")])
        self.assertEqual({call.args[-1] for call in docker.call_args_list[1:]}, {item["id"] for item in before})

    def test_zero_runtime_publication_fails_before_http(self):
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=inventory()), patch.object(puertos, "get_http") as http:
            with self.assertRaisesRegex(RuntimeError, "NetworkSettings.Ports"):
                puertos.verify()
        http.assert_not_called()

    def test_compose_port_zero_is_not_reported_as_success(self):
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=inventory(True)), patch.object(puertos.infra, "compose", return_value=":0"), patch.object(puertos, "get_http") as http:
            with self.assertRaisesRegex(RuntimeError, ":0"):
                puertos.verify()
        http.assert_not_called()

    def test_verification_requires_all_real_mappings_and_http_contracts(self):
        output = io.StringIO()
        responses = [(200, {"estado": "ok"}), (200, {"nombre": "test", "alias": "champion", "version": "1"}), (200, None), (200, {})]
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=inventory(True)), patch.object(puertos.infra, "compose", side_effect=lambda _, service, port: f"127.0.0.1:{port}"), patch.object(puertos, "get_http", side_effect=responses) as http, contextlib.redirect_stdout(output):
            puertos.verify()
        result = json.loads(output.getvalue())
        self.assertEqual(len(result["publicaciones"]), 3)
        self.assertEqual(http.call_count, 4)

    def test_http_failure_produces_no_success_report(self):
        output = io.StringIO()
        with patch.object(puertos.infra, "configuration", return_value=configuration()), patch.object(puertos, "containers", return_value=inventory(True)), patch.object(puertos.infra, "compose", side_effect=lambda _, service, port: f"127.0.0.1:{port}"), patch.object(puertos, "get_http", return_value=(503, {})), contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                puertos.verify()
        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
