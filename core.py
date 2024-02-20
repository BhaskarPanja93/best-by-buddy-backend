from gevent import monkey

monkey.patch_all()

from threading import Thread
from typing import Dict, Any
from gevent.pywsgi import WSGIServer
from flask import Flask, request, Request
from PIL import Image
from io import BytesIO
from base64 import b64encode
from requests import Session
from json import loads
from functools import wraps
from dateutil.relativedelta import relativedelta
from datetime import datetime, date
from dotenv import load_dotenv
from openai import OpenAI
import uuid
from pathlib import Path

from internal.Enum import Routes, GPTElements, Constants, Secrets, commonMethods, Tasks
from internal.Logger import Logger
from internal.StringGenerator import randomGenerator
from internal.CustomResponse import CustomResponse
from internal.MysqlPool import mysqlPool as MySQLPool

load_dotenv()


client = OpenAI()

STATIC_FOLDER = "savedimages/"
LOGIN_REQUIRED = False
COMPRESS_IMAGES = False
RECOGNISE_IMAGE = False
USE_DUMMY_IMAGE = False
RECOGNISE_DATES = False
ATTACH_IMAGES = False
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
    for host in ["127.0.0.1"]:
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
    if not RECOGNISE_DATES:
        return (
            200,
            "DUMMY_DATES",
            {
                "APPLE": date(2024, 2, 27),
                "BANANA": date(2024, 2, 27),
                "PAPAYA": date(2024, 2, 27),
            },
        )

    expiryAttachedDict = {}
    unknownItems = []
    for item in itemList:
        statusCode, statusDesc, duration = fetchDurationDB(item)
        if statusCode == 200:
            expiryAttachedDict[item] = duration
        else:
            unknownItems.append(item)

    statusCode, statusDesc, itemsWithGPTExpiryDate = fetchDurationGPT(unknownItems)
    if statusCode == 200:
        expiryAttachedDict.update(itemsWithGPTExpiryDate)
        return 200, "", expiryAttachedDict
    else:
        return 500, "DUR_UNAVAILABLE", expiryAttachedDict


def attachImageURL(itemList: dict) -> tuple[int, str, dict]:
    if not ATTACH_IMAGES:
        return (
            200,
            "DUMMY_FINAL",
            {
                "APPLE": {"IMG": "http://someimage.jpg", "EXPIRES": date(2024, 2, 27)},
                "BANANA": {
                    "IMG": "http://someimage2.jpg",
                    "EXPIRES": date(2024, 2, 29),
                },
            },
        )

    expiryAttachedDict = {}
    unknownItems = []
    for item in itemList:
        statusCode, statusDesc, duration = fetchDurationDB(item)
        if statusCode == 200:
            expiryAttachedDict[item] = duration
        else:
            unknownItems.append(item)

    statusCode, statusDesc, itemsWithGPTExpiryDate = fetchDurationGPT(unknownItems)
    if statusCode == 200:
        expiryAttachedDict.update(itemsWithGPTExpiryDate)
        return 200, "", expiryAttachedDict
    else:
        return 500, "DUR_UNAVAILABLE", expiryAttachedDict


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


def understandGPTResponseText(
    responseContent: str,
) -> tuple[int, str, Dict[str, date]]:
    """
    Tries all known GPT response types and processes the final expiry date recommendations recognized from the given
    JSON from GPT response
    :param responseContent: Response from GPT
    :return: status code and dictionary of items with suggested expiry date
    """
    try:
        return 200, "", parse_expiry_suggestions(responseContent)
    except:
        return 422, "PARSE_FAIL", {}


def parse_expiry_suggestions(responseContent: str) -> Dict[str, date]:
    parsed = dict()
    mapping = loads(responseContent)
    for item, expiry_date in mapping.items():
        parsed[item] = parse_str_to_datetime(duration_str=expiry_date).date()

    return parsed


def parse_str_to_datetime(duration_str) -> datetime:
    """
    Parses a duration string (e.g., "30 D", "2 W", "3 M") and returns a datetime object.
    - "D" stands for days
    - "W" stands for weeks
    - "M" stands for months
    """
    num, unit = duration_str.split()
    num = int(num)
    now = datetime.now()

    if unit == "D":
        return now + relativedelta(days=num)
    elif unit == "W":
        return now + relativedelta(weeks=num)
    elif unit == "M":
        return now + relativedelta(months=num)
    else:
        raise ValueError("Unknown duration unit")


def fetchDurationGPT(itemList: list) -> tuple[int, str, dict]:
    if not RECOGNISE_IMAGE:
        return (
            200,
            "DUMMY_EXPIRY_DATES",
            {
                "APPLE": {"IMG": "http://someimage.jpg", "EXPIRES": date(2024, 2, 27)},
                "BANANA": {
                    "IMG": "http://someimage2.jpg",
                    "EXPIRES": date(2024, 2, 29),
                },
            },
        )

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
                        '<NUMBER> M/W/D', where the duration is expressed in either Month(s) ('M'), Week(s) ('W') or 
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
                            "Apple": "1 W", 
                            "Grape": "4 D", 
                            "Egg": "1 M" 
                        }} 
                        """,
                    },
                ],
            }
        ],
    }
    statusCode, statusDesc, itemsWithExpiryDate = send_request(
        payload=payload, task=Tasks.text_gen
    )

    return statusCode, statusDesc, itemsWithExpiryDate


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
    statusCode, statusDesc, recognisedItemList = send_request(
        payload, task=Tasks.img_understanding
    )
    return statusCode, statusDesc, recognisedItemList


def send_request(
    payload: Dict[str, Any], task: Tasks
) -> tuple[int, str, list | dict[str, date]]:
    try:
        gtpSession = Session()
        gtpSession.headers = GPTElements.headers.value
        responseJSON = gtpSession.post(
            "https://api.openai.com/v1/chat/completions", json=payload
        ).json()
        responseContent = responseJSON["choices"][0]["message"]["content"]
        match task:
            case Tasks.img_understanding:
                statusCode, statusDesc, response = understandGPTResponseImage(
                    responseContent
                )
            case Tasks.text_gen:
                statusCode, statusDesc, response = understandGPTResponseText(
                    responseContent
                )
    except Exception as e:
        statusCode = 422
        statusDesc = "GPT_POST_ERROR"
        logger.fatal("GPTPOST", repr(e))
        response = [] if task == Tasks.img_understanding else {}
    return statusCode, statusDesc, response


def generate_icon(item_name: str) -> tuple[int, str, Any]:
    if USE_DUMMY_IMAGE:
        return 200, "DUMMY_IMAGE", Path(STATIC_FOLDER, "apple.jpg")

    response = client.images.generate(
        model="dall-e-3",
        prompt=f"Generate an icon for '{item_name}'",
        size="1024x1024",
        quality="standard",
        n=1,
    )

    image_url = response.data[0].url

    statusCode, statusDesc, icon_uid = download_image()

    return statusCode, statusDesc, icon_uid


def download_image():
    pass


def generate_item_uid(item_name):
    """
    Generates a unique identifier for an item by combining a UUID with the item's name.

    Parameters:
    - item_name: The name of the item (e.g., "Apple", "Banana").

    Returns:
    A tuple containing the unique identifier (item_uid) and the path to the item's icon.
    """
    # Generate a unique UUID
    unique_id = str(uuid.uuid4())
    # Create the item_uid by combining the UUID with the item name
    item_uid = f"{unique_id}-{item_name}"

    # Assuming a simple function to get the path to an item's icon based on its name
    icon_path = get_icon_path(item_name)

    return item_uid, icon_path


def saveImage(imgBytes, purchaseUID) -> None:
    """
    Save the image for future reference
    :param purchaseUID: purchase UID or image UID
    :param imgBytes: bytes received from the client
    :return: None
    """
    if imgBytes:
        imgObj = Image.open(BytesIO(imgBytes))
        imgObj = imgObj.convert("RGB")
        imgObj.save(
            f"{STATIC_FOLDER}{purchaseUID}",
            optimize=True,
            quality=50 if COMPRESS_IMAGES else 100,
            format="JPEG",
        )
        logger.success("IMGSAVE", f"{purchaseUID} saved")
    else:
        logger.info("IMGSAVE", f"Dummy image")


def baseRecognise(requestObj: Request) -> tuple[int, str, dict]:
    """
    All image processing starts here. Fetches files from flask request and starts the recognizing process.
    :param requestObj: Flask Request object
    :return: statusCode and the final processed json/dict
    """
    imgBytes = requestObj.data
    statusCode, statusDesc, itemList = recogniseImageGPT(imgBytes)
    statusCode, statusDesc, itemDict = attachExpiry(itemList)
    statusCode, statusDesc, itemDict = attachImageURL(itemDict)
    if statusCode == 200:
        while True:
            purchaseUID = randomGenerator().AlphaNumeric(50, 51)
            if not mysqlPool.execute(
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
        if LOGIN_REQUIRED:
            jwtCorrect, userUID, deviceUID = __checkJWTCorrectness(request)
            if not jwtCorrect:
                logger.critical("JWT", f"{request.url_rule} incorrect")
                statusCode = 403
                statusDesc = "SERVER_OOS"
                return (
                    CustomResponse()
                    .readValues(statusCode, statusDesc, "")
                    .createFlaskResponse()
                )
        else:
            userUID, deviceUID = "", ""

        return flaskFunction(userUID, deviceUID)

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
    logger.skip("RECV", f"{request.url_rule} {request.remote_addr}")
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


print(f"CORE: {Constants.coreServerPort.value}")
connectDB()
WSGIServer(
    (
        "127.0.0.1",
        Constants.coreServerPort.value,
    ),
    recognitionServer,
    log=None,
).serve_forever()


# if __name__ == "__main__":
#     pprint(
#         fetchDurationGPT(
#             ["Pineapple", "Banana", "Chicken thigh", "Pork ribs", "Fresh lentils"]
#         )
#     )

# # Example output from fetchDurationGPT:
# (200,
#  '',
#  {'Banana': datetime.date(2024, 2, 27),
#   'Chicken thigh': datetime.date(2024, 2, 27),
#   'Fresh lentils': datetime.date(2024, 4, 20),
#   'Pineapple': datetime.date(2024, 2, 27),
#   'Pork ribs': datetime.date(2024, 3, 5)})
