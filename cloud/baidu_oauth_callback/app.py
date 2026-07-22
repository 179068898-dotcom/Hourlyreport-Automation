import json
import os
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from index import main_handler, refresh_handler, store_profile_handler, token_handler


STATUS_TEXT = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    401: "Unauthorized",
    405: "Method Not Allowed",
    413: "Payload Too Large",
    404: "Not Found",
    500: "Internal Server Error",
    502: "Bad Gateway",
}


def _query_from_environ(environ):
    parsed = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    method = str(environ.get("REQUEST_METHOD", "GET")).upper()
    if path in (
        "/baidu/oauth/refresh",
        "/baidu/oauth/refresh/",
        "/baidu/oauth/token",
        "/baidu/oauth/token/",
        "/baidu/oauth/store-profile",
        "/baidu/oauth/store-profile/",
    ):
        if method != "POST":
            result = {
                "statusCode": 405,
                "headers": {"Content-Type": "application/json; charset=utf-8"},
                "body": json.dumps({"status": "error", "code": "method_not_allowed"}),
            }
        else:
            try:
                content_length = int(environ.get("CONTENT_LENGTH") or "0")
            except ValueError:
                content_length = -1
            if content_length < 0:
                result = {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/json; charset=utf-8"},
                    "body": json.dumps({"status": "error", "code": "invalid_content_length"}),
                }
            elif content_length > 65536:
                result = {
                    "statusCode": 413,
                    "headers": {"Content-Type": "application/json; charset=utf-8"},
                    "body": json.dumps({"status": "error", "code": "payload_too_large"}),
                }
            else:
                body = environ.get("wsgi.input").read(content_length).decode("utf-8")
                handler = refresh_handler
                if path.rstrip("/") == "/baidu/oauth/token":
                    handler = token_handler
                elif path.rstrip("/") == "/baidu/oauth/store-profile":
                    handler = store_profile_handler
                result = handler(
                    {
                        "httpMethod": method,
                        "path": path,
                        "headers": {
                            "X-Baidu-Refresh-Timestamp": environ.get("HTTP_X_BAIDU_REFRESH_TIMESTAMP", ""),
                            "X-Baidu-Refresh-Signature": environ.get("HTTP_X_BAIDU_REFRESH_SIGNATURE", ""),
                        },
                        "body": body,
                    },
                    None,
                )
    elif path not in ("/", "/baidu/oauth/callback", "/baidu/oauth/callback/"):
        result = {
            "statusCode": 404,
            "headers": {"Content-Type": "application/json; charset=utf-8"},
            "body": json.dumps({"status": "error", "code": "not_found"}),
        }
    else:
        result = main_handler(
            {"queryStringParameters": _query_from_environ(environ)},
            None,
        )
    status_code = int(result["statusCode"])
    status = "%d %s" % (status_code, STATUS_TEXT.get(status_code, "Unknown"))
    headers = [(str(key), str(value)) for key, value in result.get("headers", {}).items()]
    body = result.get("body", "").encode("utf-8")
    headers.append(("Content-Length", str(len(body))))
    start_response(status, headers)
    return [body]


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9000"))
    make_server("0.0.0.0", port, application).serve_forever()
