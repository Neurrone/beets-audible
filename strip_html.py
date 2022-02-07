from io import StringIO
from html.parser import HTMLParser

# see https://stackoverflow.com/questions/753052/strip-html-from-strings-in-python

class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = StringIO()
    def handle_data(self, d):
        self.text.write(d)
    def get_data(self):
        return self.text.getvalue()

def strip_html(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()