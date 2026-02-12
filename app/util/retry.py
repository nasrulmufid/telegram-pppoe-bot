from __future__ import annotations

from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)


def _is_retryable_httpx(exc: BaseException) -> bool:
    import httpx

    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


def retry_nuxbill():
    return retry(
        retry=retry_if_exception(_is_retryable_httpx),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.2, max=1.0),
        reraise=True,
    )


def retry_telegram():
    return retry(
        retry=retry_if_exception(_is_retryable_httpx),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.2, max=1.0),
        reraise=True,
    )


def format_retry_log(retry_state: RetryCallState) -> str:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    return f"attempt={retry_state.attempt_number} exc={exc!r}"
