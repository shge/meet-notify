import os

import requests
from dotenv import load_dotenv

load_dotenv()


def send_slack(message: str) -> None:
    try:
        requests.post(
            os.environ["SLACK_WEBHOOK"],
            json={
                "text": message,
                "username": "Meet Bot",
            },
        )
    except Exception as e:
        print(e)
