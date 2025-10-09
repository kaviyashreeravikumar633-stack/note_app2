import requests
import os

API_URLS = {
    "summary": "https://api-inference.huggingface.co/models/facebook/bart-large-cnn",
}

headers = {
    "Authorization": f"Bearer {os.environ.get('HUGGINGFACE_API_KEY')}"
}

def query(payload, type):
    response = requests.post(API_URLS[type], headers=headers, json=payload)
    return response.json()