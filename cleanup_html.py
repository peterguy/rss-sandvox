import sys
from bs4 import BeautifulSoup
import os

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

def main():
    # Check if there are enough arguments
    if len(sys.argv) < 3:
        print("Usage: python cleanup_html.py hostname file1 [file2 ... fileN]")
        sys.exit(1)

    hostname = sys.argv[1]
    # Process each file provided as argument
    for file_path in sys.argv[2:]:
        with open(file_path, 'r', encoding='utf-8') as file:
            soup, cleaned = clean_up_page(BeautifulSoup(file, 'html.parser'), hostname)
            if cleaned:
                print("cleaned up", file_path)
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(str(soup))

if __name__ == "__main__":
    main()
