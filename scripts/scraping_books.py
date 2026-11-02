import csv
import re
from pathlib import Path
from time import perf_counter, sleep
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

type Category = dict[str, str]
type Book = dict[str, str | float]

BASE_URL = 'https://books.toscrape.com'
OUTPUT_PATH = Path(__file__).resolve().parents[1] / 'data' / 'books.csv'
BOOK_COLUMNS = ('category', 'title', 'price', 'image', 'rating')
MAX_ATTEMPTS = 3
RETRY_DELAY = 10
REQUEST_TIMEOUT = 90


def create_session() -> requests.Session:
    """
    Creates an HTTP session for collecting books.

    Returns:
        requests.Session: Session with the scraper's user agent configured.
    """
    session = requests.Session()
    session.headers.update(
        {
            'User-Agent': 'books-scraping/0.1.0'
        }
    )
    return session


def fetch_page(session: requests.Session, url: str) -> BeautifulSoup:
    """
    Fetches and parses an HTML page with up to three attempts.

    Args:
        session (requests.Session): Session used to request the page.
        url (str): Absolute URL of the page to collect.

    Returns:
        BeautifulSoup: Parsed HTML of the requested page.

    Raises:
        RuntimeError: When all attempts to request the page fail.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(
                url=url,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
        except requests.RequestException as error:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(
                    f'After {MAX_ATTEMPTS} failed attempts, '
                    f'it was not possible to collect {url}.'
                )
            print(f'Attempt {attempt} failed for {url}: {error}. Trying again...')
            sleep(RETRY_DELAY)
        else:
            return BeautifulSoup(
                response.content,
                'html.parser',
                from_encoding='utf-8'
            )


def get_categories(session: requests.Session, url: str) -> list[Category]:
    """
    Collects the names and URLs of all book categories.

    Args:
        session (requests.Session): Session used to request the catalogue.
        url (str): Absolute URL of the catalogue's home page.

    Returns:
        list[Category]: Category names and their absolute URLs.

    Raises:
        RuntimeError: When the home page cannot be fetched after three attempts.
        ValueError: When the home page contains no book categories.
    """
    page = fetch_page(session, url)
    categories = [
        {
            'category': link.get_text(strip=True),
            'url': urljoin(url, str(link['href']))
        }
        for link in page.select('.side_categories a[href*="catalogue/category/books/"]')
    ]
    if not categories:
        raise ValueError(f'No book categories were found at {url}.')
    return categories


def parse_books(page: BeautifulSoup, category: str, url: str) -> list[Book]:
    """
    Extracts book details from a category page.

    Args:
        page (BeautifulSoup): Parsed HTML containing the books.
        category (str): Category name assigned to the collected books.
        url (str): Absolute page URL used to resolve book images.

    Returns:
        list[Book]: Books with category, title, price, image URL, and rating.

    Raises:
        ValueError: When the page has no books or a book has missing or invalid data.
    """
    books: list[Book] = []
    for book in page.select('article.product_pod'):
        title = book.select_one('h3 a[title]')
        price = book.select_one('div.product_price p.price_color')
        image = book.select_one('div.image_container img[src]')
        rating = book.select_one('p.star-rating')
        if title is None or price is None or image is None or rating is None:
            raise ValueError(f'A book has missing details at {url}.')

        ratings = [value for value in rating.get_attribute_list('class') if value != 'star-rating']
        if not ratings:
            raise ValueError(f'A book has no rating at {url}.')

        books.append({
            'category': category,
            'title': str(title['title']),
            'price': float(re.sub(r'[^\d.]', '', price.get_text())),
            'image': urljoin(url, str(image['src'])),
            'rating': ratings[-1]
        })

    if not books:
        raise ValueError(f'No books were found at {url}.')
    return books


def scraping_books(session: requests.Session, categories: list[Category]) -> list[Book]:
    """
    Collects books from every page of each category.

    Args:
        session (requests.Session): Session used to request category pages.
        categories (list[Category]): Category names and their starting URLs.

    Returns:
        list[Book]: All books collected across the supplied categories.

    Raises:
        RuntimeError: When a category page cannot be fetched after three attempts.
        ValueError: When a category page has no books or contains invalid book data.
    """
    books: list[Book] = []
    for index, category in enumerate(categories, start=1):
        print(
            f'Collecting books from the {category["category"]} category. '
            f'Category {index} of {len(categories)} categories...'
        )
        url = category['url']
        while url:
            page = fetch_page(session, url)
            books.extend(parse_books(page, category['category'], url))
            next_page = page.select_one('li.next a[href]')
            url = urljoin(url, str(next_page['href'])) if next_page is not None else ''
    return books


def export_books(books: list[Book]) -> Path:
    """
    Saves the collected books to data/books.csv in the project root.

    Args:
        books (list[Book]): Book records to write to the CSV report.

    Returns:
        Path: Absolute path of the generated CSV report.

    Raises:
        OSError: When the output directory or CSV file cannot be written.
    """
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open('w', newline='', encoding='utf-8-sig') as report:
        writer = csv.DictWriter(report, fieldnames=BOOK_COLUMNS)
        writer.writeheader()
        writer.writerows(books)
    return OUTPUT_PATH


def main() -> None:
    """
    Runs the scraper immediately and exports the books to CSV.

    Returns:
        None: Completes the collection and prints the report location.

    Raises:
        RuntimeError: When a required page cannot be fetched after three attempts.
        ValueError: When categories or books are missing or book data is invalid.
        OSError: When the CSV report cannot be written.
    """
    start_time = perf_counter()
    with create_session() as session:
        categories = get_categories(session, BASE_URL)
        books = scraping_books(session, categories)

    report_path = export_books(books)
    print(f'{len(books)} books saved to {report_path}.')
    print(f'Scraping process successfully completed in {perf_counter() - start_time:.2f} seconds.')


if __name__ == '__main__':
    main()
