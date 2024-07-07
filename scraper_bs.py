import sys
import os
from bs4 import BeautifulSoup
import requests
from urllib.parse import urljoin, urlparse
import feedparser
from feedgen.feed import FeedGenerator, FeedEntry
from datetime import datetime
import tldextract
import re

def get_hostname(url):
    parsed_url = urlparse(url)
    return parsed_url.hostname

def format_date(date_str):
    # Accepts dates in the format Mon DD, YYYY
    date_obj = datetime.strptime(date_str, "%b %d, %Y")
    # Add time and format according to the expectations of the RSS feed
    formatted_date = date_obj.strftime("%a, %d %b %Y 00:00:00 GMT")
    return date_obj, formatted_date

def remove_invisible_chars(text):
    # Define a regular expression pattern to match invisible Unicode characters
    pattern = r'[\u0000-\u0008\u000B-\u000C\u000E-\u001F\u007F-\u009F\u00AD\u0600-\u0604\u070F\u17B4\u17B5\u200B-\u200F\u2028-\u202F\u2060-\u206F\uFEFF\uFFF9-\uFFFC\t]'
    
    # Use the sub() function to replace the matched characters with an empty string
    cleaned_text = re.sub(pattern, '', text)
    
    return cleaned_text

def clean_up_page(soup, hostname):
    
    replaced = False

    # replace relative links to images with protocol-relative links to the website, otherwise they stay as relative links
    # when imported into substack, and 404
    images = soup.select('span, img')
    for img in images:
        for x in ['src', 'data-img-src', 'data-img-src-hr']:
            src = img.get(x)
            if src and not src.startswith(('http://', 'https://', '//')):
                normalized_src = os.path.normpath(src).lstrip("./")
                img[x] = f"//{hostname}/{normalized_src}"
                replaced = True

    articles = soup.select('div#main-content > div.article')
    if articles:
        for article in articles:
            summary = article.select_one('div.article-summary')
            if not summary:
                continue
            for child in summary.children:
                if child.name == 'p' and child.select_one('img.first'):
                    # <div class="first graphic-container wide center ImageElement">
                    #     <div class="graphic">
                    #         <div class="figure-content">
                    #             <!-- sandvox.ImageElement --><img src="../../_Media/img_8269_med_hr.jpeg" alt="IMG 8269" width="455" height="341">
                    #             <!-- /sandvox.ImageElement --></div>
                    #     </div>
                    # </div>
                    #<p><img src="../../_Media/img_5912_med_hr_med_hr.jpeg" alt="" width="267" height="356" class="first"></p>
                    newelem = '<div class="first graphic-container wide center ImageElement"><div class="graphic"><div class="figure-content">'
                    newelem += str(child.select_one('img.first')).replace('class="first"', '')
                    newelem += '</div></div></div>'
                    child.replace_with(BeautifulSoup(newelem, 'html.parser'))
                    replaced = True
    return soup, replaced

def scrape_page(url, existing_entries, fg):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    soup, replaced = clean_up_page(soup, get_hostname(url))
    articles = soup.select('div#main-content > div.article')
    for article in articles:
        existing = False
        entry = FeedEntry()
        title_link = article.select_one('.index-title > a:nth-child(1)')
        if title_link:
            title = title_link.select_one('span:nth-child(1)')
            if title:
                if title.text in existing_entries:
                    print("updating existing entry:", title.text)
                    entry = existing_entries[title.text]
                    existing = True
                else:
                    entry.title(title.text)
            if not entry.link():
                href = title_link.get('href')
                if href:
                    link = urljoin(url, href)
                    entry.link(href=link)
                    entry.guid(link)
        if not entry.title():
            if entry.guid():
                print("skipping because of missing title:", entry.guid())
            else:
                print("skipping one of the articles because of missing title:", url)
            continue
        if not entry.published():
            timestamp = article.select_one('div.article-info > div.timestamp > a:nth-child(1)')
            if timestamp:
                sort_date, display_date = format_date(timestamp.text)
                entry.published(display_date)
            else:
                print("skipping because no published date:", entry.title())
                continue
        summary = article.select_one('div.article-summary')
        description = remove_invisible_chars(''.join(str(child) for child in summary.children))
        if not description:
            print("skipping because no description:", entry.title())
            continue
        entry.description(description)
        if not existing:
            fg.add_entry(entry)
    for link in soup.select('a'):
        href = link.get('href')
        if href:
            if href.startswith('archives'):
                scrape_page(urljoin(url, href), existing_entries, fg)


def main():
    if len(sys.argv) < 2:
        print("Usage: python scraper_bs.py <url of the posts>/ <file name of the existing feed (typically index.xml)>")
        sys.exit(1)
    
    base_url = sys.argv[1]
    existing_feed_url = base_url + sys.argv[2]

    existing_feed = feedparser.parse(existing_feed_url)
    
    fg = FeedGenerator()
    fg.id()
    fg.title(existing_feed.feed.title)
    fg.link(href=existing_feed.feed.link)
    fg.subtitle(existing_feed.feed.subtitle)
    fg.language(existing_feed.feed.language)
    fg.description(existing_feed.feed.description)
    if not fg.description():
        fg.description(fg.title())

    existing_entries = {}

    for entry in existing_feed.entries:
        new_entry = fg.add_entry()
        new_entry.id(entry.id)
        new_entry.title(entry.title)
        new_entry.link(href=entry.link)
        new_entry.guid(entry.link)
        new_entry.description(entry.description)
        new_entry.pubDate(entry.published)
        if 'author' in entry:
            new_entry.author({'name': entry.author})
        existing_entries[entry.title] = new_entry

    scrape_page(base_url, existing_entries, fg)

    fg.rss_file(filename='updated_rss.xml', pretty=True)

    # write to file first because rss_str does not output a string
    with open('updated_rss.xml', 'r', encoding='utf-8') as f:
        rss = f.read()
    
    # if the supplied url is secure (https), make sure all of the links in the rss feed are secure as well
    # when importing the feed into substack, the images are not imported, just links to them,
    # and if the image uses an insecure url, the browser may not load it.
    if base_url.startswith('https'):
        hostname = get_hostname(base_url)
        rss = rss.replace('http://' + hostname, 'https://' + hostname)
        if hostname.startswith('www.'):
            rss = rss.replace('http://' + hostname[4:], 'https://' + hostname[4:])
        else:
            rss = rss.replace('http://www.' + hostname, 'https://www.' + hostname)
    host_parts = tldextract.extract(base_url)
    if host_parts.subdomain != 'www':
        rss = rss.replace('//www.' + host_parts.domain + '.' + host_parts.suffix, '//' + host_parts.fqdn)

    with open('updated_rss.xml', 'w', encoding='utf-8') as f:
        f.write(rss)

if __name__ == "__main__":
    main()
