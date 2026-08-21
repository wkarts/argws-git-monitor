from app.services.github_client import GitHubAPIError
from app.services.repository_compliance import (
    classify_access_error,
    deletion_confirmation,
    normalize_full_name,
    validate_personal_owner,
)


def test_normalize_repository_full_name() -> None:
    assert normalize_full_name(" wkarts/projeto ") == "wkarts/projeto"


def test_reject_invalid_repository_full_name() -> None:
    try:
        normalize_full_name("apenas-um-nome")
    except ValueError as exc:
        assert "owner/repo" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Nome inválido deveria ser rejeitado")


def test_personal_owner_must_match_connection_login() -> None:
    validate_personal_owner("WKARTS/projeto", "wkarts")
    try:
        validate_personal_owner("outra-conta/projeto", "wkarts")
    except PermissionError as exc:
        assert "própria conta" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Owner diferente deveria ser rejeitado")


def test_dmca_451_is_classified_as_legal_restriction() -> None:
    status = classify_access_error(
        "wkarts/projeto",
        "wkarts",
        GitHubAPIError("Unavailable For Legal Reasons", status_code=451),
    )
    assert status.status == "legal_restriction"
    assert status.http_status == 451
    assert status.restricted is True
    assert status.accessible is False


def test_not_visible_can_still_be_offered_for_delete_attempt() -> None:
    status = classify_access_error(
        "wkarts/projeto",
        "wkarts",
        GitHubAPIError("Not Found", status_code=404),
    )
    assert status.status == "not_visible"
    assert "DELETE" in status.message


def test_delete_confirmation_is_explicit() -> None:
    assert deletion_confirmation("wkarts/projeto") == "EXCLUIR wkarts/projeto"
