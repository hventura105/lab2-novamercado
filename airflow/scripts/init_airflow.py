"""Inicialización idempotente para Airflow 3, sin crear DAGs."""

import json
import os
from pathlib import Path
import subprocess


def main():
    # Volúmenes nombrados: no cambiar permisos de directorios de otros proyectos.
    if os.getuid() == 0:
        os.setgid(0)
        os.setuid(50000)
    os.umask(0o077)
    password_file = Path(os.environ["AIRFLOW__CORE__SIMPLE_AUTH_MANAGER_PASSWORDS_FILE"])
    username = os.environ["AIRFLOW_ADMIN_USER"]
    if password_file.exists():
        passwords = json.loads(password_file.read_text())
        if passwords.get(username) != os.environ["AIRFLOW_ADMIN_PASSWORD"]:
            raise RuntimeError("La contraseña persistida difiere de .env; revisar antes de cambiarla")
    else:
        with password_file.open("x") as file:
            json.dump({username: os.environ["AIRFLOW_ADMIN_PASSWORD"]}, file)
    subprocess.run(["airflow", "db", "migrate"], check=True)
    print("Migraciones completadas y autenticación persistente preparada.")


if __name__ == "__main__":
    main()
