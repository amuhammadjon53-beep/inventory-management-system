"""
Global error handler for Discord.py bot.
Handles errors for both prefix commands and slash commands with proper error codes.
Features structured logging, error metrics tracking, and production-ready error handling.
"""

from exceptions import (
    DatabaseConnectionError, DatabaseQueryError, DatabaseTransactionError,
    DatabaseIntegrityError, DatabaseTimeoutError,
    CacheConnectionError, CacheReadFailed, CacheWriteFailed,
    CacheDeleteFailed, CacheBatchFailed, CacheKeyNotFound,
    CacheTimeoutError, CacheSerializationError,
    ValidationError, MissingArgumentError, InvalidArgumentError,
    ExternalAPIError, ExternalAPITimeoutError, ExternalAPIRateLimitError
)
import asyncio
import io
import logging
import traceback
import time
import uuid
from typing import Union, Optional, Dict, Any, List, Tuple
from collections import defaultdict, deque, Counter
from datetime import datetime, timedelta
import discord
from discord.ext import commands
from discord import app_commands
import sys
import os
from pathlib import Path

root_dir = Path(__file__).parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
try:
    from pythonjsonlogger import jsonlogger

    class StackdriverJsonFormatter(jsonlogger.JsonFormatter):
        """Custom JSON formatter that ensures all fields are included."""

        def process_log_record(self, log_record):
            log_record['severity'] = log_record.get('levelname', 'INFO')
            log_record['timestamp'] = log_record.get('asctime')
            return log_record

    log_handler = logging.StreamHandler()
    formatter = StackdriverJsonFormatter(
        fmt='%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s %(error_code)s %(error_name)s %(command_name)s'
    )
    log_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[log_handler])
except ImportError:
    # Fallback to basic formatting if json-logger not installed
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
    )

logger = logging.getLogger(__name__)


# Error Code Enum for standardized error handling
class ErrorCode:
    """Centralized error codes for the bot."""

    # Discord API Errors (100-199)
    DISCORD_FORBIDDEN = 101
    DISCORD_NOT_FOUND = 102
    DISCORD_HTTP_EXCEPTION = 103
    DISCORD_INVALID_DATA = 104
    DISCORD_RATE_LIMIT = 106
    DISCORD_UNAUTHORIZED = 107
    DISCORD_CONNECTION = 108

    # Database Errors (200-299)
    DB_CONNECTION_ERROR = 201
    DB_QUERY_ERROR = 202
    DB_TRANSACTION_ERROR = 203
    DB_INTEGRITY_ERROR = 204
    DB_TIMEOUT_ERROR = 205

    # External API Errors (300-399)
    EXTERNAL_API_ERROR = 301
    EXTERNAL_API_TIMEOUT = 302
    EXTERNAL_API_RATE_LIMIT = 303

    # Validation/Logic Errors (400-499)
    VALIDATION_ERROR = 401
    MISSING_ARGUMENT = 402
    INVALID_ARGUMENT = 403
    PERMISSION_ERROR = 404
    COOLDOWN_ERROR = 405
    MAX_CONCURRENCY_ERROR = 406
    NOT_OWNER_ERROR = 407
    COMMAND_NOT_FOUND = 408
    DISABLED_COMMAND = 409
    CHECK_FAILURE = 410
    PROGRAMMING_ERROR = 411  # New category for Python errors

    # Cache Errors (700-799)
    CACHE_CONNECTION_ERROR = 701
    CACHE_READ_FAILED = 702
    CACHE_WRITE_FAILED = 703
    CACHE_DELETE_FAILED = 704
    CACHE_BATCH_FAILED = 705
    CACHE_KEY_NOT_FOUND = 706
    CACHE_TIMEOUT_ERROR = 707
    CACHE_SERIALIZATION_ERROR = 708

    # Generic/Unknown Errors (500-599)
    GENERIC_ERROR = 500
    UNKNOWN_ERROR = 501

    # Severity mapping (semantic, not range-based)
    SEVERITY_MAP = {
        # Discord errors (mostly warnings)
        DISCORD_FORBIDDEN: "WARNING",
        DISCORD_NOT_FOUND: "WARNING",
        DISCORD_HTTP_EXCEPTION: "ERROR",
        DISCORD_INVALID_DATA: "ERROR",
        DISCORD_RATE_LIMIT: "WARNING",
        DISCORD_UNAUTHORIZED: "WARNING",
        DISCORD_CONNECTION: "ERROR",

        # Database errors (critical)
        DB_CONNECTION_ERROR: "CRITICAL",
        DB_QUERY_ERROR: "ERROR",
        DB_TRANSACTION_ERROR: "ERROR",
        DB_INTEGRITY_ERROR: "ERROR",
        DB_TIMEOUT_ERROR: "ERROR",

        # External API errors
        EXTERNAL_API_ERROR: "ERROR",
        EXTERNAL_API_TIMEOUT: "ERROR",
        EXTERNAL_API_RATE_LIMIT: "WARNING",

        # Validation errors (user errors, warnings)
        VALIDATION_ERROR: "WARNING",
        MISSING_ARGUMENT: "WARNING",
        INVALID_ARGUMENT: "WARNING",
        PERMISSION_ERROR: "WARNING",
        COOLDOWN_ERROR: "WARNING",
        MAX_CONCURRENCY_ERROR: "WARNING",
        NOT_OWNER_ERROR: "WARNING",
        COMMAND_NOT_FOUND: "DEBUG",
        DISABLED_COMMAND: "WARNING",
        CHECK_FAILURE: "DEBUG",
        PROGRAMMING_ERROR: "ERROR",

        # Cache errors
        CACHE_CONNECTION_ERROR: "ERROR",
        CACHE_READ_FAILED: "WARNING",
        CACHE_WRITE_FAILED: "WARNING",
        CACHE_DELETE_FAILED: "WARNING",
        CACHE_BATCH_FAILED: "ERROR",
        CACHE_KEY_NOT_FOUND: "DEBUG",
        CACHE_TIMEOUT_ERROR: "WARNING",
        CACHE_SERIALIZATION_ERROR: "ERROR",

        # Generic
        GENERIC_ERROR: "ERROR",
        UNKNOWN_ERROR: "CRITICAL",
    }

    @classmethod
    def get_message(cls, code: int) -> str:
        """Get user-friendly message for error code."""
        messages = {
            cls.DISCORD_FORBIDDEN: "I don't have permission to do that.",
            cls.DISCORD_NOT_FOUND: "The requested resource was not found.",
            cls.DISCORD_HTTP_EXCEPTION: "Discord API request failed.",
            cls.DISCORD_INVALID_DATA: "Received invalid data from Discord.",
            cls.DISCORD_RATE_LIMIT: "Too many requests. Please wait a moment.",
            cls.DISCORD_UNAUTHORIZED: "This action requires higher permissions.",
            cls.DISCORD_CONNECTION: "Connection to Discord was interrupted.",

            cls.DB_CONNECTION_ERROR: "Database connection failed.",
            cls.DB_QUERY_ERROR: "Database query failed.",
            cls.DB_TRANSACTION_ERROR: "Database transaction failed.",
            cls.DB_INTEGRITY_ERROR: "Database integrity error.",
            cls.DB_TIMEOUT_ERROR: "Database operation timed out.",

            cls.EXTERNAL_API_ERROR: "External API request failed.",
            cls.EXTERNAL_API_TIMEOUT: "External API request timed out.",
            cls.EXTERNAL_API_RATE_LIMIT: "External API rate limit reached.",

            cls.VALIDATION_ERROR: "Invalid input provided.",
            cls.MISSING_ARGUMENT: "Missing required argument.",
            cls.INVALID_ARGUMENT: "Invalid argument provided.",
            cls.PERMISSION_ERROR: "You don't have permission to use this command.",
            cls.COOLDOWN_ERROR: "Command is on cooldown.",
            cls.MAX_CONCURRENCY_ERROR: "Too many instances of this command running.",
            cls.NOT_OWNER_ERROR: "This command is bot owner only.",
            cls.COMMAND_NOT_FOUND: "Command not found.",
            cls.DISABLED_COMMAND: "This command is currently disabled.",
            cls.CHECK_FAILURE: "You don't meet the requirements to use this command.",
            cls.PROGRAMMING_ERROR: "An internal error occurred. The developers have been notified.",

            cls.CACHE_CONNECTION_ERROR: "Cache service connection failed.",
            cls.CACHE_READ_FAILED: "Failed to read from cache.",
            cls.CACHE_WRITE_FAILED: "Failed to write to cache.",
            cls.CACHE_DELETE_FAILED: "Failed to delete from cache.",
            cls.CACHE_BATCH_FAILED: "Cache batch operation failed.",
            cls.CACHE_KEY_NOT_FOUND: "Requested data not found in cache.",
            cls.CACHE_TIMEOUT_ERROR: "Cache operation timed out.",
            cls.CACHE_SERIALIZATION_ERROR: "Failed to serialize/deserialize cache data.",

            cls.GENERIC_ERROR: "An unexpected error occurred.",
            cls.UNKNOWN_ERROR: "An unknown error occurred.",
        }
        return messages.get(code, "An unknown error occurred.")

    @classmethod
    def get_severity(cls, code: int) -> str:
        """Get semantic severity level for error code."""
        return cls.SEVERITY_MAP.get(code, "ERROR")

    @classmethod
    def get_name(cls, code: int) -> str:
        """Get the constant name for an error code."""
        if not hasattr(cls, '_name_map'):
            # Build name map lazily on first access
            cls._name_map = {
                v: k for k, v in vars(cls).items()
                if isinstance(v, int) and not k.startswith('_') and k != 'SEVERITY_MAP'
            }
        return cls._name_map.get(code, f"UNKNOWN_{code}")


class TimeWindowedCounter:
    """
    Counter that tracks events within a sliding time window.
    Used for accurate alerting based on recent error frequency.
    Thread-safe for async operations with proper lock handling.
    """

    def __init__(self, window_minutes: int = 5):
        self.window_minutes = window_minutes
        self.events: Dict[int, deque] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def increment(self, error_code: int) -> int:
        """
        Increment counter for an error code and return current count.

        Args:
            error_code: The error code to increment

        Returns:
            int: Current count within the time window
        """
        async with self._lock:
            now = datetime.utcnow()
            window_start = now - timedelta(minutes=self.window_minutes)

            # Add new event
            self.events[error_code].append(now)

            # Prune old events
            while self.events[error_code] and self.events[error_code][0] < window_start:
                self.events[error_code].popleft()

            return len(self.events[error_code])

    async def get_count(self, error_code: int) -> int:
        """Get current count for an error code within the time window."""
        async with self._lock:
            if error_code not in self.events:
                return 0

            now = datetime.utcnow()
            window_start = now - timedelta(minutes=self.window_minutes)

            # Prune old events on read
            while self.events[error_code] and self.events[error_code][0] < window_start:
                self.events[error_code].popleft()

            return len(self.events[error_code])

    async def get_all_counts(self) -> Dict[int, int]:
        """
        Get all current counts with proper pruning.
        Fixed: No nested lock calls to prevent deadlocks.
        """
        async with self._lock:
            result = {}
            now = datetime.utcnow()
            window_start = now - timedelta(minutes=self.window_minutes)

            # Process each error code
            for code, timestamps in list(self.events.items()):
                # Prune old events
                while timestamps and timestamps[0] < window_start:
                    timestamps.popleft()

                # Add to result if there are events
                if timestamps:
                    result[code] = len(timestamps)
                elif not timestamps:
                    # Clean up empty deques
                    del self.events[code]

            return result

    def reset(self):
        """Reset all counters (sync version for non-async contexts)."""
        self.events.clear()


class ErrorMetrics:
    """Advanced error metrics tracker with time windowing."""

    def __init__(self, window_minutes: int = 5):
        self.window_minutes = window_minutes
        self.counter = TimeWindowedCounter(window_minutes)
        self.total_counts = Counter()
        self.last_reset = datetime.utcnow()

    async def increment(self, error_code: int) -> Tuple[int, int]:
        """
        Increment counters and return (window_count, total_count).

        Args:
            error_code: The error code to increment

        Returns:
            Tuple[int, int]: (count in current window, total lifetime count)
        """
        window_count = await self.counter.increment(error_code)
        self.total_counts[error_code] += 1
        return window_count, self.total_counts[error_code]

    async def get_window_count(self, error_code: int) -> int:
        """Get count within current time window."""
        return await self.counter.get_count(error_code)

    def get_total_count(self, error_code: int) -> int:
        """Get total lifetime count."""
        return self.total_counts[error_code]

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics."""
        return {
            'window_minutes': self.window_minutes,
            'window_counts': await self.counter.get_all_counts(),
            'total_counts': dict(self.total_counts),
            'last_reset': self.last_reset.isoformat(),
            'unique_error_types': len(self.total_counts)
        }

    async def should_alert(self, error_code: int, threshold: int = 10) -> bool:
        """
        Check if error frequency exceeds alert threshold within the time window.

        Args:
            error_code: The error code to check
            threshold: Number of occurrences to trigger alert

        Returns:
            bool: True if alert should be triggered
        """
        count = await self.get_window_count(error_code)
        return count >= threshold

    def reset(self):
        """Reset all counters."""
        self.counter.reset()
        self.total_counts.clear()
        self.last_reset = datetime.utcnow()


class ErrorHandler(commands.Cog):
    """
    Global error handler cog for both prefix and slash commands.
    Handles exceptions and displays user-friendly messages with error codes.
    Includes metrics tracking and structured logging.
    """

    def __init__(self, bot: commands.Bot, alert_threshold: int = 10, window_minutes: int = 5):
        self.bot = bot
        self.metrics = ErrorMetrics(window_minutes=window_minutes)
        self.alert_threshold = alert_threshold
        self.window_minutes = window_minutes
        self._alert_cooldown = {}  # Prevent alert storms
        self._alert_cooldown_minutes = 15

    def _unwrap_error(self, error: Exception) -> Exception:
        """
        Unwrap command invocation errors to get the original exception.

        Args:
            error: The error to unwrap

        Returns:
            Exception: The unwrapped error
        """
        # Handle prefix command wrapping
        if isinstance(error, commands.CommandInvokeError):
            return error.original

        # Handle slash command wrapping
        if isinstance(error, app_commands.CommandInvokeError):
            return error.original

        return error

    def _should_ignore_error(self, error: Exception) -> bool:
        """
        Determine if an error should be ignored (not logged or sent to user).

        Args:
            error: The error to check

        Returns:
            bool: True if the error should be ignored
        """
        # Ignore check failures - these are expected permission denials
        if isinstance(error, (commands.CheckFailure, app_commands.CheckFailure)):
            return True

        # Ignore command not found - handled by help command, no message should be sent
        if isinstance(error, (commands.CommandNotFound, app_commands.CommandNotFound)):
            return True

        return False

    def _should_send_user_message(self, error_code: int) -> bool:
        """
        Determine if an error message should be sent to the user.

        Args:
            error_code: The error code to check

        Returns:
            bool: True if a user message should be sent
        """
        # Error codes that should NOT send messages to users
        silent_error_codes = {
            ErrorCode.COMMAND_NOT_FOUND,  # User typed wrong command
            # Permission checks (usually handled elsewhere)
            ErrorCode.CHECK_FAILURE,
        }

        return error_code not in silent_error_codes

    def get_error_code(self, error: Exception) -> int:
        """
        Maps exceptions to appropriate error codes.
        Note: Expects already-unwrapped errors.

        Args:
            error: The exception to map (should be unwrapped)

        Returns:
            int: Corresponding error code
        """
        # Discord API Errors
        if isinstance(error, discord.Forbidden):
            return ErrorCode.DISCORD_FORBIDDEN
        elif isinstance(error, discord.NotFound):
            return ErrorCode.DISCORD_NOT_FOUND
        elif isinstance(error, discord.HTTPException):
            # Check for specific HTTP status codes
            if hasattr(error, 'status'):
                if error.status == 429:
                    return ErrorCode.DISCORD_RATE_LIMIT
                elif error.status == 401:
                    return ErrorCode.DISCORD_UNAUTHORIZED
                elif error.status == 403:
                    return ErrorCode.DISCORD_FORBIDDEN
            return ErrorCode.DISCORD_HTTP_EXCEPTION
        elif isinstance(error, discord.InvalidData):
            return ErrorCode.DISCORD_INVALID_DATA
        elif isinstance(error, discord.errors.ConnectionClosed):
            return ErrorCode.DISCORD_CONNECTION

        # Database Errors
        elif isinstance(error, DatabaseConnectionError):
            return ErrorCode.DB_CONNECTION_ERROR
        elif isinstance(error, DatabaseQueryError):
            return ErrorCode.DB_QUERY_ERROR
        elif isinstance(error, DatabaseTransactionError):
            return ErrorCode.DB_TRANSACTION_ERROR
        elif isinstance(error, DatabaseIntegrityError):
            return ErrorCode.DB_INTEGRITY_ERROR
        elif isinstance(error, DatabaseTimeoutError):
            return ErrorCode.DB_TIMEOUT_ERROR

        # External API Errors
        elif isinstance(error, ExternalAPIError):
            return ErrorCode.EXTERNAL_API_ERROR
        elif isinstance(error, ExternalAPITimeoutError):
            return ErrorCode.EXTERNAL_API_TIMEOUT
        elif isinstance(error, ExternalAPIRateLimitError):
            return ErrorCode.EXTERNAL_API_RATE_LIMIT

        # Cache Errors
        elif isinstance(error, CacheConnectionError):
            return ErrorCode.CACHE_CONNECTION_ERROR
        elif isinstance(error, CacheReadFailed):
            return ErrorCode.CACHE_READ_FAILED
        elif isinstance(error, CacheWriteFailed):
            return ErrorCode.CACHE_WRITE_FAILED
        elif isinstance(error, CacheDeleteFailed):
            return ErrorCode.CACHE_DELETE_FAILED
        elif isinstance(error, CacheBatchFailed):
            return ErrorCode.CACHE_BATCH_FAILED
        elif isinstance(error, CacheKeyNotFound):
            return ErrorCode.CACHE_KEY_NOT_FOUND
        elif isinstance(error, CacheTimeoutError):
            return ErrorCode.CACHE_TIMEOUT_ERROR
        elif isinstance(error, CacheSerializationError):
            return ErrorCode.CACHE_SERIALIZATION_ERROR

        # Validation/Logic Errors
        elif isinstance(error, ValidationError):
            return ErrorCode.VALIDATION_ERROR
        elif isinstance(error, MissingArgumentError):
            return ErrorCode.MISSING_ARGUMENT
        elif isinstance(error, InvalidArgumentError):
            return ErrorCode.INVALID_ARGUMENT
        elif isinstance(error, commands.MissingRequiredArgument):
            return ErrorCode.MISSING_ARGUMENT
        elif isinstance(error, commands.BadArgument):
            return ErrorCode.INVALID_ARGUMENT
        elif isinstance(error, commands.MissingPermissions):
            return ErrorCode.PERMISSION_ERROR
        elif isinstance(error, commands.BotMissingPermissions):
            return ErrorCode.DISCORD_FORBIDDEN
        elif isinstance(error, commands.CommandOnCooldown):
            return ErrorCode.COOLDOWN_ERROR
        elif isinstance(error, commands.MaxConcurrencyReached):
            return ErrorCode.MAX_CONCURRENCY_ERROR
        elif isinstance(error, commands.NotOwner):
            return ErrorCode.NOT_OWNER_ERROR
        elif isinstance(error, commands.CommandNotFound):
            return ErrorCode.COMMAND_NOT_FOUND
        elif isinstance(error, commands.DisabledCommand):
            return ErrorCode.DISABLED_COMMAND
        elif isinstance(error, (commands.CheckFailure, app_commands.CheckFailure)):
            return ErrorCode.CHECK_FAILURE

        # Programming errors (Python built-in exceptions)
        elif isinstance(error, (TypeError, ValueError, AttributeError, KeyError, IndexError)):
            return ErrorCode.PROGRAMMING_ERROR

        # App Command specific errors
        elif isinstance(error, app_commands.CommandOnCooldown):
            return ErrorCode.COOLDOWN_ERROR
        elif isinstance(error, app_commands.MissingPermissions):
            return ErrorCode.PERMISSION_ERROR
        elif isinstance(error, app_commands.BotMissingPermissions):
            return ErrorCode.DISCORD_FORBIDDEN
        elif isinstance(error, app_commands.CommandNotFound):
            return ErrorCode.COMMAND_NOT_FOUND

        # Generic/Unknown
        else:
            return ErrorCode.UNKNOWN_ERROR

    async def _should_send_alert(self, error_code: int) -> bool:
        """
        Check if an alert should be sent with rate limiting.

        Args:
            error_code: The error code to check

        Returns:
            bool: True if alert should be sent
        """
        now = datetime.utcnow()

        # Check cooldown
        if error_code in self._alert_cooldown:
            last_alert = self._alert_cooldown[error_code]
            if (now - last_alert).total_seconds() < self._alert_cooldown_minutes * 60:
                return False

        # Check threshold
        if await self.metrics.should_alert(error_code, self.alert_threshold):
            self._alert_cooldown[error_code] = now
            return True

        return False

    async def handle_error(
        self,
        ctx_or_interaction: Union[commands.Context, discord.Interaction],
        error: Exception
    ) -> None:
        """
        Central error handling function with metrics and structured logging.

        Args:
            ctx_or_interaction: Either a commands.Context or discord.Interaction
            error: The exception that was raised
        """
        # Generate correlation ID for this error instance
        correlation_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Check if error should be ignored (no logging, no user message)
        if self._should_ignore_error(error):
            return

        # Unwrap the error first for clean handling
        error = self._unwrap_error(error)

        # Get error code and metadata
        error_code = self.get_error_code(error)
        error_name = ErrorCode.get_name(error_code)
        error_message = ErrorCode.get_message(error_code)
        severity = ErrorCode.get_severity(error_code)

        # Track metrics with time window
        window_count, total_count = await self.metrics.increment(error_code)

        # Prepare structured log data
        execution_time_ms = round((time.time() - start_time) * 1000, 2)
        log_extra = {
            'correlation_id': correlation_id,
            'error_code': error_code,
            'error_name': error_name,
            'error_type': type(error).__name__,
            'severity': severity,
            'execution_time_ms': execution_time_ms,
            'window_count': window_count,
            'total_count': total_count,
            'window_minutes': self.window_minutes
        }

        # Add command context if available
        if isinstance(ctx_or_interaction, commands.Context):
            log_extra.update({
                'command_type': 'prefix',
                'command_name': ctx_or_interaction.command.name if ctx_or_interaction.command else 'unknown',
                'guild_id': ctx_or_interaction.guild.id if ctx_or_interaction.guild else None,
                'channel_id': ctx_or_interaction.channel.id if ctx_or_interaction.channel else None,
                'user_id': ctx_or_interaction.author.id
            })
        elif isinstance(ctx_or_interaction, discord.Interaction):
            log_extra.update({
                'command_type': 'slash',
                'command_name': ctx_or_interaction.command.name if ctx_or_interaction.command else 'unknown',
                'guild_id': ctx_or_interaction.guild_id,
                'channel_id': ctx_or_interaction.channel_id,
                'user_id': ctx_or_interaction.user.id
            })

        # Log with appropriate level based on severity
        log_message = f"Command error | {error_name} ({error_code})"

        if severity == "DEBUG":
            logger.debug(log_message, extra=log_extra)
        elif severity == "WARNING":
            logger.warning(log_message, extra=log_extra)
        elif severity == "CRITICAL":
            logger.critical(log_message, extra=log_extra, exc_info=True)
        else:  # ERROR
            logger.error(log_message, extra=log_extra, exc_info=True)

        # Check if we should send alert (with rate limiting)
        if await self._should_send_alert(error_code):
            logger.warning(
                f"ALERT: {error_name} ({error_code}) | "
                f"{window_count} occurrences in {self.window_minutes} minutes",
                extra={
                    'correlation_id': correlation_id,
                    'error_code': error_code,
                    'error_name': error_name,
                    'window_count': window_count,
                    'threshold': self.alert_threshold,
                    'window_minutes': self.window_minutes,
                    'alert': True
                }
            )
            # In production: send to webhook, PagerDuty, etc.

        # Only send user message if this error code requires it
        if self._should_send_user_message(error_code):
            # Prepare user-friendly response
            response = (
                f"Error Code: {error_code}\n"
                f"{error_message}\n"
                f"Reference: {correlation_id}"
            )

            # Determine response type and send
            if isinstance(ctx_or_interaction, commands.Context):
                await self._send_prefix_response(ctx_or_interaction, response, correlation_id)
            elif isinstance(ctx_or_interaction, discord.Interaction):
                await self._send_interaction_response(ctx_or_interaction, response, correlation_id)

    async def _send_prefix_response(
        self,
        ctx: commands.Context,
        response: str,
        correlation_id: str
    ) -> None:
        """Send error response for prefix commands."""
        try:
            if ctx.interaction:
                # Hybrid command with interaction
                interaction = ctx.interaction
                if not interaction.response.is_done():
                    await interaction.response.send_message(response, ephemeral=True)
                else:
                    await interaction.followup.send(response, ephemeral=True)
            else:
                # Regular prefix command
                await ctx.reply(response)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(
                "Failed to send error response",
                extra={
                    'correlation_id': correlation_id,
                    'error_type': type(e).__name__
                }
            )

    async def _send_interaction_response(
        self,
        interaction: discord.Interaction,
        response: str,
        correlation_id: str
    ) -> None:
        """Send error response for slash commands."""
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(response, ephemeral=True)
            else:
                await interaction.followup.send(response, ephemeral=True)
        except (discord.Forbidden, discord.HTTPException) as e:
            logger.error(
                "Failed to send error response via interaction",
                extra={
                    'correlation_id': correlation_id,
                    'error_type': type(e).__name__
                }
            )

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        """
        Global error handler for prefix commands.
        Respects command-specific error handlers.

        Args:
            ctx: The command context
            error: The exception that was raised
        """
        # Skip if command has its own error handler
        if ctx.command and ctx.command.has_error_handler():
            return

        # Skip if cog has its own error handler
        if ctx.cog and ctx.cog.has_error_handler():
            return

        await self.handle_error(ctx, error)

    @commands.Cog.listener()
    async def on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """
        Global error handler for slash commands.
        Respects command-specific error handlers.

        Args:
            interaction: The interaction that triggered the error
            error: The app command exception that was raised
        """
        # Skip if command has its own error handler
        if interaction.command and interaction.command.on_error:
            return

        await self.handle_error(interaction, error)


async def setup(bot: commands.Bot) -> None:
    """
    Setup function to add the ErrorHandler cog to the bot.

    Args:
        bot: The bot instance
    """
    await bot.add_cog(ErrorHandler(bot))
