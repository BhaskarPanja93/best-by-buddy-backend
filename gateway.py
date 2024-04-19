from gevent import monkey
monkey.patch_all()

from werkzeug.security import generate_password_hash, check_password_hash
from base64 import b64decode
from gevent.pywsgi import WSGIServer
from flask import Flask, request, Request
from requests import post
from functools import wraps
from flask_jwt_extended import create_access_token, JWTManager
from cryptography.fernet import Fernet
import datetime
from json import loads
from datetime import timedelta, datetime
from time import sleep
from customisedLogs import Manager as LogManager
from randomisedString import Generator as StrGen

from internal.CustomResponse import CustomResponse
from internal.Enum import Routes, Constants, commonMethods, Response403Messages, Response200Messages, Response500Messages
from internal.SecretEnum import Secrets

### switches
ALLOW_ANY_REQ_METHOD = True
LOGIN_REQUIRED = True
UNBLOCK_ALL_IP = True
ALLOW_LOCALHOST = True
FETCH_IMAGE = True
PENALISE_IP = False

### internal checker
DBReady = False

logger = LogManager()
fernetObj = Fernet(Secrets.fernetSecret.value)
stringGen = StrGen()
userGateway = Flask("RECOGNITION_API", template_folder="templates")
userGateway.config["JWT_SECRET_KEY"] = Secrets.JWTSecret.value
userGateway.config["SECRET_KEY"] = Secrets.userGatewaySecret.value
jwt = JWTManager(userGateway)
mysqlPool = commonMethods.connectDB(logger)


def penaliseIP(address:str, second:int=5):
    """
    Penalise any address for misuse of service
    :param second:
    :param address: IP to penalise
    :return:
    """
    if PENALISE_IP and address:
        try:
            mysqlPool.execute(f"INSERT INTO ip_penalties values(\"{address}\", DATE_ADD(now(), INTERVAL {second} SECOND ))")
        except:
            mysqlPool.execute(f"UPDATE ip_penalties set expires=DATE_ADD(now(), INTERVAL {second} SECOND) where address=\"{address}\"")


def onlyAllowedIPs(flaskFunction):
    """
    Check and disallow IPs that are already penalised, block or unblock local IPs
    :param flaskFunction: the function to switch context to if IP allowed
    :return:
    """
    def __isIPPenalised(request:Request):
        address = commonMethods.sqlISafe(request.remote_addr)
        expiryTupList = mysqlPool.execute(f"SELECT address from ip_penalties where address=\"{address}\"")
        if expiryTupList and expiryTupList[0]: activePenalty = datetime.now()<expiryTupList[0][0]
        else: activePenalty = False
        if address in ["BANNED", "LOCAL" if not ALLOW_LOCALHOST else ""] or activePenalty:
            logger.fatal("AUTH", f"address not allowed: {address}")
            return True
        return False

    @wraps(flaskFunction)
    def wrapper():
        if UNBLOCK_ALL_IP or not __isIPPenalised(request):
            return flaskFunction()
        else:
            logger.failed("UNAUTHORISED", f"onlyAllowedIPs: {request.url_rule} from {request.remote_addr}")
            statusCode = 403
            penaliseIP(commonMethods.sqlISafe(request.remote_addr), 10)
            statusDesc = Response403Messages.penalisedIP.value
            return CustomResponse().readValues(statusCode, statusDesc, "").createFlaskResponse()
    return wrapper


def onlyAllowedAuth(flaskFunction):
    """
    Allow only authorised requests and reject the rest
    :param flaskFunction: the function to switch context to if auth succeeds
    :return:
    """
    def __checkAuthCorrectness(request:Request):
        username = commonMethods.sqlISafe(request.headers.get("USERNAME"))
        externalJWT = commonMethods.sqlISafe(request.headers.get("BEARER-JWT"))
        userUIDTupList = mysqlPool.execute(f"SELECT user_uid from user_info where username=\"{username}\"")
        if len(userUIDTupList)==1 and userUIDTupList[0]:
            userUID = userUIDTupList[0][0].decode()
            addressDeviceUIDTupList = mysqlPool.execute(f"SELECT address, device_uid from user_device_auth where user_uid=\"{userUID}\" and external_jwt=\"{externalJWT}\"")
            if len(addressDeviceUIDTupList)==1 and addressDeviceUIDTupList[0]:
                if commonMethods.checkRelatedIP(addressDeviceUIDTupList[0][0], request.remote_addr):
                    deviceUID = addressDeviceUIDTupList[0][1].decode()
                    return True, username, userUID, deviceUID
                else: logger.fatal("AUTH", f"address mismatch E:[{addressDeviceUIDTupList[0][0]}] R:[{request.remote_addr}] for {userUID} [{externalJWT}]")
            else: logger.fatal("AUTH", f"no address, device_uid for {userUID} [{externalJWT}]")
        else: logger.fatal("AUTH", f"no user_id for {username}")
        return False, "", "", ""

    @wraps(flaskFunction)
    def wrapper():
        authCorrect, username, userUID, deviceID = __checkAuthCorrectness(request)
        if not LOGIN_REQUIRED or authCorrect:
            return flaskFunction(username, userUID, deviceID)
        else:
            logger.failed("AUTH", f"onlyAllowedAuth: {request.url_rule} from {request.remote_addr}")
            statusCode = 403
            statusDesc = Response403Messages.loginRequired.value
            penaliseIP(commonMethods.sqlISafe(request.remote_addr))
            return CustomResponse().readValues(statusCode, statusDesc, "").createFlaskResponse()
    return wrapper


def onlyAllowedMethods(flaskFunction):
    """
    Debug only, to test with GET methods or as allowed by switches
    :param flaskFunction: the function to switch context to if method allowed
    :return:
    """
    def __checkMethodCorrectness(request:Request):
        if request.method == "POST":
            return True
        return False

    @wraps(flaskFunction)
    def wrapper():
        if ALLOW_ANY_REQ_METHOD or __checkMethodCorrectness(request):
            return flaskFunction()
        else:
            logger.failed("METHOD", f"onlyAllowedMethods: {request.method} from {request.remote_addr}")
            statusCode = 403
            statusDesc = "METHOD_INCORRECT"
            return CustomResponse().readValues(statusCode, statusDesc, "").createFlaskResponse()
    return wrapper


def waitForInitDB(flaskFunction):
    """
    Wait for Database initialisation
    :param flaskFunction: the function to switch context to when DB is initialised
    :return:
    """
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
    """
    Upon new registration, add that as a new user, only if username is unique. Also add the device details for immediate login.
    :param requestObj:
    :return:
    """
    username = commonMethods.sqlISafe(requestObj.form.get("username"))
    password = requestObj.form.get("password")
    name = requestObj.form.get("name").encode()
    authData = {}
    passHash = generate_password_hash(password, "scrypt", 50)
    address = request.remote_addr
    repeatUsernameTupList = mysqlPool.execute(f"SELECT username from user_info where username=\"{username}\"")
    if (repeatUsernameTupList and repeatUsernameTupList[0]) or not username:
        statusCode = 403
        statusDesc = Response403Messages.usernameExists.value
    else:
        while True:
            externalJWT = create_access_token(identity=username, expires_delta=timedelta(days=365))
            if not mysqlPool.execute(f"SELECT external_jwt from user_device_auth where external_jwt=\"{externalJWT}\"") and not mysqlPool.execute(f"SELECT external_jwt from admin_device_auth where external_jwt=\"{externalJWT}\""):
                break
        while True:
            internalJWT = create_access_token(identity=username, expires_delta=timedelta(days=3650))
            if not mysqlPool.execute(f"SELECT internal_jwt from user_connection_auth where internal_jwt=\"{internalJWT}\"") and not mysqlPool.execute(f"SELECT internal_jwt from admin_connection_auth where internal_jwt=\"{internalJWT}\""):
                break
        while True:
            userUID = stringGen.AlphaNumeric(50, 51)
            if not mysqlPool.execute(f"SELECT user_uid from user_connection_auth where user_uid=\"{userUID}\"") and not mysqlPool.execute(f"SELECT admin_uid from admin_connection_auth where admin_uid=\"{userUID}\""):
                mysqlPool.execute(f"INSERT INTO user_info values (\"{userUID}\", \"{username}\", now(), \"{name}\")")
                mysqlPool.execute(f"INSERT INTO user_connection_auth values (\"{userUID}\", \"{internalJWT}\", \"{passHash}\")")
                break
        while True:
            deviceUID = stringGen.AlphaNumeric(50, 51)
            if not mysqlPool.execute(f"SELECT device_uid from user_device_auth where device_uid=\"{deviceUID}\"") and not mysqlPool.execute(f"SELECT device_uid from admin_device_auth where device_uid=\"{deviceUID}\""):
                mysqlPool.execute(f"INSERT INTO user_device_auth values (\"{deviceUID}\", \"{userUID}\", \"{externalJWT}\", \"{str(requestObj.user_agent)}\", \"{address}\")")
                break
        statusCode = 200
        statusDesc = ""
        authData["JWT"] = {"DEVICE-JWT": externalJWT}
        authData["DEVICE"] = {"DEVICE-UID": deviceUID}
        logger.skip("REGNEW", str(authData))
    return statusCode, statusDesc, authData


def baseAuthRaw(requestObj: Request) -> tuple[int, str, dict]:
    """
    Login with username and password
    :param requestObj:
    :return:
    """
    address = commonMethods.sqlISafe(requestObj.remote_addr)
    username = commonMethods.sqlISafe(requestObj.form.get("username"))
    password = requestObj.form.get("password")
    userUIDTupList = mysqlPool.execute(f"SELECT user_uid from user_info where username=\"{username}\"")
    authData = {}
    statusCode = 403
    if not userUIDTupList or not userUIDTupList[0]:
        statusDesc = Response403Messages.invalidUsername.value
    else:
        userUID = userUIDTupList[0][0].decode()
        passHashTupList = mysqlPool.execute(f"SELECT pass_hash from user_connection_auth where user_uid=\"{userUID}\"")
        if not passHashTupList or not passHashTupList[0]:
            statusDesc = Response403Messages.incompleteRegistration.value
        else:
            passHash = passHashTupList[0][0].decode()
            if not check_password_hash(passHash, password):
                statusDesc = Response403Messages.incorrectAuth.value
            else:
                statusCode = 200
                statusDesc = Response200Messages.correct.value
                externalJWT = create_access_token(identity=username, expires_delta=timedelta(days=365))
                while True:
                    deviceUID = stringGen.AlphaNumeric(50, 51)
                    if not mysqlPool.execute(f"SELECT device_uid from user_device_auth where device_uid=\"{deviceUID}\"") and not mysqlPool.execute(f"SELECT device_uid from admin_device_auth where device_uid=\"{deviceUID}\""):
                        mysqlPool.execute(f"INSERT INTO user_device_auth values (\"{deviceUID}\", \"{userUID}\", \"{externalJWT}\", \"{str(requestObj.user_agent.string)}\", \"{address}\")")
                        break
                authData["JWT"] = {"DEVICE-JWT": externalJWT}
                authData["DEVICE"] = {"DEVICE-UID": deviceUID}
    return statusCode, statusDesc, authData


def getInternalJWT(userUID:str) -> tuple[int, str, str]:
    """
    If login success, fetch the internal JWT for the current user to send auth to CORE
    :param userUID: UserUID of the requestor
    :return:
    """
    internalJWT = ""
    statusCode = 403
    statusDesc = Response403Messages.authNotFound.value
    if not LOGIN_REQUIRED:
        statusCode = 200
        statusDesc = Response200Messages.correct.value
    else:
        JWTTupList = mysqlPool.execute(f"SELECT internal_jwt from user_connection_auth where user_uid=\"{userUID}\"")
        if not JWTTupList or not JWTTupList[0]: pass
        else:
            internalJWTTupList = mysqlPool.execute(f"SELECT internal_jwt from user_connection_auth where user_uid=\"{userUID}\"")
            statusCode = 200
            statusDesc = Response200Messages.correct.value
            internalJWT = internalJWTTupList[0][0].decode()
    return statusCode, statusDesc, internalJWT


@userGateway.route(f"{Routes.register.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
def registerRawRoute():
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    statusCode, statusDesc, authData = registerNewUser(request)
    logger.success("SENT", f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}")
    return CustomResponse().readValues(statusCode, statusDesc, authData).createFlaskResponse()


@userGateway.route(f"{Routes.authRaw.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
def authenticateRawRoute():
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    statusCode, statusDesc, authData = baseAuthRaw(request)
    logger.success("SENT", f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}")
    return CustomResponse().readValues(statusCode, statusDesc, authData).createFlaskResponse()


@userGateway.route(f"{Routes.renewAuth.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
@onlyAllowedAuth
def checkOldAuthRoute(username, userUID, deviceUID):
    logger.success("SENT", f"{request.url_rule} {deviceUID} {userUID} {username}")
    return CustomResponse().readValues(200, Response200Messages.correct.value, "").createFlaskResponse()


@userGateway.route(f"{Routes.imgRecv.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
@onlyAllowedAuth
def recogniseRoute(username, userUID, deviceUID):
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    statusCode, statusDesc, internalJWT = getInternalJWT(userUID)
    imgBytes = b""
    data = CustomResponse().readValues(200, "NO_IMAGE", "").createDataDict()
    if FETCH_IMAGE:
        try:
            imgBytes = request.files.get("IMG_DATA").stream.read()
            statusCode = 200
            logger.success("IMAGE_EXTRACT", f"in Files SIZE: {len(imgBytes)}")
        except:
            try:
                imgBytes = b64decode(loads(request.data)["IMG_DATA"])
                statusCode = 200
                logger.success("IMAGE_EXTRACT", f"in Data Size: {len(imgBytes)}")
            except:
                data = CustomResponse().readValues(500, "IMG_NOT_FOUND", "").createDataDict()
                penaliseIP(commonMethods.sqlISafe(request.remote_addr))
                logger.fatal("IMAGE_EXTRACT", f"failed")
    if statusCode == 200:
        header = {
            "INTERNAL-JWT": internalJWT,
            "USERNAME": username,
            "USER-UID": userUID,
            "DEVICE-UID": deviceUID,
        }
        try:
            data = post(f"http://127.0.0.1:{Constants.coreServerPort.value}{Routes.imgRecv.value}", headers=header, data=imgBytes).json()
            logger.success("CORE_FWD", f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}")
        except:
            data = CustomResponse().readValues(500, Response500Messages.coreDown.value, "").createDataDict()
            logger.fatal("CORE_FWD", f"Unable to connect")
    return CustomResponse().readDict(data).createFlaskResponse()


@userGateway.route(f"{Routes.requestNewItemUID.value}", methods=["POST", "GET"])
@onlyAllowedMethods
@onlyAllowedIPs
@onlyAllowedAuth
def addNewItemRoute(username, userUID, deviceUID):
    statusCode, statusDesc, internalJWT = getInternalJWT(userUID)
    try:
        header = {
            "INTERNAL-JWT": internalJWT,
            "USERNAME": username,
            "USER-UID": userUID,
            "DEVICE-UID": deviceUID,
        }
        data = post(f"http://127.0.0.1:{Constants.coreServerPort.value}/{Routes.requestNewItemUID.value}", headers=header, data={"ITEMNAME": request.form.get("itemname")}).json()
        logger.success("CORE_FWD", f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}")
    except:
        data = CustomResponse().readValues(500, "CORE_DOWN", "").createDataDict()
        logger.fatal("CORE_FWD", f"Unable to connect")
    return CustomResponse().readDict(data).createFlaskResponse()


@userGateway.before_request
def userBeforeRequest():
    """
    Before any request goes to any route, it passes through this function.
    Applies user remote address correctly (received from proxy)
    :return:
    """
    address = "BANNED"
    if request.remote_addr == "127.0.0.1":
        if request.environ.get("HTTP_X_FORWARDED_FOR") == request.headers.get("X-Forwarded-For"):
            if request.environ.get("HTTP_X_FORWARDED_FOR") is not None:
                address = request.environ.get("HTTP_X_FORWARDED_FOR")
            else:
                address = "LOCAL"
    else:
        address = request.remote_addr
    request.remote_addr = address


print(f"USER GATEWAY: {Constants.userGatewayPort.value}")
WSGIServer(("0.0.0.0",Constants.userGatewayPort.value,),userGateway,log=None,).serve_forever()
