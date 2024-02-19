import os

from gevent import monkey

monkey.patch_all()

from threading import Thread
from gevent.pywsgi import WSGIServer
from flask import Flask, request, Request
from PIL import Image
from io import BytesIO
from base64 import b64encode, b64decode
from requests import Session
from json import loads
from functools import wraps

from internal.Enum import Routes, GPTElements, Constants, Secrets, commonMethods
from internal.Logger import Logger
from internal.StringGenerator import randomGenerator
from internal.CustomResponse import CustomResponse
from internal.MysqlPool import mysqlPool as MySQLPool

STATIC_FOLDER = "savedimages/"
COMPRESS_IMAGES = False
RECOGNISE_IMAGE = False
RECOGNISE_DATES = False
DELETE_IMAGE_FILES = False

mysqlPool: MySQLPool | None = None
logger = Logger()
stringGen = randomGenerator()
recognitionServer = Flask("RECOGNITION_API")
activeFiles = set()


def connectDB() -> None:
    """
    Blocking function to connect to DB and check connection
    :return: None
    """
    global mysqlPool
    for host in [os.getenv("DNS_SERVER")]:
        try:
            mysqlPool = MySQLPool(
                user="root",
                password=Secrets.DBPassword.value,
                dbName="bestbybuddy",
                host=host,
            )
            mysqlPool.execute("show databases")
            logger.success("DB", f"connected to: {host}")
            break
        except:
            logger.critical("DB", f"failed: {host}")
    else:
        logger.fatal("DB", "Unable to connect to bestbybuddy")
        input("EXIT...")
        exit(0)


def fetchDurationDB(itemName: str) -> tuple[int, str, str]:
    """
    Fetch Duration from database or return None
    :param itemName:
    :return:
    """
    statusCode = 500
    statusDesc = "DUR_UNAVAILABLE"
    itemDuration = ""
    itemUIDTupList = mysqlPool.execute(
        f'SELECT item_uid from known_items where name="{itemName}"'
    )
    if itemUIDTupList and itemUIDTupList[0][0]:
        itemUID = itemUIDTupList[0][0]
        itemDurationTupList = mysqlPool.execute(
            f'SELECT duration from known_items where item_uid="{itemUID}"'
        )
        if itemDurationTupList and itemUIDTupList[0][0]:
            itemDuration = itemDurationTupList[0][0]
            statusCode = 200
            statusDesc = ""
    return statusCode, statusDesc, itemDuration


def attachExpiry(itemList: list) -> tuple[int, str, dict]:
    expiryAttachedDict = {}
    unknownItems = []
    for item in itemList:
        statusCode, statusDesc, duration = fetchDurationDB(item)
        if statusCode == 200:
            expiryAttachedDict[item] = duration
        else:
            unknownItems.append(item)
    GPTFetchedDuration = fetchDurationGPT(unknownItems)
    for item in GPTFetchedDuration:
        expiryAttachedDict[item] = GPTFetchedDuration[item]
    return 200, "", expiryAttachedDict


def understandGPTResponseImage(responseContent: str) -> tuple[int, str, list]:
    """
    Tries all known GPT response types and processes the final image recognized JSON from GPT response
    :param responseContent: Response from GPT
    :return: status code and list of processed items
    """

    ## process 1: for returning only a list of items
    testStr = responseContent
    try:
        return 200, "", loads("[" + testStr.split("[")[1].split("]")[0] + "]")
    except:
        return 422, "PARSE_FAIL", []


def fetchDurationGPT(itemList: list) -> tuple[int, str, dict]:
    payload = {
        "max_tokens": 1000,
        "model": "gpt-4-turbo-preview	",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
                        You are given a list of groceries. 
                        Create a dictionary with recommendations for the expiry dates of all grocery items and output the dictionary as a JSON. 
                        Do not output anything but the JSON. 
                    
                        Example Input JSON:
                            groceries = [
                                "Apple",
                                "Grape",
                                "Yogurt"
                            ]
                            
                        Example Output JSON:
                            dict = {
                                "Apple": Duration,
                                "Grape": Duration,
                                "Yogurt": Duration,
                            }
                            """,
                    },
                ],
            }
        ],
    }

    pass


def recogniseImageGPT(imgBytes: bytes) -> tuple[int, str, list]:
    """
    Fetch list of items in the image from GPT, or a dummy response if asked for
    :param imgBytes: raw bytes of the image file received from client.
    :return:
    """
    if not RECOGNISE_IMAGE:
        return 200, "DUMMY_IMAGE_RECOGNISER", ["APPLE", "BANANA", "PAPAYA"]

    payload = {
        "max_tokens": 300,
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
                        You are given an image of groceries. 
                        Create a list of common names of all items included in the image and output only the python JSON list. 
                        Do not output anything but the JSON. 
                    
                        Example JSON:
                            groceries = [
                                "Apple",
                                "Grape",
                                "Yogurt"
                            ]""",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64encode(imgBytes).decode()}",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
    }
    recognisedItemList, statusCode, statusDesc = send_request(payload)
    return statusCode, statusDesc, recognisedItemList


def send_request(payload):
    try:
        gtpSession = Session()
        gtpSession.headers = GPTElements.headers.value
        responseJSON = gtpSession.post(
            "https://api.openai.com/v1/chat/completions", json=payload
        ).json()
        responseContent = responseJSON["choices"][0]["message"]["content"]
        statusCode, statusDesc, recognisedItemList = understandGPTResponseImage(
            responseContent
        )
    except Exception as e:
        statusCode = 422
        statusDesc = "GPT_POST_ERROR"
        logger.fatal("GPTPOST", repr(e))
    return recognisedItemList, statusCode, statusDesc


def saveImage(imgBytes, purchaseUID) -> None:
    """
    Save the image for future reference
    :param purchaseUID: purchase UID or image UID
    :param imgBytes: bytes received from the client
    :return: None
    """
    imgObj = Image.open(BytesIO(imgBytes))
    imgObj = imgObj.convert("RGB")
    imgObj.save(
        f"{STATIC_FOLDER}{purchaseUID}",
        optimize=True,
        quality=50 if COMPRESS_IMAGES else 100,
        format="JPEG",
    )
    logger.success("IMGSAVE", f"{purchaseUID} saved")


def baseRecognise(requestObj: Request) -> tuple[int, str, dict]:
    """
    All image processing starts here. Fetches files from flask request and starts the recognizing process.
    :param requestObj: Flask Request object
    :return: statusCode and the final processed json/dict
    """
    itemDict = {}
    imgBytes = b""
    try:
        imgBytes = requestObj.files.get("IMG_DATA").stream.read()
        statusCode = 200
        statusDesc = ""
        logger.success("IMAGE_EXTRACT", f"in Files SIZE: {len(imgBytes)}")
    except:
        try:
            imgBytes = b64decode(loads(requestObj.data)["IMG_DATA"])
            statusCode = 200
            statusDesc = ""
            logger.success("IMAGE_EXTRACT", f"in Data Size: {len(imgBytes)}")
        except:
            statusCode = 500
            statusDesc = "IMG_NOT_FOUND"
            logger.fatal("IMAGE_EXTRACT", f"failed")
    if statusCode == 200:
        statusCode, statusDesc, itemList = recogniseImageGPT(imgBytes)
        if statusCode == 200:
            while True:
                purchaseUID = randomGenerator().AlphaNumeric(50, 51)
                if mysqlPool.execute(
                    f'SELECT purchase_uid from purchases where purchase_uid="{purchaseUID}"'
                ):
                    mysqlPool.execute(
                        f"INSERT INTO purchases values (\"{purchaseUID}\", \"{request.environ.get('USER_UID')}\", {itemList}, {{}})"
                    )
                    break
            Thread(
                target=saveImage,
                args=(
                    imgBytes,
                    purchaseUID,
                ),
            ).start()
            statusCode, statusDesc, itemDict = attachExpiry(itemList)
    return statusCode, statusDesc, itemDict


def matchInternalJWT(flaskFunction):
    """
    Authentication Decorator to allow only matching (internalJWT, userUID, deviceUID, username) values
    :param flaskFunction: the function to switch context to if auth succeeds
    :return:
    """

    def __checkJWTCorrectness(request):
        """
        Fetch values from request and match with DB
        :param request: Flask Request object
        :return: bool stating if values matched
        """
        username = commonMethods.sqlISafe(request.headers.get("USERNAME"))
        deviceUID = commonMethods.sqlISafe(request.headers.get("DEVICE-UID"))
        userUID = commonMethods.sqlISafe(request.headers.get("USER-UID"))
        internalJWT = commonMethods.sqlISafe(request.headers.get("INTERNAL-JWT"))
        userUIDTupList = mysqlPool.execute(
            f'SELECT user_uid from user_info where username="{username}" and internal_jwt="{internalJWT}" and user_uid="{userUID}"'
        )
        if userUIDTupList and userUIDTupList[0]:
            return True, userUID, deviceUID
        return False, "", ""

    @wraps(flaskFunction)
    def wrapper():
        """
        Function to decide if all requests are allowed or only recognised ones, else return a 403
        :return: Flask response object
        """
        jwtCorrect, userUID, deviceUID = __checkJWTCorrectness(request)
        if jwtCorrect:
            return flaskFunction(userUID, deviceUID)
        else:
            logger.critical("JWT", f"{request.url_rule} incorrect")
            statusCode = 403
            statusDesc = "SERVER_OOS"
            return (
                CustomResponse()
                .readValues(statusCode, statusDesc, "")
                .createFlaskResponse()
            )

    return wrapper


@recognitionServer.route(f"/{Routes.imgRecv.value}", methods=["POST"])
@matchInternalJWT
def recogniseRoute(userUID, deviceUID):
    """
    One and only Image receive and recognition route.
    :param userUID:
    :param deviceUID:
    :return:
    """
    request.environ["USER_UID"] = userUID
    request.environ["DEVICE_UID"] = deviceUID
    statusCode, statusDesc, recognisedData = baseRecognise(request)
    logger.success(
        "SENT",
        f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}",
    )
    return (
        CustomResponse()
        .readValues(statusCode, statusDesc, recognisedData)
        .createFlaskResponse()
    )


connectDB()
WSGIServer(
    (
        "127.0.0.1",
        Constants.coreServerPort.value,
    ),
    recognitionServer,
    log=None,
).serve_forever()
