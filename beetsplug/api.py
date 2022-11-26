import json
import xml.etree.ElementTree as ET
from time import sleep
from typing import Dict, Tuple
from urllib import parse, request
from urllib.error import HTTPError

from .book import Book, BookChapters

AUDIBLE_ENDPOINT = "https://api.audible.com/1.0/catalog/products"
AUDNEX_ENDPOINT = "https://api.audnex.us"
GOODREADS_ENDPOINT = "https://www.goodreads.com/search/index.xml"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/"
    "35.0.1916.47 Safari/537.36"
)


def search_audible(keywords: str) -> Dict:
    params = {
        "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series",
        "num_results": 10,
        "products_sort_by": "Relevance",
        "keywords": keywords,
    }
    query = parse.urlencode(params)
    response = json.loads(make_request(f"{AUDIBLE_ENDPOINT}?{query}"))
    return response


def search_goodreads(api_key: str, keywords: str) -> ET.Element:
    params = {"key": api_key, "q": keywords}
    query = parse.urlencode(params)
    url = f"{GOODREADS_ENDPOINT}?{query}"
    return ET.fromstring(make_request(url))


def get_book_info(asin: str) -> Tuple[Book, BookChapters]:
    book_response = json.loads(make_request(f"{AUDNEX_ENDPOINT}/books/{asin}"))
    chapter_response = json.loads(make_request(f"{AUDNEX_ENDPOINT}/books/{asin}/chapters"))
    book = Book.from_audnex_book(book_response)
    book_chapters = BookChapters.from_audnex_chapter_info(chapter_response)
    return book, book_chapters


def make_request(url: str) -> bytes:
    """Makes a request to the specified url and returns received response
    The request will be retried up to 3 times in case of failure.
    """
    num_retries = 3
    sleep_time = 2
    for n in range(0, num_retries):
        try:
            req = request.Request(
                url,
                headers={
                    # Circumvent audnex's user-agent blocking
                    "User-Agent": USER_AGENT,
                },
            )
            with request.urlopen(req) as response:
                return response.read()
        except HTTPError as e:
            if e.code == 404:
                print(f"Error while requesting {url}: status code {e.code}, {e.reason}")
                raise e
            print(f"Error while requesting {url}, attempt {n+1}/{num_retries}: status code {e.code}, {e.reason}")
            if n < num_retries - 1:
                sleep(sleep_time)
                sleep_time *= n
            else:
                raise e
