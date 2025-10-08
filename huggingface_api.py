import requests

API_URLS = {
    "summary": "https://api-inference.huggingface.co/models/facebook/bart-large-cnn",
}

headers = {
    "Authorization": "Bearer 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"
}

def query(payload, type):
    response = requests.post(API_URLS[type], headers=headers, json=payload)
    return response.json()