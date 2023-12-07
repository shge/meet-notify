from main import list_subscriptions, delete_subscription

input("Enterを押すとすべてのサブスクリプションを削除します:")

data = list_subscriptions(event_type="google.workspace.meet.participant.v2.joined").json()
for subscription in data["subscriptions"]:
    print("Deleting", subscription["name"], "...")
    print(delete_subscription(subscription_name=subscription["name"]).json())

print("Deleted all subscriptions.")
