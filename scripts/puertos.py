#!/usr/bin/env python3
"""Reparación limitada a publicación: inspeccionar, comprobar y conectar; nunca recrear."""

import argparse
import json
from pathlib import Path
import socket
import sys
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import infra

TARGETS = {"api": 8000, "mlflow": 5000, "airflow-api-server": 8080}
NETWORK = "publicacion"
NETWORK_NAME = infra.PROJECT + "_" + NETWORK
NAT_OPTION = "com.docker.network.bridge.gateway_mode_ipv4"
INSPECT = ('{"id":{{json .Id}},"name":{{json .Name}},'
           '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
           '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
           '"requested":{{json .HostConfig.PortBindings}},"actual":{{json .NetworkSettings.Ports}},'
           '"networks":{{json .NetworkSettings.Networks}},"running":{{json .State.Running}}}')


def docker(*arguments):
    return infra.execute(["docker", *arguments])


def containers():
    identifiers = docker("ps", "--quiet").split()
    if not identifiers:
        return []
    # El template excluye Config.Env, por lo que no se leen ni imprimen secretos.
    return [json.loads(line) for line in docker("inspect", "--type", "container", "--format", INSPECT, *identifiers).splitlines()]


def network_state():
    identifiers = docker("network", "ls", "--filter", "name=^" + NETWORK_NAME + "$", "--quiet").split()
    if not identifiers:
        return None
    if len(identifiers) != 1:
        raise RuntimeError("Nombre de red ambiguo; no se modifica nada")
    return json.loads(docker("network", "inspect", "--format", "{{json .}}", identifiers[0]))


def validate_config(config):
    if config.get("name") != infra.PROJECT:
        raise RuntimeError("Proyecto inesperado")
    networks = config.get("networks", {})
    if not networks.get("internal", {}).get("internal"):
        raise RuntimeError("La red interna debe permanecer privada")
    public = networks.get(NETWORK, {})
    if public.get("name") != NETWORK_NAME or public.get("driver") != "bridge" or public.get("internal", False):
        raise RuntimeError("Se requiere el bridge de publicación propio del proyecto, no interno")
    if public.get("driver_opts", {}).get(NAT_OPTION) != "nat":
        raise RuntimeError("El bridge de publicación debe usar NAT, no routed/isolated")
    for service, settings in config["services"].items():
        if settings.get("network_mode") == "host":
            raise RuntimeError("No se admite network_mode: host; conservar DNS y redes Docker")
        if service not in TARGETS:
            if settings.get("ports") or NETWORK in settings.get("networks", {}):
                raise RuntimeError(f"{service} debe conservarse sin publicación ni red de publicación")
            continue
        ports = settings.get("ports", [])
        expected = TARGETS[service]
        if len(ports) != 1 or ports[0].get("host_ip") != "127.0.0.1" or ports[0].get("target") != expected or str(ports[0].get("published")) != str(expected):
            raise RuntimeError(f"{service}: se exige 127.0.0.1:{expected} → {expected}; revisar variables HOST_PORT sin imprimir .env")
        if ports[0].get("protocol") != "tcp":
            raise RuntimeError(f"{service}: publicación TCP explícita requerida")
        if set(settings.get("networks", {})) != {"internal", NETWORK}:
            raise RuntimeError(f"{service}: conservar red interna y agregar solo publicación")
    if not set(TARGETS) <= set(config["services"]):
        raise RuntimeError("Faltan servicios del proyecto")


def validate_network(network):
    if network is None:
        return
    labels = network.get("Labels") or {}
    if network.get("Name") != NETWORK_NAME or labels.get("com.docker.compose.project") != infra.PROJECT or labels.get("com.docker.compose.network") != NETWORK:
        raise RuntimeError("La red con ese nombre no pertenece a este proyecto; no se utiliza ni modifica")
    if network.get("Driver") != "bridge" or network.get("Internal") or (network.get("Options") or {}).get(NAT_OPTION, "nat") != "nat":
        raise RuntimeError("La red existente no es un bridge NAT compatible; no se elimina ni reemplaza")


def binding_matches(bindings, port):
    return bindings == [{"HostIp": "127.0.0.1", "HostPort": str(port)}]


def selected(items, config):
    result = {}
    internal_name = config["networks"]["internal"]["name"]
    for service, port in TARGETS.items():
        matches = [item for item in items if item.get("project") == infra.PROJECT and item.get("service") == service]
        if len(matches) != 1 or not matches[0].get("running"):
            raise RuntimeError(f"{service}: se requiere exactamente un contenedor propio en ejecución; no se arranca ni recrea automáticamente")
        item = matches[0]
        if internal_name not in (item.get("networks") or {}):
            raise RuntimeError(f"{service}: no está conectado a la red interna esperada; detener reparación para revisar")
        if not binding_matches((item.get("requested") or {}).get(f"{port}/tcp"), port):
            raise RuntimeError(f"{service}: HostConfig.PortBindings no solicita 127.0.0.1:{port}. Conectar una red no corrige ese caso; se requiere revisar y autorizar una recreación selectiva. No se recreó nada")
        result[service] = item
    for item in items:
        if item.get("project") == infra.PROJECT and item.get("service") in ("product-db", "airflow-db"):
            if any(value for value in (item.get("actual") or {}).values()):
                raise RuntimeError("PostgreSQL ya tiene publicaciones inesperadas; revisar sin modificarlo")
    return result


def check_availability(items, own):
    for service, port in TARGETS.items():
        for item in items:
            for bindings in (item.get("actual") or {}).values():
                for binding in bindings or []:
                    if binding.get("HostPort") == str(port) and binding.get("HostIp", "") in ("", "0.0.0.0", "::", "127.0.0.1") and item["id"] != own[service]["id"]:
                        raise RuntimeError(f"Conflicto: 127.0.0.1:{port} publicado por {item['name']}. No se detiene ni modifica ese contenedor; solicitar autorización si fuera necesario detenerlo")
        if binding_matches((own[service].get("actual") or {}).get(f"{port}/tcp"), port):
            print(f"OK {port}: ya publicado por {infra.PROJECT}/{service}")
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(("127.0.0.1", port))
        except PermissionError:
            raise RuntimeError(f"No se puede comprobar disponibilidad de {port}: sockets denegados. No aplicar cambios desde esta sesión") from None
        except OSError:
            raise RuntimeError(f"127.0.0.1:{port} no disponible. Revisar ss/Get-NetTCPConnection e identificar propietario antes de continuar; no se detuvo ningún servicio") from None
        print(f"OK {port}: disponible en Ubuntu y sin otro publicador Docker detectado")


def preflight():
    config = infra.configuration()
    validate_config(config)
    items = containers()
    own = selected(items, config)
    network = network_state()
    validate_network(network)
    check_availability(items, own)
    print("Preflight completo; ninguna mutación Docker ejecutada.")
    return config, own, network


def diagnose():
    config = infra.configuration()
    validate_config(config)
    items = containers()
    own = [item for item in items if item.get("project") == infra.PROJECT]
    network = network_state()
    print(json.dumps({"version_motor": docker("version", "--format", "{{.Server.Version}}").strip(),
        "configuracion": {name: config["services"][name]["ports"] for name in TARGETS},
        "contenedores": own, "red_publicacion": None if network is None else {key: network.get(key) for key in ("Name", "Driver", "Internal", "Options", "Labels")}}, indent=2))


def apply():
    config, own, network = preflight()  # Comprobar TODO antes de la primera mutación.
    if network is None:
        docker("network", "create", "--driver", "bridge", "--opt", NAT_OPTION + "=nat",
               "--label", "com.docker.compose.project=" + infra.PROJECT,
               "--label", "com.docker.compose.network=" + NETWORK, NETWORK_NAME)
        print("Creado únicamente el bridge de publicación del laboratorio.")
    for service, item in own.items():
        if NETWORK_NAME not in (item.get("networks") or {}):
            docker("network", "connect", "--alias", service, NETWORK_NAME, item["id"])
            print(f"Conectado {service} al bridge de publicación, conservando su red interna.")
    # IDs no cambian: no se elimina, recrea, reinicia o construye ningún contenedor.
    refreshed = selected(containers(), config)
    if any(refreshed[name]["id"] != own[name]["id"] for name in TARGETS):
        raise RuntimeError("Cambió un contenedor concurrentemente; revisar antes de declarar éxito")
    if any(NETWORK_NAME not in (item.get("networks") or {}) for item in refreshed.values()):
        raise RuntimeError("Una conexión de publicación no quedó registrada; verificar antes de continuar")
    print("Conexiones aplicadas sin recrear contenedores. Falta verificar mappings y HTTP.")


def get_http(url):
    # No pasar por proxies del entorno: probar localhost realmente.
    with build_opener(ProxyHandler({})).open(url, timeout=5) as response:
        body = response.read(65536)
        return response.status, json.loads(body) if "application/json" in response.headers.get("Content-Type", "") else None


def verify():
    config = infra.configuration()
    validate_config(config)
    own = selected(containers(), config)
    results = {"publicaciones": {}, "http": {}}
    for service, port in TARGETS.items():
        if not binding_matches((own[service].get("actual") or {}).get(f"{port}/tcp"), port):
            raise RuntimeError(f"{service}: NetworkSettings.Ports aún no contiene 127.0.0.1:{port}; no se declara resuelto")
        mapping = infra.compose("port", service, str(port)).strip()
        if mapping != f"127.0.0.1:{port}":
            raise RuntimeError(f"{service}: docker compose port devolvió {mapping!r}, no el binding esperado")
        results["publicaciones"][service] = mapping
    endpoints = ((8000, "/health"), (8000, "/modelo"), (5000, "/health"), (8080, "/api/v2/monitor/health"))
    for port, path in endpoints:
        code, body = get_http(f"http://127.0.0.1:{port}{path}")
        if code != 200:
            raise RuntimeError(f"{port}{path}: HTTP {code}; no se declara resuelto")
        if port == 8000 and path == "/health" and (not isinstance(body, dict) or body.get("estado") not in ("ok", "degradado")):
            raise RuntimeError("/health no tiene una respuesta de contrato válida")
        if path == "/modelo" and (not isinstance(body, dict) or any(not isinstance(body.get(key), str) or not body[key] for key in ("nombre", "alias", "version"))):
            raise RuntimeError("/modelo no confirmó un modelo cargado")
        results["http"][f"{port}{path}"] = {"status": code, "body": body if port == 8000 else None}
    print(json.dumps(results, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnostico", "preflight", "aplicar", "verificar"))
    arguments = parser.parse_args()
    try:
        {"diagnostico": diagnose, "preflight": preflight, "aplicar": apply, "verificar": verify}[arguments.action]()
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
