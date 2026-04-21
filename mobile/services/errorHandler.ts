/**
 * Enhanced error handling utilities
 */

import { Alert, Platform } from 'react-native';
import { AxiosError } from 'axios';

// Error types
export type ErrorCode =
  | 'NETWORK_ERROR'
  | 'TIMEOUT'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'VALIDATION_ERROR'
  | 'SERVER_ERROR'
  | 'UNKNOWN';

export interface AppError {
  code: ErrorCode;
  message: string;
  details?: string;
  statusCode?: number;
  originalError?: Error;
}

/**
 * Parse an error into a standardized AppError format
 */
export function parseError(error: unknown): AppError {
  // Handle Axios errors
  if (isAxiosError(error)) {
    const axiosError = error as AxiosError<{ detail?: string; message?: string }>;

    // Network error (no response)
    if (!axiosError.response) {
      if (axiosError.code === 'ECONNABORTED') {
        return {
          code: 'TIMEOUT',
          message: 'Request timed out',
          details: 'Please check your internet connection and try again.',
          originalError: error,
        };
      }
      return {
        code: 'NETWORK_ERROR',
        message: 'Unable to connect',
        details: 'Please check your internet connection and try again.',
        originalError: error,
      };
    }

    const status = axiosError.response.status;
    const responseData = axiosError.response.data;
    const serverMessage = responseData?.detail || responseData?.message;

    // Handle specific status codes
    switch (status) {
      case 401:
        return {
          code: 'UNAUTHORIZED',
          message: 'Session expired',
          details: 'Please log in again.',
          statusCode: 401,
          originalError: error,
        };

      case 403:
        return {
          code: 'FORBIDDEN',
          message: 'Access denied',
          details: serverMessage || 'You do not have permission to perform this action.',
          statusCode: 403,
          originalError: error,
        };

      case 404:
        return {
          code: 'NOT_FOUND',
          message: 'Not found',
          details: serverMessage || 'The requested resource was not found.',
          statusCode: 404,
          originalError: error,
        };

      case 422:
        return {
          code: 'VALIDATION_ERROR',
          message: 'Invalid data',
          details: serverMessage || 'Please check your input and try again.',
          statusCode: 422,
          originalError: error,
        };

      case 500:
      case 502:
      case 503:
        return {
          code: 'SERVER_ERROR',
          message: 'Server error',
          details: 'Something went wrong on our end. Please try again later.',
          statusCode: status,
          originalError: error,
        };

      default:
        return {
          code: 'UNKNOWN',
          message: 'Something went wrong',
          details: serverMessage || 'An unexpected error occurred.',
          statusCode: status,
          originalError: error,
        };
    }
  }

  // Handle standard errors
  if (error instanceof Error) {
    return {
      code: 'UNKNOWN',
      message: error.message || 'An error occurred',
      originalError: error,
    };
  }

  // Handle unknown error types
  return {
    code: 'UNKNOWN',
    message: 'An unexpected error occurred',
    details: String(error),
  };
}

/**
 * Check if error is an Axios error
 */
function isAxiosError(error: unknown): error is AxiosError {
  return (error as AxiosError).isAxiosError === true;
}

/**
 * Display a user-friendly error alert
 */
export function showErrorAlert(
  error: unknown,
  options?: {
    title?: string;
    onDismiss?: () => void;
    showRetry?: boolean;
    onRetry?: () => void;
  }
): void {
  const appError = parseError(error);
  const title = options?.title || appError.message;
  const message = appError.details || appError.message;

  const buttons: { text: string; onPress?: () => void; style?: 'cancel' | 'default' | 'destructive' }[] = [];

  if (options?.showRetry && options?.onRetry) {
    buttons.push({
      text: 'Retry',
      onPress: options.onRetry,
    });
  }

  buttons.push({
    text: 'OK',
    onPress: options?.onDismiss,
    style: 'cancel',
  });

  Alert.alert(title, message, buttons);
}

/**
 * Handle auth errors (logout user if needed)
 */
export function handleAuthError(
  error: unknown,
  onLogout: () => void
): boolean {
  const appError = parseError(error);

  if (appError.code === 'UNAUTHORIZED') {
    Alert.alert('Session Expired', 'Please log in again.', [
      { text: 'OK', onPress: onLogout },
    ]);
    return true;
  }

  return false;
}

/**
 * Log error for debugging (console in dev, crash reporting in prod)
 */
export function logError(
  error: unknown,
  context?: string
): void {
  const appError = parseError(error);

  if (__DEV__) {
    console.error(`[${context || 'Error'}]`, {
      code: appError.code,
      message: appError.message,
      details: appError.details,
      statusCode: appError.statusCode,
      originalError: appError.originalError,
    });
  } else {
    // In production, send to crash reporting service
    // Example: Sentry.captureException(appError.originalError || error);
  }
}

/**
 * Retry wrapper with exponential backoff
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  options?: {
    maxAttempts?: number;
    delayMs?: number;
    backoffMultiplier?: number;
    shouldRetry?: (error: unknown, attempt: number) => boolean;
  }
): Promise<T> {
  const maxAttempts = options?.maxAttempts ?? 3;
  const delayMs = options?.delayMs ?? 1000;
  const backoffMultiplier = options?.backoffMultiplier ?? 2;
  const shouldRetry = options?.shouldRetry ?? defaultShouldRetry;

  let lastError: unknown;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      if (attempt < maxAttempts && shouldRetry(error, attempt)) {
        const waitTime = delayMs * Math.pow(backoffMultiplier, attempt - 1);
        await sleep(waitTime);
      } else {
        break;
      }
    }
  }

  throw lastError;
}

/**
 * Default retry condition - retry on network errors and server errors
 */
function defaultShouldRetry(error: unknown, _attempt: number): boolean {
  const appError = parseError(error);
  return (
    appError.code === 'NETWORK_ERROR' ||
    appError.code === 'TIMEOUT' ||
    appError.code === 'SERVER_ERROR'
  );
}

/**
 * Sleep utility
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Error boundary fallback component data
 */
export function getErrorFallbackProps(error: unknown): {
  title: string;
  message: string;
  icon: string;
} {
  const appError = parseError(error);

  switch (appError.code) {
    case 'NETWORK_ERROR':
      return {
        title: 'No Connection',
        message: 'Check your internet connection and try again.',
        icon: 'wifi-off',
      };

    case 'UNAUTHORIZED':
      return {
        title: 'Session Expired',
        message: 'Please log in to continue.',
        icon: 'lock-closed',
      };

    case 'SERVER_ERROR':
      return {
        title: 'Server Error',
        message: 'We\'re having technical difficulties. Please try again later.',
        icon: 'server-outline',
      };

    default:
      return {
        title: 'Something Went Wrong',
        message: appError.details || 'An unexpected error occurred.',
        icon: 'alert-circle',
      };
  }
}
