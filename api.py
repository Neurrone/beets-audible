import json
from typing import Dict, Tuple
from urllib import parse, request
from .book import Book, BookChapters

AUDIBLE_ENDPOINT='https://api.audible.com/1.0/catalog/products'
AUDNEX_ENDPOINT="https://api.audnex.us"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36"

def search_audible(keywords: str) -> Dict:
    params = {
        "response_groups": "product_attrs",
        "num_results": 10,
        "products_sort_by": "Relevance",
        "keywords": keywords
    }
    query = parse.urlencode( params )
    response = json.loads(make_request(f"{AUDIBLE_ENDPOINT}?{query}"))
    return response

def get_book_info(asin: str) -> Tuple[Book, BookChapters]:
    # TODO: investigate running this in parallel?
    book_response = json.loads(make_request(f"{AUDNEX_ENDPOINT}/books/{asin}"))
    chapter_response = json.loads(make_request(f"{AUDNEX_ENDPOINT}/books/{asin}/chapters"))
    book = Book.from_audnex_book(book_response)
    book_chapters = BookChapters.from_audnex_chapter_info(chapter_response)
    return (book, book_chapters)

def make_request(url):
    """
        Makes and returns an HTTP request.
        Retries 4 times, increasing  time between each retry.
    """
    req = request.Request(url, headers={
        # Circumvent audnex's user-agent blocking
        'User-Agent': USER_AGENT,
    })
    with request.urlopen(req) as response:
        return response.read()
