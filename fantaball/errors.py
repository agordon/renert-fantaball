class ApiError(Exception):
    """An error with an HTTP status that is safe to show to the user."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def bad_request(msg):
    return ApiError(msg, 400)


def forbidden(msg="You do not have permission to do that"):
    return ApiError(msg, 403)


def not_found(msg="Not found"):
    return ApiError(msg, 404)


def conflict(msg):
    return ApiError(msg, 409)
