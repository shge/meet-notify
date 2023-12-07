# Google Meet Slack Notifier
This is a simple script that sends a message to a Slack channel when a participant joins or leaves a Google Meet meeting.

## Setup

```
mv .env.example .env
mv .env.yaml.example .env.yaml
```

1. Edit `.env` and `.env.yaml`.
2. Add your Artifact Registry repository name to the first line of `requirements.txt`.

```
pip install -r requirements.txt
```

## Run

```
python main.py
```

to run locally.

## Deploy

```
gcloud functions deploy your-function-name \
--gen2 \
--runtime=python312 \
--region=asia-northeast1 \
--source=. \
--entry-point=subscribe \
--trigger-topic=your-topic-name \
--env-vars-file .env.yaml
```

to deploy to Cloud Functions.
