from enum import Enum
from pathlib import Path
from time import sleep
from pooledMySQL import Manager as MySQLPool
from customisedLogs import Manager as LogManager
from ping3 import ping

from internal.SecretEnum import Secrets


for location in Secrets.possibleFolderLocation.value:
    if Path(location).is_dir():
        folderLocation = location
        break
else:
    input("Project directory not found in Enum...")


class RequiredFiles(Enum):
    common = [
        r"internal\AutoReRun.py",
        r"internal\CustomResponse.py",
        r"internal\Enum.py",
        r"internal\Logger.py",
        r"internal\MysqlPool.py",
        r"internal\SecretEnum.py",
        r"internal\StringGenerator.py",
    ]
    coreFile = r"core.py"
    userGatewayFile = r"gateway.py"
    adminGatewayFile = r"admin_gateway.py"
    purchaseImageFolder = r"savedImages"
    thumbnailFolder = r"thumbnails"


class Constants(Enum):
    logCount = 1000
    userGatewayPort = 60200
    adminGatewayPort = 60201
    coreServerPort = 60202


class Routes(Enum):
    home = "/bbb"
    register = "/bbb_register"
    authRaw = "/bbb_authraw"
    renewAuth = "/bbb_renewauth"
    imgRecv = "/bbb_imgrecv"
    requestNewItemUID = "/bbb_newitemuid"
    confirmPurchase = "/bbb_confirmPurchase"


class RequestElements(Enum):
    GPTHeaders = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {Secrets.GPT4APIKey.value}",
    }
    requestHeaders = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.4664.110 Safari/537.36'
    }


class commonMethods:
    @staticmethod
    def waitForNetwork(logger:LogManager):
        """
        Blocking function to check for internet connection.
        :param logger: LogManager object to log to if no internet found
        :return:
        """
        paused = False
        while True:
            try:
                if type(ping("3.6.0.0")) == float:
                    return
            except:
                if not paused:
                    logger.fatal("INTERNET", "No network found...")
                    paused = True
            sleep(1)

    @staticmethod
    def checkRelatedIP(addressA: str, addressB: str):
        """
        Check if 2 IPv4 belong to same */24 subnet
        :param addressA: IPv4 as string
        :param addressB: IPv4 as string
        :return:
        """
        if addressA.count(".") == 3 and addressB.count(".") == 3:
            a = addressA.split(".")[:-1]
            b = addressB.split(".")[:-1]
            return a == b
        return addressA == addressB

    @staticmethod
    def sqlISafe(parameter):
        """
        Sanitise SQL syntax before passing it to main Database
        :param parameter: String containing the syntax to execute
        :return:
        """
        if type(parameter) == str:
            return parameter.replace("'", "").replace('"', "").strip()
        return parameter

    @staticmethod
    def connectDB(logger:LogManager) -> MySQLPool:
        """
        Blocking function to connect to DB
        :return: None
        """
        for host in Secrets.DBHosts.value:
            try:
                mysqlPool = MySQLPool(user="root", password=Secrets.DBPassword.value, dbName=Secrets.DBName.value, host=host)
                mysqlPool.execute(f"SELECT DATABASE();")
                logger.success("DB", f"connected to: {host}")
                return mysqlPool
            except:
                logger.failed("DB", f"failed: {host}")
        else:
            logger.fatal("DB", "Unable to connect to DataBase")
            input("EXIT...")
            exit(0)


class Tasks(Enum):
    img_gen = "img_gen"
    text_gen = "text_gen"
    img_understanding = "img_understanding"


class Response200Messages(Enum):
    correct = "CORRECT"
    dummyRecogniser = "DUMMY_RECOGNISER"
    dummyExpiry = "DUMMY_EXPIRY"


class Response403Messages(Enum):
    penalisedIP = "IP_PENALTY"
    loginRequired = "LOGIN_REQ"
    usernameExists = "USERNAME_EXISTS"
    invalidUsername = "USERNAME_INVALID"
    authNotFound = "AUTH_NOT_FOUND"
    incorrectAuth = "INCORRECT_AUTH"
    coreRejectedAuth = "CORE_REJECTED_AUTH"
    incompleteRegistration = "INCOMPLETE_REGISTRATION"
    incorrectMethod = "METHOD_INCORRECT"

class Response422Messages(Enum):
    postErrorGPT = "GPT_POST_ERROR"
    parseFailed = "PARSE_FAIL"

class Response500Messages(Enum):
    imageNotFound = "IMG_NOT_FOUND"
    durationNotFound = "DUR_UNAVAILABLE"
    coreDown = "CORE_DOWN"
    dummy = "DUMMY"
