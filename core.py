from gevent import monkey
monkey.patch_all()

from random import randrange
from threading import Thread
from typing import Dict, Any
from gevent.pywsgi import WSGIServer
from flask import Flask, request, Request
from PIL import Image
from io import BytesIO
from base64 import b64encode
from requests import Session
from json import loads, dumps
from functools import wraps
from dateutil.relativedelta import relativedelta
from datetime import datetime, date
from openai import OpenAI
from pathlib import Path
from customisedLogs import Manager as LogManager
from randomisedString import Generator as StrGen

from internal.Enum import Routes, RequestElements, Constants, commonMethods, Tasks, RequiredFiles, Response200Messages, Response422Messages, Response403Messages, Response500Messages
from internal.SecretEnum import Secrets
from internal.CustomResponse import CustomResponse


LOGIN_REQUIRED = True
COMPRESS_IMAGES = False
DUMMY_RECOGNISER = True
DUMMY_EXPIRY = True


clientOPENAI = OpenAI(api_key=Secrets.GPT4APIKey.value)
logger = LogManager()
stringGen = StrGen()
recognitionServer = Flask("RECOGNITION_API")
mysqlPool = commonMethods.connectDB(logger)


def understandGPTResponseImage(responseContent: str) -> tuple[int, str, list]:
    """
    Tries all known GPT response types and processes the final image recognized JSON from GPT response^
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
    """
    Convert list of items to dictionary of item and its expiry
    :param itemList:
    :return:
    """
    payload = {
        "max_tokens": 1000,
        "model": "gpt-4-turbo-preview",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f""" 
                        You are given a list of groceries. For each item in the provided list, determine 
                        a typical expiry period and assign a duration string formatted as follows: 
                        '<NUMBER> Y/M/W/D', where the duration is expressed in either Year(s) ('Y'), Month(s) ('M'), Week(s) ('W') or 
                        Day(s) ('D'). Only use one unit of time for each item.

                        Based on these durations, create a dictionary mapping each grocery item to its respective 
                        duration string. Then, serialize this dictionary into a JSON string.

                        Ensure the duration for each item is realistic, based on common knowledge about how long 
                        these items typically last before expiring.

                        Input list of groceries (provided as a list of strings):
                        {itemList}

                        Example Output JSON (with hypothetical, not actually correct durations, just to show correct 
                        use of duration format):
                        {{ 
                            "Apple": "2 W", 
                            "Banana": "1 Y", 
                            "Grape": "4 D", 
                            "Egg": "1 M" 
                        }} 
                        """,
                    },
                ],
            }
        ],
    }
    statusCode, statusDesc, itemsWithExpiryDate = sendGPTRequest(payload=payload, task=Tasks.text_gen)
    return statusCode, statusDesc, itemsWithExpiryDate


def recogniseImageGPT(imgBytes: bytes, userUID: str) -> tuple[int, str, dict]:
    """
    Fetch list of items in the image from GPT, or a dummy response if asked for
    :param userUID: User ID which sent the image
    :param imgBytes: raw bytes of the image file received from client.
    :return:
    """
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
                        Create a list of common names of all items included in the image, in their singular form, and output only the python 
                        JSON list. Name each item only in the singular.
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
    statusCode, statusDesc, recognisedItemList = sendGPTRequest(payload, task=Tasks.img_understanding)
    while True:
        purchaseUID = stringGen.AlphaNumeric(50, 51)
        if not mysqlPool.execute(f"SELECT purchase_uid from purchases where purchase_uid=\"{purchaseUID}\""):
            mysqlPool.execute(f"INSERT INTO purchases values (\"{purchaseUID}\", \"{userUID}\", '{dumps(recognisedItemList)}', '{dumps([])}')")
            break
    Thread(target=savePurchaseImage, args=(imgBytes, purchaseUID,)).start()
    itemDict = {}
    for itemName in recognisedItemList:
        _, __, itemUID = itemNameToUID(itemName)
        itemDict[itemUID] = itemName
    return statusCode, statusDesc, {"PURCHASE_UID":purchaseUID, "ITEMS": itemDict}


def sendGPTRequest(payload: Dict[str, Any], task: Tasks) -> tuple[int, str, list | dict[str, date]]:
    """
    Common method to send request to GPT.
    :param payload: Data to send
    :param task: Purpose of sending
    :return:
    """
    statusCode, statusDesc = 500, Response500Messages.dummy.value
    response:list|dict[str, date] = []
    try:
        gtpSession = Session()
        gtpSession.headers = RequestElements.GPTHeaders.value
        responseJSON = gtpSession.post("https://api.openai.com/v1/chat/completions", json=payload).json()
        responseContent = responseJSON["choices"][0]["message"]["content"]
        match task:
            case Tasks.img_understanding:
                statusCode, statusDesc, response = understandGPTResponseImage(responseContent)
            case Tasks.text_gen:
                statusCode, statusDesc, response = 200, Response200Messages.correct.value, loads(responseContent)
    except Exception as e:
        statusCode = 422
        statusDesc = Response422Messages.postErrorGPT.value
        logger.fatal("GPTPOST", repr(e))
        response = [] if task == Tasks.img_understanding else {}
    return statusCode, statusDesc, response


def itemNameToUID(itemName:str):
    """
    Fetch UID for any item name, or generate a new one if name not exists
    :param itemName: Name of the item to ask for UID
    :return:
    """
    itemUIDTupList =  mysqlPool.execute(f"SELECT item_uid from known_items where name=\"{itemName}\"")
    if not itemUIDTupList or not itemUIDTupList[0]:
        while True:
            itemUID = stringGen.AlphaNumeric(50, 51)
            if not mysqlPool.execute(f"SELECT item_uid from known_items where item_uid=\"{itemUID}\""):
                mysqlPool.execute(f"INSERT INTO known_items (item_uid, name) values (\"{itemUID}\", \"{itemName}\")")
                break
    else:
        itemUID = itemUIDTupList[0][0].decode()
    return 200, "", itemUID


def fetchDurationDB(itemName: str) -> tuple[int, str, str]:
    """
    Fetch Duration from database or return None
    :param itemName:
    :return:
    """
    statusCode = 500
    statusDesc = Response500Messages.durationNotFound.value
    itemDuration = ""
    itemUIDTupList = mysqlPool.execute(f"SELECT item_uid from known_items where name=\"{itemName}\"")
    if itemUIDTupList and itemUIDTupList[0][0]:
        itemUID = itemUIDTupList[0][0].decode()
        itemDurationTupList = mysqlPool.execute(f"SELECT duration from known_items where item_uid=\"{itemUID}\"")
        if itemDurationTupList and itemUIDTupList[0][0]:
            itemDuration = itemDurationTupList[0][0]
            if itemDuration is not None:
                statusCode = 200
                statusDesc = Response200Messages.correct.value
    return statusCode, statusDesc, itemDuration


def attachExpiry(purchaseItemDict: dict) -> tuple[int, str, dict]:
    itemDict = purchaseItemDict["ITEMS"]
    if DUMMY_EXPIRY:
        statusCode, statusDesc = 200, Response200Messages.dummyExpiry.value
        expiryDict = {}
        for itemUID in itemDict:
            itemName = itemDict[itemUID]
            d = date(randrange(2024, 2025), randrange(1, 13), randrange(1, 29))
            expiryDict[itemUID] = {"NAME":itemName, "EXPIRES": f"{str(d.year).zfill(4)}-{str(d.month).zfill(2)}-{str(d.day).zfill(2)}"}
    else:
        statusCode, statusDesc = 200, Response200Messages.correct.value
        expiryDict = {}
        unknownItems = []
        nameToUID = {}
        for itemUID in itemDict:
            itemName = itemDict[itemUID]
            nameToUID[itemName] = itemUID
            expiryDict[itemUID] = {"NAME":itemName}
            statusCode, statusDesc, duration = fetchDurationDB(itemName)
            if expiryDict == 200:
                expiryDict[itemUID]["EXPIRES"] = durationStrToExpiryStr(duration)
            else:
                unknownItems.append(itemName)
        if unknownItems:
            statusCode, statusDesc, GPTFetchedExpiry = fetchDurationGPT(unknownItems)
            if statusCode == 200:
                for itemName in GPTFetchedExpiry:
                    mysqlPool.execute(f"UPDATE known_items set duration=\"{GPTFetchedExpiry[itemName]}\" where item_uid=\"{nameToUID[itemName]}\"")
                    expiryDict[nameToUID[itemName]]["EXPIRES"] = durationStrToExpiryStr(GPTFetchedExpiry[itemName])

    expiryAttachedDict = purchaseItemDict
    expiryAttachedDict["ITEMS"] = expiryDict
    return statusCode, statusDesc, expiryAttachedDict


def durationStrToExpiryStr(duration_str) -> str:
    """
    Parses a duration string (e.g., "30 D", "2 W", "3 M", "2 Y") and returns a datetime object.
    - "D" stands for days
    - "W" stands for weeks
    - "M" stands for months
    - "Y" stands for years
    """
    try:
        num, unit = duration_str.split()
        num, unit = int(num), unit.strip().upper()
    except:
        unit = duration_str[-1]
        num = duration_str[:-1]
    now = datetime.now()
    expires = datetime.now()
    if unit == "D":
        expires = now + relativedelta(days=num)
    elif unit == "W":
        expires = now + relativedelta(weeks=num)
    elif unit == "M":
        expires = now + relativedelta(months=num)
    elif unit == "Y":
        expires = now + relativedelta(years=num)
    return f"{str(expires.year).zfill(4)}-{str(expires.month).zfill(2)}-{str(expires.day).zfill(2)}"


def savePurchaseImage(imgBytes, purchaseUID) -> None:
    """
    Save the image for future reference
    :param purchaseUID: purchase UID or image UID
    :param imgBytes: bytes received from the client
    :return: None
    """
    if imgBytes:
        imgObj = Image.open(BytesIO(imgBytes))
        imgObj = imgObj.convert("RGB")
        pathToSave = Path(RequiredFiles.purchaseImageFolder.value, purchaseUID).with_suffix(".jpg")
        imgObj.save(
            pathToSave,
            optimize=True,
            quality=50 if COMPRESS_IMAGES else 100,
            format="JPEG",
        )
        logger.success("IMGSAVE", f"{purchaseUID} saved")
    else:
        logger.info("IMGSAVE", f"Dummy image")


def baseRecognise(requestObj: Request|bytes) -> tuple[int, str, dict]:
    """
    All image processing starts here. Fetches files from flask request and starts the recognizing process.
    :param requestObj: Flask Request object
    :return: statusCode and the final processed json/dict
    """
    imgBytes = requestObj.data
    userUID = requestObj.environ.get('USER-UID')
    logger.success("IMAGE_EXTRACT", f"SIZE: {len(imgBytes)}")
    if DUMMY_RECOGNISER: statusCode, statusDescRecogniser, purchaseItemDict = 200, Response200Messages.dummyRecogniser.value, {"PURCHASE_UID":"", "ITEMS": {"1":"APPLE", "2":"BANANA", "3":"MILK", "4":"MEAT"}}
    else: statusCode, statusDescRecogniser, purchaseItemDict = recogniseImageGPT(imgBytes, userUID)
    statusCode, statusDescExpiry, itemDict = attachExpiry(purchaseItemDict)
    return statusCode, f"{statusDescRecogniser}_{statusDescExpiry}", itemDict


def matchInternalJWT(flaskFunction):
    """
    Authentication Decorator to allow only matching (internalJWT, userUID, deviceUID, username) values
    :param flaskFunction: the function to switch context to if auth succeeds
    :return:
    """
    def __checkJWTCorrectness(request:Request):
        """
        Fetch values from request and match with DB
        :param request: Flask Request object
        :return: bool stating if values matched
        """
        username = commonMethods.sqlISafe(request.headers.get("USERNAME"))
        deviceUID = commonMethods.sqlISafe(request.headers.get("DEVICE-UID"))
        userUID = commonMethods.sqlISafe(request.headers.get("USER-UID"))
        internalJWT = commonMethods.sqlISafe(request.headers.get("INTERNAL-JWT"))
        userUIDExpectedTupList  = mysqlPool.execute(f"SELECT user_uid from user_connection_auth where internal_jwt=\"{internalJWT}\" and user_uid=\"{userUID}\"")
        userUIDReal = ""
        if len(userUIDExpectedTupList) == 1:
            userUIDReal = userUIDExpectedTupList[0][0].decode()
        if username and deviceUID and userUID and internalJWT and userUIDReal and userUIDReal == userUID:
            return True, userUID, deviceUID
        return False, "", ""
    @wraps(flaskFunction)
    def wrapper():
        """
        Function to decide if all requests are allowed or only recognised ones, else return a 403
        :return: Flask response object
        """
        if LOGIN_REQUIRED:
            jwtCorrect, userUID, deviceUID = __checkJWTCorrectness(request)
            if not jwtCorrect:
                logger.failed("JWT", f"{request.url_rule} incorrect")
                statusCode = 403
                statusDesc = Response403Messages.coreRejectedAuth.value
                return CustomResponse().readValues(statusCode, statusDesc, "").createFlaskResponse()
        else:
            userUID, deviceUID = "", ""
        return flaskFunction(userUID, deviceUID)
    return wrapper


@recognitionServer.route(f"{Routes.imgRecv.value}", methods=["POST", "GET"])
@matchInternalJWT
def recogniseRoute(userUID, deviceUID):
    """
    One and only Image receive and recognition route.
    :param userUID:
    :param deviceUID:
    :return:
    """
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    request.environ["USER-UID"] = userUID
    request.environ["DEVICE-UID"] = deviceUID
    statusCode, statusDesc, recognisedData = baseRecognise(request)
    logger.success("SENT",f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}",)
    return CustomResponse().readValues(statusCode, statusDesc, recognisedData).createFlaskResponse()


@recognitionServer.route(f"{Routes.requestNewItemUID.value}", methods=["POST"])
@matchInternalJWT
def createNewItemUIDRoute(userUID, deviceUID):
    """
    Add new item to known items
    :param userUID:
    :param deviceUID:
    :return:
    """
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
    request.environ["USER-UID"] = userUID
    request.environ["DEVICE-UID"] = deviceUID
    statusCode, statusDesc, newUID = itemNameToUID(request.form.get("ITEMNAME"))
    logger.success("SENT",f"{request.url_rule} response [{statusCode}: {statusDesc}] sent to {request.remote_addr}",)
    return CustomResponse().readValues(statusCode, statusDesc, newUID).createFlaskResponse()


print(f"CORE: {Constants.coreServerPort.value}")
WSGIServer(("127.0.0.1",Constants.coreServerPort.value,),recognitionServer,log=None,).serve_forever()
