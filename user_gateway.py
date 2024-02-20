

from gevent import monkey

monkey.patch_all()

from base64 import b64decode
from gevent.pywsgi import WSGIServer
from flask import Flask, request, Request
from requests import post
from functools import wraps
from bcrypt import checkpw, gensalt, hashpw
from flask_jwt_extended import create_access_token, JWTManager
from cryptography.fernet import Fernet
from json import dumps, loads
from datetime import timedelta
from threading import Thread
from time import sleep

from internal.CustomResponse import CustomResponse
from internal.Enum import Routes, Constants, Secrets, commonMethods
from internal.Logger import Logger
from internal.StringGenerator import randomGenerator
from internal.MysqlPool import mysqlPool as MySQLPool

### switches
ALLOW_ANY_REQ_TYPE = True
LOGIN_REQUIRED = False
ALLOW_ALL_IPS = True
ALLOW_LOCALHOST = False
FETCH_IMAGE = False

### internal checker
DBReady = False

fernetObj = Fernet(Secrets.fernetSecret.value)
logger = Logger()
stringGen = randomGenerator()
userGateway = Flask("RECOGNITION_API")
userGateway.config["JWT_SECRET_KEY"] = Secrets.JWTSecret.value
userGateway.config["SECRET_KEY"] = Secrets.userGatewaySecret.value
jwt = JWTManager(userGateway)
activeUsers = {}
mysqlPool: MySQLPool | None = None


def connectDB():
    global DBReady, mysqlPool
    for host in ["127.0.0.1", "bhindi1.ddns.net"]:
        try:
            mysqlPool = MySQLPool(
                user="root",
                password=Secrets.DBPassword.value,
                dbName="bestbybuddy",
                host=host,
            )
            mysqlPool.execute("show databases")
            logger.success("DB", f"connected to: {host}")
            DBReady = True
            break
        except:
            logger.critical("DB", f"failed: {host}")
    else:
        logger.fatal("DB", "Unable to connect to bestbybuddy")
        input("EXIT...")
        exit(0)


def penaliseIP(requestObj: Request):
    address = commonMethods.sqlISafe(requestObj.remote_addr)
    try:
        mysqlPool.execute(
            f'INSERT INTO ip_penalties values("{address}", DATE_ADD(now(), INTERVAL 1 HOUR))',
            ignoreErrors=False,
        )
    except:
        mysqlPool.execute(
            f'UPDATE ip_penalties set expires=DATE_ADD(expires, INTERVAL 1 HOUR) where address="{address}"'
        )


def onlyAllowedIPs(flaskFunction):
    def __isIPPenalised(request):
        address = commonMethods.sqlISafe(request.remote_addr)
        if address in [
            "BANNED",
            "LOCAL" if not ALLOW_LOCALHOST else "",
        ] or mysqlPool.execute(
            f'SELECT address from ip_penalties where address="{address}" and expires>now()'
        ):
            return True
        return False

    @wraps(flaskFunction)
    def wrapper():
        if ALLOW_ALL_IPS or not __isIPPenalised(request):
            return flaskFunction()
        else:
            logger.critical(
                "UNAUTHORISED", f"{request.url_rule} from {request.remote_addr}"
            )
            statusCode = 403
            statusDesc = "IP_PENALTY"
            return (
                CustomResponse()
                .readValues(statusCode, statusDesc, "")
                .createFlaskResponse()
            )

    return wrapper


def onlyAllowedAuth(flaskFunction):
    def __checkAuthCorrectness(request):
        username = commonMethods.sqlISafe(request.headers.get("USERNAME"))
        externalJWT = commonMethods.sqlISafe(request.headers.get("BEARER-JWT"))
        cookie = commonMethods.sqlISafe(request.cookies.get("DEVICE-COOKIE"))
        userUIDTupList = mysqlPool.execute(
            f'SELECT user_uid from user_info where username="{username}"'
        )
        if userUIDTupList and userUIDTupList[0]:
            userUID = userUIDTupList[0][0].decode()
            addressDeviceUIDTupList = mysqlPool.execute(
                f'SELECT address, device_uid from user_device_auth where user_uid="{userUID}" and cookie="{cookie}" and external_jwt="{externalJWT}"'
            )
            for addressDeviceUIDTup in addressDeviceUIDTupList:
                if commonMethods.checkRelatedIP(
                    addressDeviceUIDTup[0], request.remote_addr
                ):
                    deviceUID = addressDeviceUIDTup[1]
                    return True, username, userUID, deviceUID
        return False, "", "", ""

    @wraps(flaskFunction)
    def wrapper():
        authCorrect, username, userUID, deviceID = __checkAuthCorrectness(request)
        if not LOGIN_REQUIRED or authCorrect:
            return flaskFunction(username, userUID, deviceID)
        else:
            logger.critical("COOKIE", f"{request.url_rule} from {request.remote_addr}")
            statusCode = 403
            statusDesc = "LOGIN_REQ"
            return (
                CustomResponse()
                .readValues(statusCode, statusDesc, "")
                .createFlaskResponse()
            )

    return wrapper


def onlyAllowedMethods(flaskFunction):
    def __checkMethodCorrectness(request):
        if request.method == "POST":
            return True
        return False

    @wraps(flaskFunction)
    def wrapper():
        if ALLOW_ANY_REQ_TYPE or __checkMethodCorrectness(request):
            return flaskFunction()
        else:
            logger.critical("METHOD", f"{request.method} from {request.remote_addr}")
            statusCode = 403
            statusDesc = "METHOD_INCORRECT"
            return (
                CustomResponse()
                .readValues(statusCode, statusDesc, "")
                .createFlaskResponse()
            )

    return wrapper


def waitForInitDB(flaskFunction):
    def __checkInitDB():
        if DBReady:
            return True
        return False

    @wraps(flaskFunction)
    def wrapper():
        while not __checkInitDB():
            sleep(0.5)
        return flaskFunction()

    return wrapper


def registerNewUser(requestObj: Request) -> tuple[int, str, dict]:
    print(requestObj.form)
    username = commonMethods.sqlISafe(requestObj.form.get("username"))
    passwordEncoded = requestObj.form.get("password").encode()
    name = requestObj.form.get("name").encode()
    authData = {}
    passHash = hashpw(passwordEncoded, gensalt())
    cookieDict = {"ADDRESS": requestObj.remote_addr, "UA": requestObj.user_agent.string}
    cookieStr = fernetObj.encrypt(dumps(cookieDict).encode()).decode()
    address = request.remote_addr
    while True:
        externalJWT = create_access_token(
            identity=username, expires_delta=timedelta(days=365)
        )
        if not mysqlPool.execute(
            f'SELECT external_jwt from user_device_auth where external_jwt="{externalJWT}"'
        ) and not mysqlPool.execute(
            f'SELECT external_jwt from admin_device_auth where external_jwt="{externalJWT}"'
        ):
            break
    while True:
        internalJWT = create_access_token(
            identity=username, expires_delta=timedelta(days=3650)
        )
        if not mysqlPool.execute(
            f'SELECT internal_jwt from user_connection_auth where internal_jwt="{internalJWT}"'
        ) and not mysqlPool.execute(
            f'SELECT internal_jwt from admin_connection_auth where internal_jwt="{internalJWT}"'
        ):
            break
    while True:
        userUID = randomGenerator().AlphaNumeric(50, 51)
        if not mysqlPool.execute(
            f'SELECT user_uid from user_connection_auth where user_uid="{userUID}"'
        ) and not mysqlPool.execute(
            f'SELECT admin_uid from admin_connection_auth where admin_uid="{userUID}"'
        ):
            mysqlPool.execute(
                f'INSERT INTO user_info values ("{userUID}", "{username}", now(), "{name}")'
            )
            mysqlPool.execute(
                f'INSERT INTO user_connection_auth values ("{userUID}", "{internalJWT}", "{passHash}")'
            )
            break
    while True:
        deviceUID = randomGenerator().AlphaNumeric(50, 51)
        if not mysqlPool.execute(
            f'SELECT device_uid from user_device_auth where device_uid="{deviceUID}"'
        ) and not mysqlPool.execute(
            f'SELECT device_uid from admin_device_auth where device_uid="{deviceUID}"'
        ):
            mysqlPool.execute(
                f'INSERT INTO user_device_auth values ("{deviceUID}", "{userUID}", "{cookieStr}", "{externalJWT}", {requestObj.user_agent.string}, "{address}")'
            )
            break
    authData["COOKIE"] = {"DEVICE-COOKIE": cookieStr}
    authData["JWT"] = {"DEVICE-JWT": externalJWT}
    authData["DEVICE"] = {"DEVICE-UID": deviceUID}
    logger.skip("REGNEW", str(authData))
    return 200, "", authData


def baseAuthRaw(requestObj: Request) -> tuple[int, str, dict]:
    address = commonMethods.sqlISafe(requestObj.remote_addr)
    username = commonMethods.sqlISafe(requestObj.form.get("username"))
    passwordEncoded = requestObj.form.get("password").encode()
    userUIDTupList = mysqlPool.execute(
        f'SELECT user_uid from user_info where username="{username}"'
    )
    authData = {}
    statusCode = 403
    if not userUIDTupList or not userUIDTupList[0]:
        statusDesc = "INCORRECT_USERNAME"
    else:
        userUID = userUIDTupList[0][0].decode()
        passHashTupList = mysqlPool.execute(
            f'SELECT pass_hash from user_connection_auth where user_uid="{userUID}"'
        )
        if not passHashTupList or not passHashTupList[0]:
            statusDesc = "INCOMPLETE_REGISTRATION"
        else:
            passHash = passHashTupList[0][0].decode()
            if passHash != checkpw(passwordEncoded, passHash):
                statusDesc = "INCORRECT_AUTH"
            else:
                statusCode = 200
                statusDesc = ""
                cookieDict = {
                    "ADDRESS": requestObj.remote_addr,
                    "UA": requestObj.user_agent.string,
                }
                externalJWT = create_access_token(
                    identity=username, expires_delta=timedelta(days=365)
                )
                cookieStr = fernetObj.encrypt(dumps(cookieDict).encode()).decode()
                while True:
                    deviceUID = randomGenerator().AlphaNumeric(50, 51)
                    if not mysqlPool.execute(
                        f'SELECT device_uid from user_device_auth where device_uid="{deviceUID}"'
                    ) and not mysqlPool.execute(
                        f'SELECT device_uid from admin_device_auth where device_uid="{deviceUID}"'
                    ):
                        mysqlPool.execute(
                            f'INSERT INTO user_device_auth values ("{deviceUID}", "{userUID}", "{cookieStr}", "{externalJWT}", {requestObj.user_agent.string}, "{address}")'
                        )
                        break
                authData["COOKIE"] = {"DEVICE-COOKIE": cookieStr}
                authData["JWT"] = {"DEVICE-JWT": externalJWT}
                authData["DEVICE"] = {"DEVICE-UID": deviceUID}
    return statusCode, statusDesc, authData


def getInternalJWT(requestObj: Request) -> tuple[int, str, str]:
    internalJWT = ""
    statusCode = 403
    statusDesc = "INCORRECT_USERNAME"
    if not LOGIN_REQUIRED:
        statusCode = 200
        statusDesc = ""
        username, externalJWT, cookie = "", "", ""
    else:
        username = commonMethods.sqlISafe(requestObj.headers.get("username"))
        externalJWT = requestObj.headers.get("Bearer-JWT")
        cookie = requestObj.cookies.get("auth")
        userUIDTupList = mysqlPool.execute(f'SELECT user_uid from user_info where username="{username}"')
        if userUIDTupList and userUIDTupList[0]:
            userUID = userUIDTupList[0][0].decode()
            cookieJWTTupList = mysqlPool.execute(f'SELECT cookie, external_jwt from user_device_auth where user_uid="{userUID}"')
            if not cookieJWTTupList or not cookieJWTTupList[0]:
                statusDesc = "AUTH_NOT_FOUND"
            else:
                savedCookie, savedExternalJWT = cookieJWTTupList[0]
                savedCookie = savedCookie.decode()
                savedExternalJWT = savedExternalJWT.decode()
                if cookie != savedCookie or savedExternalJWT != externalJWT:
                    statusDesc = "INCORRECT_AUTH"
                else:
                    internalJWTTupList = mysqlPool.execute(f'SELECT internal_jwt from user_connection_auth where user_uid="{userUID}"')
                    if not userUIDTupList or not userUIDTupList[0]:
                        statusDesc = "CORE_REJECTED_AUTH"
                    else:
                        statusCode = 200
                        statusDesc = ""
                        internalJWT = internalJWTTupList[0][0].decode()
    return statusCode, statusDesc, internalJWT


"""@userGateway.route(f"/{Routes.renewAuth.value}", methods=["POST", "GET"] if ALLOW_ANY_REQ_TYPE else ["POST"])
@onlyAllowedIPs
def authenticateApp():
    statusCode, statusDesc, authData = renewAuthData(request)
    logger.success("SENT", f"{request.url_rule} response sent to {request.remote_addr}")
    return CustomResponse().readValues(statusCode, statusDesc, authData).createFlaskResponse()"""


@userGateway.route(f"/{Routes.register.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
def registerRaw():
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    statusCode, statusDesc, authData = registerNewUser(request)
    logger.success("SENT", f"{request.url_rule} response sent to {request.remote_addr}")
    return (
        CustomResponse()
        .readValues(statusCode, statusDesc, authData, authData["COOKIE"])
        .createFlaskResponse()
    )


@userGateway.route(f"/{Routes.authRaw.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
def authenticateRaw():
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    statusCode, statusDesc, authData = baseAuthRaw(request)
    logger.success("SENT", f"{request.url_rule} response sent to {request.remote_addr}")
    return (
        CustomResponse()
        .readValues(statusCode, statusDesc, authData, authData["COOKIE"])
        .createFlaskResponse()
    )


@userGateway.route(f"/{Routes.imgRecv.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
@onlyAllowedAuth
def recogniseRoute(username, userUID, deviceUID):
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    statusCode, statusDesc, internalJWT = getInternalJWT(request)
    imgBytes = b""
    data = ""
    if FETCH_IMAGE:
        try:
            imgBytes = request.files.get("IMG_DATA").stream.read()
            statusCode = 200
            statusDesc = ""
            logger.success("IMAGE_EXTRACT", f"in Files SIZE: {len(imgBytes)}")
        except:
            try:
                imgBytes = b64decode(loads(request.data)["IMG_DATA"])
                statusCode = 200
                statusDesc = ""
                logger.success("IMAGE_EXTRACT", f"in Data Size: {len(imgBytes)}")
            except:
                statusCode = 500
                statusDesc = "IMG_NOT_FOUND"
                logger.fatal("IMAGE_EXTRACT", f"failed")
    if statusCode == 200:
        header = {
            "INTERNAL-JWT": internalJWT,
            "USERNAME": username,
            "USER-UID": userUID,
            "DEVICE-UID": deviceUID,
        }
        try:
            data = post(
                        f"http://127.0.0.1:{Constants.coreServerPort.value}/{Routes.imgRecv.value}",
                        headers=header, data=imgBytes
                    ).json()
            logger.success("CORE_FWD", f"{request.url_rule} sent to {request.remote_addr}")
        except Exception as e:
            print(repr(e))
            statusCode = 500
            statusDesc = "CORE_DOWN"
            logger.fatal("CORE_FWD", f"Unable to connect")
    return CustomResponse().readValues(statusCode, statusDesc, data).createFlaskResponse()


@userGateway.before_request
def userBeforeRequest():
    address = "BANNED"
    if request.remote_addr == "127.0.0.1":
        if request.environ.get("HTTP_X_FORWARDED_FOR") == request.headers.get(
            "X-Forwarded-For"
        ):
            if request.environ.get("HTTP_X_FORWARDED_FOR") is not None:
                address = request.environ.get("HTTP_X_FORWARDED_FOR")
            else:
                address = "LOCAL"
    else:
        address = request.remote_addr

    request.remote_addr = address
    # print(request.headers.get("JWT"))
    # print(request.environ)

print(f"USER GATEWAY: {Constants.userGatewayPort.value}")
Thread(target=connectDB).start()
WSGIServer(
    (
        "0.0.0.0",
        Constants.userGatewayPort.value,
    ),
    userGateway,
    log=None,
).serve_forever()
