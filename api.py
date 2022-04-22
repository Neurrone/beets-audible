import json
import xml.etree.ElementTree as ET
from time import sleep
from typing import Dict, Tuple
from urllib import parse, request
from urllib.error import HTTPError, URLError
from .book import Book, BookChapters

AUDIBLE_ENDPOINT="https://api.audible.com/1.0/catalog/products"
AUDNEX_ENDPOINT="https://api.audnex.us"
GOODREADS_ENDPOINT="https://www.goodreads.com"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36"

def search_audible(keywords: str) -> Dict:
    params = {
        "response_groups": "contributors,product_attrs,product_desc,product_extended_attrs,series",
        "num_results": 10,
        "products_sort_by": "Relevance",
        "keywords": keywords
    }
    query = parse.urlencode( params )
    response = json.loads(make_request(f"{AUDIBLE_ENDPOINT}?{query}"))
    return response

def search_goodreads(asin: str, api_key: str) -> Dict:
    goodreads_response = ET.fromstring(make_request(f"{GOODREADS_ENDPOINT}/search/index.xml?key={api_key}&q={asin}"))

    totalresults = int(goodreads_response.findtext("./search/total-results"))
    original_date = {}

    if totalresults == 1:
        #if just one match assume it is correct for now
        work = goodreads_response.find("./search/results/work")
        original_date["year"] = int(work.findtext("original_publication_year"))
        original_date["month"] = int(work.findtext("original_publication_month"))
        original_date["day"] = int(work.findtext("original_publication_day"))
    
    return original_date

def get_book_info(asin: str) -> Tuple[Book, BookChapters]:
    book_response = json.loads(make_request(f"{AUDNEX_ENDPOINT}/books/{asin}"))
    chapter_response = json.loads(make_request(f"{AUDNEX_ENDPOINT}/books/{asin}/chapters"))
    book = Book.from_audnex_book(book_response)
    book_chapters = BookChapters.from_audnex_chapter_info(chapter_response)
    return (book, book_chapters)

def make_request(url):
    """Makes a request to the specified url and returns received response
    The request will be retried up to 3 times in case of failure.
    """
    NUM_RETRIES = 3
    SLEEP_TIME = 2
    for n in range(0, NUM_RETRIES):
        try:
            req = request.Request(url, headers={
                # Circumvent audnex's user-agent blocking
                'User-Agent': USER_AGENT,
            })
            with request.urlopen(req) as response:
                return response.read()
        except HTTPError as e:
            print(f"Error while requesting {url}, attempt {n+1}/{NUM_RETRIES}: status code {e.code}, {e.reason}")
            if n < NUM_RETRIES - 1:
                sleep(SLEEP_TIME)
                SLEEP_TIME *= n
            else:
                raise e
