from main import delete_subscription, list_subscriptions

input("Enterを押すとすべてのサブスクリプションを削除します:")

data = list_subscriptions(event_type="google.workspace.meet.participant.v2.joined").json()
print(data)
for subscription in data["subscriptions"]:
    print("Deleting", subscription["name"], "...")
    print(delete_subscription(subscription_name=subscription["name"]).json())

print("Deleted all subscriptions.")
