"""
Custom exception classes for the bot.
Separated from error handler to avoid circular imports and ensure proper isinstance checks.
This file must exist for the error handler to work correctly.

All exceptions support rich context for structured logging and debugging.
"""

from typing import Optional, Dict, Any, Union


class BaseBotException(Exception):
    """
    Base exception for all bot exceptions.
    Provides rich context for structured logging.
    """

    def __init__(
        self,
        message: str,
        *,
        context: Optional[Dict[str, Any]] = None,
        original: Optional[Exception] = None
    ):
        """
        Initialize the exception with rich context.

        Args:
            message: Human-readable error message
            context: Dictionary of structured context data (query, user_id, etc.)
            original: Original exception that caused this one (for chaining)
        """
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.original = original

    def __str__(self) -> str:
        """String representation with context."""
        base = self.message
        if self.context:
            context_str = " | ".join(
                f"{k}={v}" for k, v in self.context.items())
            base = f"{base} | {context_str}"
        if self.original:
            base = f"{base} (caused by: {type(self.original).__name__}: {self.original})"
        return base

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for structured logging."""
        result = {
            'exception_type': self.__class__.__name__,
            'message': self.message,
            'context': self.context
        }
        if self.original:
            result['original'] = {
                'type': type(self.original).__name__,
                'message': str(self.original)
            }
        return result


# Database Exceptions
class DatabaseError(BaseBotException):
    """Base exception for database errors."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when database connection fails."""
    pass


class DatabaseQueryError(DatabaseError):
    """Raised when a database query fails."""
    pass


class DatabaseTransactionError(DatabaseError):
    """Raised when a database transaction fails."""
    pass


class DatabaseIntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated."""
    pass


class DatabaseTimeoutError(DatabaseError):
    """Raised when a database operation times out."""
    pass


# Cache Exceptions
class CacheError(BaseBotException):
    """Base exception for cache errors."""
    pass


class CacheConnectionError(CacheError):
    """Raised when cache connection fails."""
    pass


class CacheReadFailed(CacheError):
    """Raised when cache read operation fails."""
    pass


class CacheWriteFailed(CacheError):
    """Raised when cache write operation fails."""
    pass


class CacheDeleteFailed(CacheError):
    """Raised when cache delete operation fails."""
    pass


class CacheBatchFailed(CacheError):
    """
    Raised when a cache batch operation fails.

    Example context:
        operation: 'mget' or 'mset'
        keys: ['user:1', 'user:2']
        failed_keys: ['user:2']
    """
    pass


class CacheKeyNotFound(CacheError):
    """
    Raised when a key is not found in cache.
    Note: This should only be raised when a key is required but missing,
    not for normal cache misses in batch operations.
    """
    pass


class CacheTimeoutError(CacheError):
    """Raised when a cache operation times out."""
    pass


class CacheSerializationError(CacheError):
    """Raised when serialization/deserialization fails."""
    pass


# Validation Exceptions
class ValidationError(BaseBotException):
    """Base exception for validation errors."""
    pass


class MissingArgumentError(ValidationError):
    """
    Raised when a required argument is missing.

    Example context:
        argument: 'user_id'
        command: 'profile'
    """
    pass


class InvalidArgumentError(ValidationError):
    """
    Raised when an argument is invalid.

    Example context:
        argument: 'limit'
        value: 'abc'
        expected_type: 'int'
    """
    pass


class PermissionError(ValidationError):
    """
    Raised when a user lacks required permissions.

    Example context:
        user_id: 12345
        required_permission: 'administrator'
        command: 'ban'
    """
    pass


# External API Exceptions
class ExternalAPIError(BaseBotException):
    """
    Base exception for external API errors.

    Example context:
        api: 'discord'
        endpoint: '/users/{user_id}'
        status_code: 429
        retry_after: 30
    """
    pass


class ExternalAPITimeoutError(ExternalAPIError):
    """Raised when an external API request times out."""
    pass


class ExternalAPIRateLimitError(ExternalAPIError):
    """Raised when an external API rate limit is hit."""
    pass


# Business Logic Exceptions
class BusinessLogicError(BaseBotException):
    """Base exception for business logic errors."""
    pass


class InsufficientFundsError(BusinessLogicError):
    """
    Raised when a user has insufficient funds for an operation.

    Example context:
        user_id: 12345
        required: 100
        balance: 50
        currency: 'coins'
    """
    pass


class CooldownError(BusinessLogicError):
    """
    Raised when a command is on cooldown.

    Example context:
        command: 'daily'
        user_id: 12345
        remaining_seconds: 3600
    """
    pass
