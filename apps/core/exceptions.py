from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        message = "A record with these values already exists."
        detail = str(exc)
        if "name" in detail and "language" in detail:
            message = "This template name already exists for the selected language."
        return Response(
            {"success": False, "error": {"name": [message]}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = exception_handler(exc, context)
    if response is not None:
        response.data = {
            "success": False,
            "error": response.data,
        }
    return response


class APIResponse:
    @staticmethod
    def success(data=None, message="Success", status_code=status.HTTP_200_OK):
        return Response(
            {"success": True, "message": message, "data": data},
            status=status_code,
        )

    @staticmethod
    def error(message="Error", errors=None, status_code=status.HTTP_400_BAD_REQUEST):
        return Response(
            {"success": False, "message": message, "errors": errors or {}},
            status=status_code,
        )
