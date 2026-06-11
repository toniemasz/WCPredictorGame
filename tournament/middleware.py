from django.shortcuts import render


class CustomErrorPageMiddleware:
    ERROR_STATUS_CODES = {400, 403, 404, 500}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if self._should_replace_response(request, response):
            return self._render_error_page(request, response.status_code)

        return response

    def process_exception(self, request, exception):
        return self._render_error_page(request, 500)

    def _should_replace_response(self, request, response):
        if response.status_code not in self.ERROR_STATUS_CODES:
            return False

        if response.headers.get("X-Custom-Error-Page") == "1":
            return False

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return False

        content_type = response.headers.get("Content-Type", "")
        if content_type and "text/html" not in content_type:
            return False

        accept = request.headers.get("Accept", "")
        if "application/json" in accept and "text/html" not in accept:
            return False

        return True

    @staticmethod
    def _render_error_page(request, status_code):
        response = render(
            request,
            "errors/error.html",
            {"status_code": status_code},
            status=status_code,
        )
        response.headers["X-Custom-Error-Page"] = "1"
        return response
