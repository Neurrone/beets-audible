from xml.etree.ElementTree import Element

from .api import search_goodreads


def get_original_date(self, asin: str, authors: str, title: str) -> dict:
    api_key = self.config["goodreads_apikey"]
    goodreads_response = search_goodreads(api_key, asin)
    totalresults = goodreads_get_total_result(goodreads_response)

    if totalresults == 0:
        # search with author and title
        self._log.debug("search Goodreads again based on author/title.")
        goodreads_response = search_goodreads(api_key, f"{authors} {title}")
        totalresults = goodreads_get_total_result(goodreads_response)

    self._log.debug(f"{totalresults} results found")
    if totalresults >= 1:
        work = goodreads_get_best_match(self, goodreads_response, authors, title)
        original_date = parse_original_date(work)
    else:
        original_date = {}

    return original_date


def goodreads_get_best_match(self, response: Element, author: str, title: str) -> Element:
    # returns best matching work from results
    author_cleaned = author.replace(" ", "")
    # get all works
    for work in response.findall("./search/results/work"):
        best_book = work.find("best_book")

        # remove anything after parenthesis, this is where GR puts series and other non title info
        gr_title = best_book.find("title").text
        gr_title_cleaned = gr_title.split("(")[0].strip()

        # remove all spaces from author name. Audible can have names like James S.
        # A. Corey, GR might have James S.A. Corey
        gr_author = best_book.find("author/name").text
        gr_author_cleaned = gr_author.replace(" ", "").strip()

        # confirm author and titles
        if author_cleaned == gr_author_cleaned and title == gr_title_cleaned:
            self._log.debug(f"Goodreads match found #{best_book.find('id').text} - {gr_author} {gr_title}")
            return work


def goodreads_get_total_result(response: Element) -> int:
    return int(response.findtext("./search/total-results"))


def parse_original_date(work: Element) -> dict:
    original_date = {}
    if work is not None:
        year = work.findtext("original_publication_year")
        original_date["year"] = int(year) if year.isdigit() else None
        month = work.findtext("original_publication_month")
        original_date["month"] = int(month) if month.isdigit() else None
        day = work.findtext("original_publication_day")
        original_date["day"] = int(day) if day.isdigit() else None

    return original_date
