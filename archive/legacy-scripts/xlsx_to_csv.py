import zipfile
import xml.etree.ElementTree as ET
import csv
import os

def extract_xlsx_to_csv(xlsx_path, csv_path):
    with zipfile.ZipFile(xlsx_path, 'r') as zip_ref:
        # Load shared strings
        shared_strings = []
        if 'xl/sharedStrings.xml' in zip_ref.namelist():
            with zip_ref.open('xl/sharedStrings.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                # XLSX namespace
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('ns:si', ns):
                    t = si.find('ns:t', ns)
                    if t is not None:
                        shared_strings.append(t.text)
                    else:
                        # Handle rich text strings
                        text_parts = []
                        for r in si.findall('ns:r', ns):
                            t_part = r.find('ns:t', ns)
                            if t_part is not None:
                                text_parts.append(t_part.text)
                        shared_strings.append("".join(text_parts))

        # Load sheet1
        with zip_ref.open('xl/worksheets/sheet1.xml') as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            
            rows = []
            for row in root.findall('.//ns:row', ns):
                cells = []
                # Simple cell value extraction
                for c in row.findall('ns:c', ns):
                    v = c.find('ns:v', ns)
                    t = c.get('t')
                    val = ""
                    if v is not None:
                        val = v.text
                        if t == 's': # shared string
                            val = shared_strings[int(val)]
                    cells.append(val)
                rows.append(cells)
            
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(rows)

if __name__ == "__main__":
    xlsx = "/home/ubuntu/.openclaw/media/inbound/Alte_Kanzleien_1---811665a0-d86c-4e40-8353-57b23d7e928e.xlsx"
    extract_xlsx_to_csv(xlsx, "alte_kanzleien_raw.csv")
    print("Done")
