import json
from urllib import parse, request

AUDIBLE_ENDPOINT='https://api.audible.com/1.0/catalog/products'

def search_audible(keywords: str):
    print(f"searching for {keywords}")
    params = {
        "response_groups": "contributors,product_desc,product_attrs,product_extended_attrs,series,media",
        "num_results": 10,
        "products_sort_by": "Relevance",
        "keywords": keywords
    }
    query = parse.urlencode( params )
    response = json.loads(make_request(f"{AUDIBLE_ENDPOINT}?{query}"))
    # print(response)
    return response

def make_request(url):
    """
        Makes and returns an HTTP request.
        Retries 4 times, increasing  time between each retry.
    """
    with request.urlopen(url) as response:
        return response.read()
