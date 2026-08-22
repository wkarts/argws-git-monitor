from __future__ import annotations

from typing import Any, TypeVar


class SSHHostKeyError(RuntimeError):
    """Raised when SSH host-key verification cannot be configured safely."""


E = TypeVar("E", bound=RuntimeError)


def configure_ssh_host_keys(
    client: Any,
    paramiko: Any,
    *,
    config: dict[str, Any] | None,
    secret: dict[str, Any] | None,
    error_type: type[E] = SSHHostKeyError,
) -> None:
    """Configure strict SSH host-key verification.

    Unknown host keys are never accepted automatically. Trusted keys can come
    from the container/system known_hosts, an explicit known_hosts file, or
    inline OpenSSH known_hosts entries. Inline entries may be stored inside the
    encrypted secret payload so they do not need to exist on the filesystem.
    """

    config = config or {}
    secret = secret or {}

    if bool(config.get("allow_unknown_host_key", False)):
        raise error_type(
            "A opção allow_unknown_host_key não é permitida. "
            "Cadastre a chave do host em known_hosts antes de conectar."
        )

    client.load_system_host_keys()

    known_hosts_file = str(config.get("known_hosts_file") or "").strip()
    if known_hosts_file:
        try:
            client.load_host_keys(known_hosts_file)
        except (OSError, ValueError) as exc:
            raise error_type("Não foi possível carregar o arquivo known_hosts configurado.") from exc

    inline_known_hosts = str(
        secret.get("known_hosts") or config.get("known_hosts") or ""
    ).strip()
    if inline_known_hosts:
        loaded = 0
        for raw_line in inline_known_hosts.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                entry = paramiko.hostkeys.HostKeyEntry.from_line(line)
            except Exception as exc:  # pragma: no cover - implementação Paramiko
                raise error_type("Entrada known_hosts inválida.") from exc
            if entry is None or entry.key is None or not entry.hostnames:
                raise error_type("Entrada known_hosts inválida.")
            for hostname in entry.hostnames:
                client.get_host_keys().add(hostname, entry.key.get_name(), entry.key)
                loaded += 1
        if loaded == 0:
            raise error_type("Nenhuma chave SSH válida foi encontrada em known_hosts.")

    # Segurança obrigatória: nunca usar AutoAddPolicy/WarningPolicy em produção.
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
