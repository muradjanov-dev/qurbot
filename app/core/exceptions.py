class QurBotException(Exception):
    """Base exception for all QurBot errors."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DomainException(QurBotException):
    """Base exception for pure domain business logic errors."""


class UnknownUnitError(DomainException):
    """Raised when an unrecognized unit code is encountered."""

    def __init__(self, unit: str) -> None:
        super().__init__(f"Unknown unit code: '{unit}'")
        self.unit = unit


class IncompatibleUnitsError(DomainException):
    """Raised when attempting cross-dimension comparison or conversion (e.g. kg vs m2)."""

    def __init__(self, from_unit: str, to_unit: str, from_dim: str, to_dim: str) -> None:
        super().__init__(
            f"Cannot convert '{from_unit}' ({from_dim}) to '{to_unit}' ({to_dim}): "
            "incompatible dimensions"
        )
        self.from_unit = from_unit
        self.to_unit = to_unit
        self.from_dim = from_dim
        self.to_dim = to_dim


class ParsingError(DomainException):
    """Raised when parsing fails."""


class OptimizationError(DomainException):
    """Raised when basket optimization cannot produce a valid quote."""
