from __future__ import annotations
from flask import make_response


class CustomResponse:
    def __init__(self):
        self.statusCode: int = -1
        self.statusDesc = ""
        self.data = None
        self.cookie: None | dict = None

    def createDataDict(self):
        return {
            "STATUS_CODE": self.statusCode,
            "STATUS_DESC": self.statusDesc,
            "DATA": self.data,
        }

    def createFlaskResponse(self):
        response = make_response(self.createDataDict())
        response.status_code = self.statusCode
        if self.cookie is not None and self.cookie:
            for name in self.cookie:
                response.set_cookie(name, self.cookie.get(name))
        return response

    def readValues(
        self, statusCode: int, statusDesc: str, data, cookieDict: dict | None = None
    ):
        self.statusCode = statusCode
        self.statusDesc = statusDesc
        self.data = data
        self.cookie = cookieDict
        return self

    def readDict(self, dictionary: dict):
        self.statusCode = dictionary.get("STATUS_CODE")
        self.statusDesc = dictionary.get("STATUS_DESC")
        self.data = dictionary.get("DATA")
        self.cookie = dictionary.get("COOKIE")
        return self

    def readAnotherResponse(self, customResponse: CustomResponse):
        self.statusCode = customResponse.statusCode
        self.statusDesc = customResponse.statusDesc
        self.data = customResponse.data
        self.cookie = customResponse.cookie
        return self
