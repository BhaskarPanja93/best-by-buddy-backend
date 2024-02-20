from __future__ import annotations
from flask import make_response


class CustomResponse:
    def __init__(self):
        self.statusCode: int = -1
        self.statusDesc = ""
        self.data = None

    def createDataDict(self):
        return {
            "STATUS_CODE": self.statusCode,
            "STATUS_DESC": self.statusDesc,
            "DATA": self.data,
        }

    def createFlaskResponse(self):
        response = make_response(self.createDataDict())
        response.status_code = self.statusCode
        return response

    def readValues(self, statusCode: int, statusDesc: str, data):
        self.statusCode = statusCode
        self.statusDesc = statusDesc
        self.data = data
        return self

    def readDict(self, dictionary: dict):
        self.statusCode = dictionary.get("STATUS_CODE")
        self.statusDesc = dictionary.get("STATUS_DESC")
        self.data = dictionary.get("DATA")
        return self

    def readAnotherResponse(self, customResponse: CustomResponse):
        self.statusCode = customResponse.statusCode
        self.statusDesc = customResponse.statusDesc
        self.data = customResponse.data
        return self
