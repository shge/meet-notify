import os

from dotenv import load_dotenv

from main import create_space, subscribe_to_space

load_dotenv()

if __name__ == "__main__":
    subscription = subscribe_to_space(
        topic_name=os.environ["TOPIC_NAME"], space_name=os.environ["SPACE_NAME"]
    )
    print(subscription.json().get("response"))
