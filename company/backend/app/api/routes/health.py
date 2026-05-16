"""
Health check endpoint for monitoring application availability and status.

This module provides endpoints for verifying that the application is running
and retrieving basic diagnostic information such as version and current time.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

from app.core.config import settings

# Create router with health-related tags for API documentation
router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """
    Health check endpoint that returns the application status.
    
    Returns a dictionary containing:
    - status: Application operational status (e.g., "OK" when healthy)
    - version: Current application version from configuration
    - time: Current UTC timestamp in ISO format for diagnostics
    
    Returns:
        dict: A dictionary with status, version, and current UTC time.
    """
    return {
        "status": "OK",  # Application is operational
        "version": settings.app_version,  # Application version from config
        "time": datetime.now(timezone.utc).isoformat(),  # Current UTC time for monitoring
    }