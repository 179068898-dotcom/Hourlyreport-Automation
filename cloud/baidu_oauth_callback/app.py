import json
import os
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server

from index import main_handler


STATUS_TEXT = {
    200: "OK",
    201: "Created",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
    502: "Bad Gateway",
}


def _query_from_environ(environ):
    parsed = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def application(environ, start_response):
    path = environ.get("PATH_INFO", "/")
    if path not in ("/", "/baidu/oauth/callback", "/baidu/oauth/callback/"):
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
