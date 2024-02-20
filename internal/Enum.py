from enum import Enum
from pathlib import Path
folderLocation = "D:\\testing\\best-by-buddy\\"

class RequiredFiles(Enum):
    common = [
        Path(folderLocation, r"internal\AutoReRun.py"),
        Path(folderLocation, r"internal\CustomResponse.py"),
        Path(folderLocation, r"internal\Enum.py"),
        Path(folderLocation, r"internal\Logger.py"),
        Path(folderLocation, r"internal\MysqlPool.py"),
        Path(folderLocation, r"internal\StringGenerator.py"),
        Path(folderLocation, r"internal\MysqlPool.py"),
    ]
    coreFile = Path(folderLocation, r"core.py")
    userGatewayFile = Path(folderLocation, r"user_gateway.py")
    adminGatewayFile = Path(folderLocation, r"admin_gateway.py")



class Constants(Enum):
    logCount = 1000
    userGatewayPort = 50000
    adminGatewayPort = 50001
    coreServerPort = 50002


class Secrets(Enum):
    fernetSecret = "SKe1v6zExvJ3v_2q3Rj9up3RV-D_Sku0aOMX2OY8Nzc="
    JWTSecret = "QYHo8hEWLdNbv8EbtdV2MX6836s7qPtumOzCtkM3SeTkR7iVSpJG7sDcslpafZn6BrhrVm"
    userGatewaySecret = "Dg6a52PILi98QK5nxvRnDSoiq3ztX4NJQkoAql6dsLWaCGhlZNdfMCCLAA"
    adminGatewaySecret = "IJkrS7xjTTDSR4FrMbbsiupPTnC4gXGK8PJLNs2nP5H9sY9lkqC6RbBTujs9A75ouXy4gL2XgE5jbkz33v8EeRnH"
    GPT4APIKey = "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"
    DBHosts = ["127.0.0.1", "10.30.200.1", "bhindi1.ddns.net"]
    DBPassword = "SageHasBestBoobs@69"


class Routes(Enum):
    register = "register"
    authRaw = "authraw"
    renewAuth = "renewauth"
    imgRecv = "imgrecv"


class GPTElements(Enum):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {Secrets.GPT4APIKey.value}",
    }


class commonMethods:
    @staticmethod
    def checkRelatedIP(addressA: str, addressB: str):
        if addressA.count(".") == 3 and addressB.count(".") == 3:
            a = addressA.split(".")[:-1]
            b = addressB.split(".")[:-1]
            return a == b
        return addressA == addressB

    @staticmethod
    def sqlISafe(parameter):
        if type(parameter) == str:
            return parameter.replace("'", "").replace('"', "")
        return parameter


class Tasks(Enum):
    img_gen = "img_gen"
    text_gen = "text_gen"
    img_understanding = "img_understanding"
