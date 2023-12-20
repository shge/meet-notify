from main import list_subscriptions

if __name__ == "__main__":
    data = list_subscriptions(
        event_type="google.workspace.meet.participant.v2.joined"
    ).json()
    print(data)
    for subscription in data["subscriptions"]:
        print(subscription)
