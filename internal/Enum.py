from enum import Enum


class RequiredFiles(Enum):
    folderLocation = r"C:\FILES\AllProjects\Python\best-by-buddy"
    common = [
        folderLocation.value+r"\internal\AutoReRun.py",
        folderLocation.value+r"\internal\CustomResponse.py",
        folderLocation.value+r"\internal\Enum.py",
        folderLocation.value+r"\internal\Logger.py",
        folderLocation.value+r"\internal\MysqlPool.py",
        folderLocation.value+r"\internal\StringGenerator.py",
        folderLocation.value+r"\internal\MysqlPool.py",
    ]
    


class Constants(Enum):
    logCount = 1000
    userGatewayPort = 50000
    adminGatewayPort = 50001
    coreServerPort = 50002


class Secrets(Enum):
    fernetSecret = 'SKe1v6zExvJ3v_2q3Rj9up3RV-D_Sku0aOMX2OY8Nzc='
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
        "Authorization": f"Bearer {Secrets.GPT4APIKey.value}"
    }

class commonMethods:
    @staticmethod
    def checkRelatedIP(addressA: str, addressB: str):
        if addressA.count(".") == 3 and addressB.count(".") == 3:
            a = addressA.split('.')[:-1]
            b = addressB.split('.')[:-1]
            return a == b
        return addressA == addressB

    @staticmethod
    def sqlISafe(parameter):
        if type(parameter) == str:
            return parameter.replace("'", "").replace('"', '')
        return parameter


