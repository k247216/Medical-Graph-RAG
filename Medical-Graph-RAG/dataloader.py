
import os
import pymupdf

def load_high(datapath):
    if datapath.endswith('.pdf'):
        doc = pymupdf.open(datapath)
        return "\n".join(page.get_text() for page in doc)

    all_content = ""
    with open(datapath, 'r', encoding='utf-8') as file:
        for line in file:
            all_content += line.strip() + "\n"
    return all_content





